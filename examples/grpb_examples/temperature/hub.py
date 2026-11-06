"""Hub: receives readings, keeps the latest per sensor, streams them to watchers.

Runs on the laptop (or any Pi). Over MQTT it is addressed by server ID (default "hub");
over plain gRPC sensors and fan controllers connect to <host>:50051.

    python -m grpb_examples.temperature.hub [--transport mqtt|grpc] [--port 50051]
"""

from __future__ import annotations

import argparse
import logging
import queue
import signal
import sys
import threading

import grpc

from grpb.config import Config
from grpb_examples import transport
from grpb_examples.temperature import temperature_pb2 as pb
from grpb_examples.temperature import temperature_pb2_grpc as pb_grpc

MIN_C, MAX_C = -50.0, 150.0  # plausible sensor range; anything else is rejected


def log(msg: str) -> None:
    sys.stdout.write(msg + "\n")  # one write per line, so lines from handler threads don't interleave


class Hub(pb_grpc.TemperatureServiceServicer):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: dict[str, pb.Reading] = {}
        self._counts: dict[str, int] = {}
        self._watchers: list[tuple[str, queue.Queue]] = []

    def ReportReading(self, request: pb.Reading, context: grpc.ServicerContext) -> pb.ReportAck:
        if not request.sensor_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "sensor_id is required")
        if not MIN_C <= request.celsius <= MAX_C:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                          f"celsius {request.celsius:.2f} outside [{MIN_C}, {MAX_C}]")
        with self._lock:
            self._latest[request.sensor_id] = request
            self._counts[request.sensor_id] = total = self._counts.get(request.sensor_id, 0) + 1
            watchers = [q for f, q in self._watchers if f in ("", request.sensor_id)]
        for q in watchers:
            try:
                q.put_nowait(request)
            except queue.Full:  # a stuck watcher must not block sensors
                pass
        log(f"[hub] {request.sensor_id} #{request.seq}: {request.celsius:.2f} °C "
            f"({request.ByteSize()} bytes) -> {len(watchers)} watcher(s)")
        return pb.ReportAck(seq=request.seq, total_stored=total)

    def GetLatest(self, request: pb.GetLatestRequest, context: grpc.ServicerContext) -> pb.Reading:
        with self._lock:
            reading = self._latest.get(request.sensor_id)
        if reading is None:
            context.abort(grpc.StatusCode.NOT_FOUND, f"no readings from {request.sensor_id!r}")
        return reading

    def WatchReadings(self, request: pb.WatchRequest, context: grpc.ServicerContext):
        q: queue.Queue = queue.Queue(maxsize=100)
        entry = (request.sensor_id, q)
        with self._lock:
            self._watchers.append(entry)
        context.add_callback(lambda: q.put(None))  # unblock the loop when the client goes away
        log(f"[hub] watcher joined (filter={request.sensor_id or '*'}, peer={context.peer()})")
        try:
            while (reading := q.get()) is not None:
                yield reading
        finally:
            with self._lock:
                self._watchers.remove(entry)
            log("[hub] watcher left")

    def close_watchers(self) -> None:
        with self._lock:
            for _, q in self._watchers:
                q.put(None)


def serve(kind: str, cfg: Config, port: int = 50051, hub: Hub | None = None):
    """Start a hub; returns (server, hub)."""
    hub = hub or Hub()
    server = transport.make_server(kind, cfg, port)
    pb_grpc.add_TemperatureServiceServicer_to_server(hub, server)
    server.start()
    return server, hub


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    transport.add_args(ap)
    ap.add_argument("--port", type=int, default=50051, help="listen port for --transport grpc")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="[grpb] %(message)s")
    cfg = Config.from_env()
    server, hub = serve(args.transport, cfg, args.port)
    log(f"[hub] TemperatureService on {transport.describe(args.transport, cfg)}  (Ctrl-C to stop)")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):  # SIGTERM: `kill`, systemd
        signal.signal(sig, lambda *_: stop.set())
    while not stop.wait(1):
        pass
    log("[hub] shutting down")
    hub.close_watchers()
    server.stop(grace=2).wait()


if __name__ == "__main__":
    main()
