"""Watch gRPB-M2M traffic on the broker: every frame with its kind, call, and size on the wire.
Ctrl-C prints a size summary per frame kind (payload bytes; MQTT adds topic + ~5 B header).

    python tools/sniff.py [--quiet]
"""

from __future__ import annotations

import argparse
import signal
import statistics
from collections import defaultdict

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from grpb import topics
from grpb.config import Config
from grpb.wire_pb2 import Frame


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefix", default=topics.DEFAULT_PREFIX)
    ap.add_argument("--quiet", action="store_true", help="only print the summary")
    args = ap.parse_args()
    cfg = Config.from_env()
    sizes: dict[str, list[int]] = defaultdict(list)
    topic_sizes: dict[str, list[int]] = defaultdict(list)

    def on_message(client, userdata, msg) -> None:
        if "/presence/" in msg.topic:
            if not args.quiet:
                print(f"presence  {msg.topic.rsplit('/', 1)[1]:<20} {msg.payload.decode()}")
            return
        f = Frame.FromString(msg.payload)
        kind = Frame.Kind.Name(f.kind)
        sizes[kind].append(len(msg.payload))
        topic_sizes[kind].append(len(msg.topic))
        if not args.quiet:
            status = f" code={f.code}" if f.code else ""
            print(f"{kind:<15} call={f.call_id:<5} {len(msg.payload):>4} B frame "
                  f"({len(f.payload)} B message){status}  {msg.topic}")

    c = mqtt.Client(CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    c.on_connect = lambda cl, *a: cl.subscribe(f"{args.prefix}/#")
    c.on_message = on_message
    c.connect(cfg.broker_host, cfg.broker_port)
    print(f"sniffing {args.prefix}/# on {cfg.broker_host}:{cfg.broker_port} (Ctrl-C for summary)", flush=True)
    signal.signal(signal.SIGTERM, signal.default_int_handler)  # `kill` also prints the summary
    try:
        c.loop_forever()
    except KeyboardInterrupt:
        pass
    print("\nframe kind       count  median frame B  median topic B")
    for kind, vals in sorted(sizes.items()):
        print(f"{kind:<15} {len(vals):>6}  {statistics.median(vals):>14}  {statistics.median(topic_sizes[kind]):>14}")


if __name__ == "__main__":
    main()
