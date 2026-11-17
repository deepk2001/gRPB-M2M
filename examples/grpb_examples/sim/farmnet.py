"""FarmNet: a fleet of farm sensors reporting through oneM2M (patched ACME) in JSON, CBOR or Protobuf.

Each simulated node is its own oneM2M AE with its own MQTT connection. It registers, creates a
container and writes a reading (content instance) every --interval seconds. An "alert service" AE
subscribes to every container and receives each reading as a notification. At the end, a few
containers are read back over HTTP as JSON, the way an existing dashboard would, to prove that
data written in Protobuf stays readable by anyone.

    python -m grpb_examples.sim farmnet --nodes 50 --interval 5 --format pb --duration 60
    python -m grpb_examples.sim farmnet --nodes 20 --duration 0 --keep      # demo: run until Ctrl-C

Needs the broker and the patched CSE (make broker, make cse).
"""

from __future__ import annotations

import argparse
import json
import random
import threading
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from grpb.config import Config
from grpb.onem2m.client import SERIALIZATIONS, Notification, Onem2mClient, Onem2mError

from . import common

API = "Ngrpb.farmnet"


class Node:
    """One field sensor: an AE with a 'data' container, its own MQTT connection and a simulated soil probe."""

    def __init__(self, idx: int, run_id: str, fmt: str, cfg: Config, rng: random.Random) -> None:
        self.idx, self.name = idx, f"farm{run_id}n{idx:03d}"
        self.cse_name = cfg.cse_name
        self.client = Onem2mClient(f"C{self.name}", serialization=fmt, host=cfg.broker_host, port=cfg.broker_port,
                                   cse_id=cfg.cse_id, timeout=cfg.request_timeout).connect()
        self.cnt = f"{cfg.cse_name}/{self.name}/data"
        self.soil, self.temp, self.hum, self.bat = rng.uniform(20, 40), rng.uniform(12, 30), rng.uniform(30, 80), 100.0
        self.rng = rng
        self.last_content = ""
        expect(self.client.request(1, cfg.cse_name, ty=2, pc={"m2m:ae": {
            "rn": self.name, "api": API, "rr": False, "srv": ["5"], "csz": [self.client.media_type],
            "lbl": ["app:farmnet", f"node:{idx}"]}}), 2001, f"register {self.name}")
        expect(self.client.request(1, f"{cfg.cse_name}/{self.name}", ty=3,
                                   pc={"m2m:cnt": {"rn": "data", "mni": 20}}), 2001, f"container {self.name}")

    def reading(self, plain: bool) -> str:
        r = self.rng
        self.soil = min(60.0, max(5.0, self.soil + r.gauss(0, 0.3)))
        self.temp = min(45.0, max(-5.0, self.temp + r.gauss(0, 0.2)))
        self.hum = min(100.0, max(5.0, self.hum + r.gauss(0, 0.5)))
        self.bat = max(0.0, self.bat - 0.001)
        if plain:
            return f"{self.temp:.1f}"
        return json.dumps({"soil": round(self.soil, 1), "t": round(self.temp, 2), "h": round(self.hum, 1),
                           "bat": round(self.bat), "ts": int(time.time())}, separators=(",", ":"))

    def remove(self) -> None:
        try:
            self.client.request(4, f"{self.cse_name}/{self.name}", timeout=5)
        except Onem2mError:
            pass

    def close(self) -> None:
        self.client.close()


class Collector:
    """The alert service: one AE subscribed to every node's container."""

    def __init__(self, run_id: str, fmt: str, cfg: Config) -> None:
        self.name = f"farm{run_id}alert"
        self.cse_name = cfg.cse_name
        self._lock = threading.Lock()
        self._sent: dict[str, float] = {}        # tag -> perf_counter at send
        self.received: dict[str, float] = {}     # tag -> latency ms
        self.client = Onem2mClient(f"C{self.name}", serialization=fmt, host=cfg.broker_host, port=cfg.broker_port,
                                   cse_id=cfg.cse_id, timeout=cfg.request_timeout, on_notify=self._on_notify).connect()
        c = self.client
        expect(c.request(1, cfg.cse_name, ty=2, pc={"m2m:ae": {
            "rn": self.name, "api": API, "rr": True, "srv": ["5"], "poa": [c.poa], "csz": [c.media_type],
            "lbl": ["app:farmnet", "role:alerts"]}}), 2001, "register alert service")

    def subscribe(self, node: Node) -> None:
        expect(self.client.request(1, node.cnt, ty=23, pc={"m2m:sub": {
            "rn": "alerts", "nu": [self.client.originator], "enc": {"net": [3]}}}), 2001, f"subscribe {node.name}")

    def expect_tag(self, tag: str, t_send: float) -> None:
        with self._lock:
            self._sent[tag] = t_send

    def _on_notify(self, n: Notification) -> None:
        cin = n.primitive.get("pc", {}).get("m2m:sgn", {}).get("nev", {}).get("rep", {}).get("m2m:cin", {})
        tag = (cin.get("lbl") or [None])[0]
        with self._lock:
            t_send = self._sent.pop(tag, None)
            if t_send is not None:
                self.received[tag] = (n.received - t_send) * 1000

    def remove(self) -> None:
        try:
            self.client.request(4, f"{self.cse_name}/{self.name}", timeout=5)
        except Onem2mError:
            pass


def expect(r: Any, rsc: int, what: str) -> None:
    if r.rsc != rsc:
        raise SystemExit(f"{what} failed: rsc={r.rsc} {r.pc}")


def http_latest(cfg: Config, node: Node) -> str | None:
    """Read a node's latest reading over HTTP as JSON, like an existing oneM2M dashboard would."""
    req = urllib.request.Request(f"{cfg.cse_http}/{node.cnt}/la", headers={
        "X-M2M-Origin": "CAdmin", "X-M2M-RI": uuid.uuid4().hex[:12], "X-M2M-RVI": "5",
        "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=cfg.request_timeout) as r:
            return json.load(r).get("m2m:cin", {}).get("con")
    except OSError:
        return None


def sum_stats(clients: list[Onem2mClient]) -> dict[str, int]:
    total = {"msgs_out": 0, "bytes_out": 0, "msgs_in": 0, "bytes_in": 0}
    for c in clients:
        for k, v in c.stats().items():
            total[k] += v
    return total


def main(args: argparse.Namespace) -> None:
    cfg = Config.from_env()
    run = common.Run("farmnet", args)
    run_id = uuid.uuid4().hex[:5]
    rng = random.Random(args.seed)
    run.log(f"farmnet: {args.nodes} nodes x 1 reading / {args.interval}s in {args.format}, "
            f"broker {cfg.broker_host}:{cfg.broker_port}, CSE {cfg.cse_http}, netem={args.netem}")

    # Setup happens before the network emulation and the clock, so it never counts.
    t_setup = time.monotonic()
    collector = Collector(run_id, args.format, cfg)
    with ThreadPoolExecutor(args.setup_workers) as pool:
        nodes = list(pool.map(lambda i: Node(i, run_id, args.format, cfg, random.Random(rng.random())),
                              range(args.nodes)))
        list(pool.map(collector.subscribe, nodes))
    run.log(f"setup: {len(nodes)} AEs, containers and subscriptions in {time.monotonic() - t_setup:.2f}s")

    sampler = common.Sampler(common.find_pids())
    stop = threading.Event()
    snap: dict[str, Any] = {}
    plain = args.content == "plain"

    def node_loop(node: Node) -> None:
        nxt = time.monotonic() + rng.uniform(0, args.interval)  # spread the fleet over the interval
        seq = 0
        while common.sleep_until(nxt, stop):
            seq += 1
            tag = f"n{node.idx}s{seq}"
            content = node.reading(plain)
            lag_ms = (time.monotonic() - nxt) * 1000
            measured = run.measuring()
            t_send = time.perf_counter()
            if measured:
                collector.expect_tag(tag, t_send)
            row: dict[str, Any] = {"t": round(run.t(), 3), "node": node.idx, "seq": seq, "tag": tag,
                                   "sched_lag_ms": round(lag_ms, 2)}
            try:
                r = node.client.request(1, node.cnt, ty=4, pc={"m2m:cin": {
                    "cnf": "application/json:0", "con": content, "lbl": [tag]}})
                row.update(rsc=r.rsc, ok=int(r.rsc == 2001), rtt_ms=round(r.rtt_ms, 3),
                           req_payload_B=r.req_bytes, resp_payload_B=r.resp_bytes)
                if r.rsc == 2001:
                    node.last_content = content
            except Onem2mError as e:
                row.update(rsc="", ok=0, rtt_ms="", error=str(e)[:80])
            if measured:
                run.add(row)
            nxt += args.interval
            if nxt < time.monotonic():   # fell behind (overloaded): don't burst to catch up
                nxt = time.monotonic()

    threads = [threading.Thread(target=node_loop, args=(n,), daemon=True) for n in nodes]
    try:
        with common.Netem(args.netem):
            run.t0 = time.monotonic()
            run.t_measure = run.t0 + args.warmup
            sampler.start()
            for th in threads:
                th.start()
            run.event("start", nodes=args.nodes, format=args.format, netem=args.netem)
            common.sleep_until(run.t_measure, stop)
            snap["start"] = (sum_stats([n.client for n in nodes]), sum_stats([collector.client]), common.loopback_bytes())
            run.event("measuring")
            end = run.t_measure + args.duration if args.duration > 0 else float("inf")
            last_report = time.monotonic()
            while time.monotonic() < end:
                time.sleep(min(1.0, max(0.0, end - time.monotonic())))
                if time.monotonic() - last_report >= 10:
                    last_report = time.monotonic()
                    ok = [s for s in run.samples if s.get("ok")]
                    run.log(f"  t={run.t():5.0f}s  readings={len(ok)}  errors={len(run.samples) - len(ok)}  "
                            f"rtt p95={common.pct([s['rtt_ms'] for s in ok[-500:]], 95)} ms")
            snap["end"] = (sum_stats([n.client for n in nodes]), sum_stats([collector.client]), common.loopback_bytes())
            stop.set()
            for th in threads:
                th.join(cfg.request_timeout + 1)
            time.sleep(1.0)  # trailing notifications
            run.event("stopped")
    except KeyboardInterrupt:
        stop.set()
        snap.setdefault("end", (sum_stats([n.client for n in nodes]), sum_stats([collector.client]),
                                common.loopback_bytes()))
        run.event("interrupted")
    finally:
        sampler.stop()

    # Interop: read some nodes' latest reading over HTTP/JSON and compare with what was written.
    check = rng.sample(nodes, min(10, len(nodes)))
    interop_ok = sum(1 for n in check if n.last_content and http_latest(cfg, n) == n.last_content)
    run.event("interop", checked=len(check), ok=interop_ok)

    if not args.keep:
        with ThreadPoolExecutor(args.setup_workers) as pool:
            list(pool.map(Node.remove, nodes))
        collector.remove()
    for n in nodes:
        n.close()
    collector.client.close()

    # Join notification latencies onto the samples.
    for s in run.samples:
        lat = collector.received.get(s["tag"])
        s["notify_ms"] = round(lat, 3) if lat is not None else ""

    summary = summarize(run, args, snap, sampler, check, interop_ok)
    run.finish(summary, COLUMNS, resources=sampler.rows, notes=NOTES)


def summarize(run: common.Run, args: argparse.Namespace, snap: dict, sampler: common.Sampler,
              check: list, interop_ok: int) -> dict:
    ok = [s for s in run.samples if s.get("ok")]
    rtts = [s["rtt_ms"] for s in ok]
    notes = [s["notify_ms"] for s in ok if s["notify_ms"] != ""]
    secs = max(min(run.t(), args.duration) if args.duration > 0 else run.t(), 1e-9)
    zero = {"msgs_out": 0, "bytes_out": 0, "msgs_in": 0, "bytes_in": 0}
    (n0, c0, lo0), (n1, c1, lo1) = snap.get("start", (zero, zero, None)), snap.get("end", (zero, zero, None))
    dev_bytes = (n1["bytes_out"] - n0["bytes_out"]) + (n1["bytes_in"] - n0["bytes_in"])
    dev_msgs = n1["msgs_out"] - n0["msgs_out"]
    per_reading = dev_bytes / dev_msgs if dev_msgs else 0.0
    notif_msgs = c1["msgs_in"] - c0["msgs_in"]
    per_notif = (c1["bytes_in"] - c0["bytes_in"]) / notif_msgs if notif_msgs else ""
    lo_per = (lo1 - lo0) / dev_msgs if dev_msgs and lo0 is not None and lo1 is not None else ""
    per_day = 86400 / args.interval
    return {
        "app": "farmnet", "format": args.format, "nodes": args.nodes, "interval_s": args.interval,
        "content": args.content, "netem": args.netem, "duration_s": round(secs, 1),
        "offered_per_s": round(args.nodes / args.interval, 2), "achieved_per_s": round(len(ok) / secs, 2),
        "readings": len(ok), "errors": len(run.samples) - len(ok),
        "error_rate": round((len(run.samples) - len(ok)) / len(run.samples), 4) if run.samples else "",
        "req_payload_B": common.mean(s["req_payload_B"] for s in ok),
        "resp_payload_B": common.mean(s["resp_payload_B"] for s in ok),
        "device_link_B_per_reading": round(per_reading, 1),
        "notify_B": round(per_notif, 1) if per_notif != "" else "",
        "loopback_B_per_reading_all_hops": round(lo_per, 1) if lo_per != "" else "",
        "device_kB_per_day": round(per_reading * per_day / 1e3, 1),
        "fleet_MB_per_day": round(per_reading * per_day * args.nodes / 1e6, 2),
        "rtt_p50_ms": common.pct(rtts, 50), "rtt_p95_ms": common.pct(rtts, 95), "rtt_p99_ms": common.pct(rtts, 99),
        "notify_p50_ms": common.pct(notes, 50), "notify_p95_ms": common.pct(notes, 95),
        "notifications_missing": len(ok) - len(notes),
        "sched_lag_p95_ms": common.pct([s["sched_lag_ms"] for s in run.samples], 95),
        "interop_checked": len(check), "interop_ok": interop_ok,
        **sampler.means(),
    }


COLUMNS = [("format", "format"), ("nodes", "nodes"), ("netem", "network"), ("achieved_per_s", "readings/s"),
           ("errors", "errors"), ("device_link_B_per_reading", "device B/reading"), ("notify_B", "notify B"),
           ("fleet_MB_per_day", "fleet MB/day"), ("rtt_p50_ms", "RTT p50 ms"), ("rtt_p95_ms", "p95"),
           ("notify_p95_ms", "notify p95 ms"), ("interop_ok", "JSON reads ok"), ("cse_cpu_mean", "CSE CPU %"),
           ("broker_cpu_mean", "broker CPU %")]

NOTES = ("device B/reading = exact MQTT PUBLISH bytes of request + response on the device's own link "
         "(topics and properties included, PUBACKs excluded). fleet MB/day projects that over 24 h at this "
         "interval. JSON reads ok = containers read back over HTTP as JSON matching what the device wrote.")


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("farmnet", help="sensor fleet through oneM2M (needs broker + CSE)",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--nodes", type=int, default=50, help="simulated sensors")
    p.add_argument("--interval", type=float, default=5.0, help="seconds between readings per sensor")
    p.add_argument("--format", choices=SERIALIZATIONS, default="pb", help="oneM2M serialization")
    p.add_argument("--content", choices=("reading", "plain"), default="reading",
                   help="reading = small JSON object per reading, plain = one number")
    p.add_argument("--keep", action="store_true", help="leave the AEs in the CSE afterwards (for the dashboard)")
    p.add_argument("--seed", type=int, default=1, help="random seed for sensor values and timing")
    p.add_argument("--setup-workers", type=int, default=8, help="parallel registrations during setup")
    common.add_args(p, duration=60, warmup=10)
    p.set_defaults(func=main)
