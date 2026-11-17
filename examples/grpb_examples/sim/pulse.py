"""PulseWatch: wearables / vibration sensors stream samples at a high rate; several viewers watch live.

Each simulated node publishes --hz samples per second to a hub; --viewers clients (a live chart, an
anomaly detector, an archiver) each hold a Watch() stream and receive every sample. The same
.proto and the same code run over three transports:

  grpb   gRPB-M2M: typed calls and server streaming over MQTT (hub in its own process)
  grpc   plain gRPC over HTTP/2, the usual way (hub in its own process)
  json   the usual MQTT way: nodes publish JSON, viewers subscribe directly, no hub, no replies

    python -m grpb_examples.sim pulse --transport grpb --nodes 10 --hz 20 --viewers 3 --duration 60
    python -m grpb_examples.sim pulse --transport grpb --flap 20:5      # 5 s total outage at t=20 s (Linux)

Needs the broker for grpb and json.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import queue
import random
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections import defaultdict
from concurrent import futures
from typing import Any

import grpc
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

import grpb
from grpb._endpoint import publish_packet_size
from grpb.config import Config

from . import common
from . import pulse_pb2 as pb
from . import pulse_pb2_grpc as pb_grpc

TRANSPORTS = ("grpb", "grpc", "json")


# --- the hub (runs in its own process for grpb and grpc) -----------------------------------------


class PulseHub(pb_grpc.PulseServicer):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._watchers: list[tuple[str, queue.Queue]] = []
        self.dropped = 0

    def Publish(self, request: pb.Sample, context: grpc.ServicerContext) -> pb.Ack:
        with self._lock:
            targets = [q for f, q in self._watchers if f in ("", request.node_id)]
        for q in targets:
            try:
                q.put_nowait(request)
            except queue.Full:
                self.dropped += 1
        return pb.Ack(seq=request.seq)

    def Watch(self, request: pb.WatchRequest, context: grpc.ServicerContext):
        q: queue.Queue = queue.Queue(maxsize=50_000)
        entry = (request.node_id, q)
        with self._lock:
            self._watchers.append(entry)
        context.add_callback(lambda: q.put(None))  # wake up when the viewer goes away
        try:
            while context.is_active():
                try:
                    item = q.get(timeout=0.5)
                except queue.Empty:
                    continue
                if item is None:
                    break
                yield item
        finally:
            with self._lock:
                self._watchers.remove(entry)


def hub_main(args: argparse.Namespace) -> None:
    cfg = Config.from_env()
    hub = PulseHub()
    if args.transport == "grpb":
        server = grpb.MqttServer(args.server_id, cfg.broker_host, cfg.broker_port, max_workers=args.workers)
    else:
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=args.workers))
        server.add_insecure_port(f"127.0.0.1:{args.port}")
    pb_grpc.add_PulseServicer_to_server(hub, server)
    server.start()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    stop.wait()
    server.stop(0.5).wait(3)


# --- nodes and viewers ---------------------------------------------------------------------------


def channel_for(transport: str, cfg: Config, server_id: str, port: int, client_id: str) -> Any:
    if transport == "grpb":
        return grpb.MqttChannel(server_id, cfg.broker_host, cfg.broker_port, client_id=client_id)
    # A private connection per simulated device (grpc would otherwise share one between channels).
    return grpc.insecure_channel(f"127.0.0.1:{port}", options=[("grpc.use_local_subchannel_pool", 1)])


class Motion:
    """Simulated wrist/vibration sensor: accelerometer around 1 g plus a heart rate."""

    def __init__(self, rng: random.Random) -> None:
        self.rng, self.phase, self.hr = rng, rng.uniform(0, 6.28), rng.uniform(60, 90)

    def sample(self, node_id: str, seq: int) -> pb.Sample:
        r, t = self.rng, time.monotonic()
        self.hr = min(180.0, max(45.0, self.hr + r.gauss(0, 0.3)))
        return pb.Sample(node_id=node_id, seq=seq, sent_us=common.now_us(),
                         accel=[round(0.1 * math.sin(t * 6 + self.phase) + r.gauss(0, 0.02), 4),
                                round(0.1 * math.cos(t * 6 + self.phase) + r.gauss(0, 0.02), 4),
                                round(1.0 + r.gauss(0, 0.02), 4)],
                         heart_rate=round(self.hr, 1))


def as_json(s: pb.Sample) -> bytes:
    return json.dumps({"node_id": s.node_id, "seq": s.seq, "sent_us": s.sent_us,
                       "accel": [round(a, 4) for a in s.accel], "heart_rate": round(s.heart_rate, 1)},
                      separators=(",", ":")).encode()


class Viewer:
    """Receives every sample; records delivery delay and which sequence numbers arrived."""

    def __init__(self, idx: int, run: common.Run, transport: str, cfg: Config, server_id: str, port: int,
                 topic: str, run_id: str) -> None:
        self.idx, self.run, self.transport = idx, run, transport
        self.received: dict[str, set[int]] = defaultdict(set)
        self.bytes_in = 0
        self.first_sample = threading.Event()
        self._call = None
        cid = f"pulse-{run_id}-v{idx}"
        if transport == "json":
            self._mq = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=cid, protocol=mqtt.MQTTv5)
            self._mq.on_message = lambda c, u, m: self._json_msg(m)
            self._mq.on_connect = lambda c, u, f, rc, p: c.subscribe(topic, qos=1)
            self._mq.connect(cfg.broker_host, cfg.broker_port, keepalive=15)
            self._mq.loop_start()
        else:
            self._ch = channel_for(transport, cfg, server_id, port, cid)
            self._thread = threading.Thread(target=self._watch, daemon=True)
            self._thread.start()

    def _record(self, node_id: str, seq: int, sent_us: int, size: int) -> None:
        now = common.now_us()
        self.first_sample.set()
        self.bytes_in += size
        self.received[node_id].add(seq)
        self.run.add({"kind": "delivery", "t": round(self.run.t(), 3), "viewer": self.idx, "node": node_id,
                      "seq": seq, "sent_us": sent_us, "delay_ms": round((now - sent_us) / 1000, 3)})

    def _json_msg(self, m: Any) -> None:
        d = json.loads(m.payload)
        self._record(d["node_id"], d["seq"], d["sent_us"],
                     publish_packet_size(m.topic, len(m.payload), len(m.properties.pack()) if m.properties else 1))

    def _watch(self) -> None:
        stub = pb_grpc.PulseStub(self._ch)
        while True:
            try:
                self._call = stub.Watch(pb.WatchRequest(), wait_for_ready=True)
                for s in self._call:
                    self._record(s.node_id, s.seq, s.sent_us, 0)
                return
            except grpc.RpcError as e:
                if e.code() == grpc.StatusCode.CANCELLED:
                    return
                time.sleep(0.5)  # hub or network gone: rejoin

    def stats_bytes(self) -> int:
        if self.transport == "grpb":
            return self._ch.stats()["bytes_in"]
        return self.bytes_in

    def close(self) -> None:
        if self.transport == "json":
            self._mq.disconnect()
            self._mq.loop_stop()
            return
        if self._call is not None:
            self._call.cancel()
        self._ch.close()


class Node:
    def __init__(self, idx: int, run: common.Run, transport: str, cfg: Config, server_id: str, port: int,
                 topic_head: str, run_id: str, rng: random.Random) -> None:
        self.idx, self.run, self.transport = idx, run, transport
        self.node_id = f"w{idx:03d}"
        self.motion = Motion(rng)
        self.published: list[tuple[int, int]] = []   # (seq, sent_us) acknowledged
        self.bytes = 0
        cid = f"pulse-{run_id}-n{idx}"
        if transport == "json":
            self.topic = f"{topic_head}/{self.node_id}"
            self._mq = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=cid, protocol=mqtt.MQTTv5)
            self._mq.connect(cfg.broker_host, cfg.broker_port, keepalive=15)
            self._mq.loop_start()
        else:
            self._ch = channel_for(transport, cfg, server_id, port, cid)
            self._stub = pb_grpc.PulseStub(self._ch)

    def send(self, seq: int) -> dict:
        s = self.motion.sample(self.node_id, seq)
        row: dict[str, Any] = {"kind": "publish", "t": round(self.run.t(), 3), "node": self.node_id, "seq": seq,
                               "sent_us": s.sent_us}
        t0 = time.perf_counter()
        try:
            if self.transport == "json":
                payload = as_json(s)
                info = self._mq.publish(self.topic, payload, qos=1)
                info.wait_for_publish(2.0)   # PUBACK from the broker (no reply from anyone else)
                if not info.is_published():
                    raise TimeoutError("no PUBACK")
                self.bytes += publish_packet_size(self.topic, len(payload))
            else:
                self._stub.Publish(s, timeout=2.0)
            row.update(ok=1, rtt_ms=round((time.perf_counter() - t0) * 1000, 3))
            self.published.append((seq, s.sent_us))
        except grpc.RpcError as e:
            row.update(ok=0, code=e.code().name, rtt_ms=round((time.perf_counter() - t0) * 1000, 3))
        except (TimeoutError, RuntimeError, ValueError) as e:
            row.update(ok=0, code=type(e).__name__, rtt_ms=round((time.perf_counter() - t0) * 1000, 3))
        return row

    def stats_bytes(self) -> int:
        if self.transport == "grpb":
            st = self._ch.stats()
            return st["bytes_out"] + st["bytes_in"]
        return self.bytes

    def close(self) -> None:
        if self.transport == "json":
            self._mq.disconnect()
            self._mq.loop_stop()
        else:
            self._ch.close()


# --- the run ---------------------------------------------------------------------------------------


def start_hub(args: argparse.Namespace, server_id: str, port: int) -> subprocess.Popen | None:
    if args.transport == "json":
        return None
    cmd = [sys.executable, "-m", "grpb_examples.sim", "pulse-hub", "--transport", args.transport,
           "--server-id", server_id, "--port", str(port), "--workers", str(args.nodes + args.viewers + 16)]
    return subprocess.Popen(cmd, env=os.environ.copy())


def free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(args: argparse.Namespace) -> None:
    cfg = Config.from_env()
    run = common.Run("pulse", args)
    run_id = uuid.uuid4().hex[:5]
    server_id, port, topic_head = f"pulse-{run_id}", free_port(), f"naive/pulse/{run_id}"
    rng = random.Random(args.seed)
    run.log(f"pulse: {args.nodes} nodes x {args.hz} Hz, {args.viewers} viewers, transport={args.transport}, "
            f"netem={args.netem}")

    hub = start_hub(args, server_id, port)
    sampler = common.Sampler(common.find_pids())
    if hub:
        sampler.add("hub", hub.pid)
    stop = threading.Event()
    flap_at, flap_for = (float(x) for x in args.flap.split(":")) if args.flap else (None, None)
    try:
        viewers = [Viewer(i, run, args.transport, cfg, server_id, port, f"{topic_head}/+", run_id)
                   for i in range(args.viewers)]
        nodes = [Node(i, run, args.transport, cfg, server_id, port, topic_head, run_id, random.Random(rng.random()))
                 for i in range(args.nodes)]
        if args.transport != "json":   # wait until the hub answers and every viewer is attached
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                row = nodes[0].send(0)
                if row.get("ok") and all(v.first_sample.wait(0.05) for v in viewers):
                    break
                time.sleep(0.2)
            else:
                raise SystemExit("hub did not come up (is the broker running?)")
        else:
            time.sleep(1.0)

        def node_loop(node: Node) -> None:
            period = 1.0 / args.hz
            nxt = time.monotonic() + rng.uniform(0, period)
            seq = 0
            while common.sleep_until(nxt, stop):
                seq += 1
                measured = run.measuring()
                row = node.send(seq)
                row["sched_lag_ms"] = round((time.monotonic() - nxt) * 1000, 2)
                if measured:
                    run.add(row)
                nxt += period
                if nxt < time.monotonic():
                    nxt = time.monotonic()

        with common.Netem(args.netem) as net:
            run.t0 = time.monotonic()
            run.t_measure = run.t0 + args.warmup
            sampler.start()
            threads = [threading.Thread(target=node_loop, args=(n,), daemon=True) for n in nodes]
            for th in threads:
                th.start()
            run.event("start", transport=args.transport, nodes=args.nodes, hz=args.hz, viewers=args.viewers)
            common.sleep_until(run.t_measure, stop)
            w0, snap0 = common.now_us(), snapshot(nodes, viewers)
            run.event("measuring")
            end = run.t_measure + args.duration
            flapped = False
            last = time.monotonic()
            while time.monotonic() < end:
                time.sleep(0.1)
                if flap_at is not None and not flapped and run.t() >= flap_at:
                    flapped = True
                    run.event("network_down", seconds=flap_for)
                    net.set("loss 100%")
                    time.sleep(flap_for)
                    net.set(net.spec)
                    run.event("network_up")
                if time.monotonic() - last >= 10:
                    last = time.monotonic()
                    pubs = [s for s in run.samples if s["kind"] == "publish"]
                    run.log(f"  t={run.t():5.0f}s  published={sum(s.get('ok', 0) for s in pubs)}  "
                            f"delivered={sum(1 for s in run.samples if s['kind'] == 'delivery')}")
            w1, snap1 = common.now_us(), snapshot(nodes, viewers)
            stop.set()
            for th in threads:
                th.join(3)
            time.sleep(1.0)   # let in-flight samples reach the viewers
            run.event("stopped")
    finally:
        stop.set()
        sampler.stop()
        for v in locals().get("viewers", []):
            v.close()
        for n in locals().get("nodes", []):
            n.close()
        if hub:
            hub.terminate()
            try:
                hub.wait(5)
            except subprocess.TimeoutExpired:
                hub.kill()

    summary = summarize(run, args, nodes, viewers, w0, w1, snap0, snap1, sampler, flap_at)
    run.finish(summary, COLUMNS, resources=sampler.rows, notes=NOTES)


def snapshot(nodes: list[Node], viewers: list[Viewer]) -> tuple[int, int, int | None]:
    return sum(n.stats_bytes() for n in nodes), sum(v.stats_bytes() for v in viewers), common.loopback_bytes()


def summarize(run: common.Run, args: argparse.Namespace, nodes: list[Node], viewers: list[Viewer],
              w0: int, w1: int, snap0: tuple, snap1: tuple, sampler: common.Sampler, flap_at: float | None) -> dict:
    pubs = [s for s in run.samples if s["kind"] == "publish" and w0 <= s["sent_us"] < w1]
    ok = [s for s in pubs if s.get("ok")]
    dels = [s for s in run.samples if s["kind"] == "delivery" and w0 <= s["sent_us"] < w1]
    delays = [s["delay_ms"] for s in dels]
    secs = (w1 - w0) / 1e6
    # Which acknowledged samples did each viewer miss?
    expected = {n.node_id: {seq for seq, sent in n.published if w0 <= sent < w1} for n in nodes}
    missing = sum(len(exp - v.received.get(node, set())) for v in viewers for node, exp in expected.items())
    expected_total = sum(len(e) for e in expected.values()) * len(viewers)
    dev_bytes, view_bytes, lo = snap1[0] - snap0[0], snap1[1] - snap0[1], None
    if snap0[2] is not None and snap1[2] is not None:
        lo = snap1[2] - snap0[2]
    example = Motion(random.Random(0)).sample("w000", 1234)
    recovery = ""
    if flap_at is not None:
        down = next((e for e in run.events if e["event"] == "network_up"), None)
        if down:
            after = [s for s in ok if s["t"] >= down["t"]]
            recovery = round((min(s["t"] for s in after) - down["t"]) * 1000, 1) if after else ""
    return {
        "app": "pulse", "transport": args.transport, "nodes": args.nodes, "hz": args.hz, "viewers": args.viewers,
        "netem": args.netem, "flap": args.flap or "", "duration_s": round(secs, 1),
        "offered_per_s": args.nodes * args.hz, "published": len(ok), "achieved_per_s": round(len(ok) / secs, 1),
        "publish_errors": len(pubs) - len(ok),
        "publish_rtt_p50_ms": common.pct([s["rtt_ms"] for s in ok], 50),
        "publish_rtt_p95_ms": common.pct([s["rtt_ms"] for s in ok], 95),
        "delivered": len(dels), "delivery_ratio": round(1 - missing / expected_total, 5) if expected_total else "",
        "missing": missing,
        "delay_p50_ms": common.pct(delays, 50), "delay_p95_ms": common.pct(delays, 95),
        "delay_p99_ms": common.pct(delays, 99), "delay_max_ms": round(max(delays), 1) if delays else "",
        "sample_pb_B": example.ByteSize(), "sample_json_B": len(as_json(example)),
        "device_link_B_per_sample": round(dev_bytes / len(ok), 1) if ok and args.transport != "grpc" else "",
        "viewer_B_per_sample": round(view_bytes / len(dels), 1) if dels and args.transport != "grpc" else "",
        "loopback_B_per_sample_all_hops": round(lo / len(ok), 1) if ok and lo is not None else "",
        "recovery_ms": recovery,
        "sched_lag_p95_ms": common.pct([s["sched_lag_ms"] for s in pubs], 95),
        **sampler.means(),
    }


COLUMNS = [("transport", "transport"), ("nodes", "nodes"), ("hz", "Hz"), ("viewers", "viewers"),
           ("netem", "network"), ("achieved_per_s", "samples/s"), ("publish_errors", "errors"),
           ("delivery_ratio", "delivered"), ("delay_p50_ms", "delay p50 ms"), ("delay_p95_ms", "p95"),
           ("delay_p99_ms", "p99"), ("device_link_B_per_sample", "device B/sample"),
           ("sample_pb_B", "pb B"), ("sample_json_B", "JSON B"), ("hub_cpu_mean", "hub CPU %"),
           ("sim_cpu_mean", "sim CPU %")]

NOTES = ("delay = sample creation at the node to arrival at a viewer (one Pi clock). delivered = share of "
         "acknowledged samples every viewer received. device B/sample = exact MQTT bytes on the node's own link "
         "per sample, including the hub's reply for grpb (json has no reply, only a PUBACK, not counted); "
         "HTTP/2 framing isn't visible to the app, so grpc shows only loopback bytes in summary.csv.")


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("pulse", help="high-rate streaming to several viewers (grpb, grpc or json)",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--transport", choices=TRANSPORTS, default="grpb")
    p.add_argument("--nodes", type=int, default=10, help="simulated wearables")
    p.add_argument("--hz", type=float, default=20, help="samples per second per node")
    p.add_argument("--viewers", type=int, default=3, help="live consumers watching every sample")
    p.add_argument("--flap", default="", help="AT:SECONDS total network outage during the run (Linux), e.g. 20:5")
    p.add_argument("--seed", type=int, default=1)
    common.add_args(p, duration=60, warmup=5)
    p.set_defaults(func=main)

    h = sub.add_parser("pulse-hub", help=argparse.SUPPRESS)
    h.add_argument("--transport", choices=("grpb", "grpc"), required=True)
    h.add_argument("--server-id", required=True)
    h.add_argument("--port", type=int, required=True)
    h.add_argument("--workers", type=int, default=64)
    h.set_defaults(func=hub_main)
