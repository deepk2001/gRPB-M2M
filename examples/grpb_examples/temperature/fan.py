"""Fan controller: subscribes to WatchReadings() and switches a relay with hysteresis.
Fan turns ON above --on and OFF below --off (relay on GPIO17 on a Pi, simulated elsewhere).
Reconnects automatically if the hub restarts.

    python -m grpb_examples.temperature.fan [--transport mqtt|grpc] [--sensor s1] [--on 26] [--off 24]
"""

from __future__ import annotations

import argparse
import logging
import time

import grpc

from grpb.config import Config
from grpb_examples import transport
from grpb_examples.hal import make_relay, use_simulator
from grpb_examples.temperature import temperature_pb2 as pb
from grpb_examples.temperature import temperature_pb2_grpc as pb_grpc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    transport.add_args(ap)
    ap.add_argument("--sensor", default="", help="watch one sensor (default: all)")
    ap.add_argument("--on", type=float, default=26.0, help="turn fan on above this °C")
    ap.add_argument("--off", type=float, default=24.0, help="turn fan off below this °C")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="[grpb] %(message)s")
    if args.off >= args.on:
        ap.error("--off must be lower than --on")

    cfg = Config.from_env()
    relay = make_relay()
    print(f"[fan] backend={'simulator' if use_simulator() else 'hardware'} "
          f"hub={transport.describe(args.transport, cfg)} on>{args.on} off<{args.off}", flush=True)

    with transport.open_channel(args.transport, cfg) as channel:
        stub = pb_grpc.TemperatureServiceStub(channel)
        while True:
            try:
                # wait_for_ready: block until the hub is reachable instead of failing immediately
                for r in stub.WatchReadings(pb.WatchRequest(sensor_id=args.sensor), wait_for_ready=True):
                    if not relay.is_on and r.celsius > args.on:
                        relay.set(True)
                    elif relay.is_on and r.celsius < args.off:
                        relay.set(False)
                    print(f"[fan] {r.sensor_id} #{r.seq} {r.celsius:.2f} °C  fan={'ON' if relay.is_on else 'off'}",
                          flush=True)
                print("[fan] hub closed the stream; reconnecting", flush=True)
            except grpc.RpcError as e:
                print(f"[fan] stream lost ({e.code().name}); reconnecting in 2 s", flush=True)
                time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
