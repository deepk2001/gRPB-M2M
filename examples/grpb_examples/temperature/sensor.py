"""Sensor device: reads temperature (DS18B20 on a Pi, simulated elsewhere) and calls
ReportReading() on the hub at a fixed interval. Survives the hub being down or restarting.

    python -m grpb_examples.temperature.sensor [--transport mqtt|grpc] [--id s1] [--interval 2] [--seed 1]
    GRPB_BROKER_HOST=192.168.1.20 python -m grpb_examples.temperature.sensor   # on a Pi
"""

from __future__ import annotations

import argparse
import json
import socket
import time

import grpc

from grpb.config import Config
from grpb_examples import transport
from grpb_examples.hal import make_sensor, use_simulator
from grpb_examples.temperature import temperature_pb2 as pb
from grpb_examples.temperature import temperature_pb2_grpc as pb_grpc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    transport.add_args(ap)
    ap.add_argument("--id", default=f"{socket.gethostname().split('.')[0]}-temp")
    ap.add_argument("--interval", type=float, default=2.0, help="seconds between readings")
    ap.add_argument("--seed", type=int, default=None, help="simulator seed (different phase per sensor)")
    args = ap.parse_args()

    cfg = Config.from_env()
    sensor = make_sensor(seed=args.seed)
    print(f"[sensor {args.id}] backend={'simulator' if use_simulator() else 'hardware'} "
          f"hub={transport.describe(args.transport, cfg)}", flush=True)

    with transport.open_channel(args.transport, cfg, client_id=args.id) as channel:
        stub = pb_grpc.TemperatureServiceStub(channel)
        seq = 0
        while True:
            seq += 1
            reading = pb.Reading(sensor_id=args.id, celsius=sensor.read_celsius(),
                                 timestamp=int(time.time()), seq=seq)
            json_size = len(json.dumps({"sensor_id": reading.sensor_id, "celsius": round(reading.celsius, 2),
                                        "timestamp": reading.timestamp, "seq": reading.seq}))
            t0 = time.perf_counter()
            try:
                ack = stub.ReportReading(reading, timeout=5)
                rtt = (time.perf_counter() - t0) * 1000
                print(f"[sensor {args.id}] #{seq} {reading.celsius:.2f} °C  "
                      f"{reading.ByteSize()} B protobuf vs {json_size} B JSON  "
                      f"rtt {rtt:.1f} ms  stored={ack.total_stored}", flush=True)
            except grpc.RpcError as e:
                print(f"[sensor {args.id}] #{seq} failed: {e.code().name}: {e.details()}", flush=True)
            time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
