"""Collect evidence for Protobuf vs JSON vs CBOR in oneM2M over MQTT.

  codec   message size and encode/decode CPU time on real ACME primitives (no network)
  e2e     device -> broker -> patched ACME -> device, with notifications, all formats interleaved
  report  merge the summaries of several runs (e.g. laptop and Pi) into one table

Every run writes results/<timestamp>-<label>/ (pass --no-save to only print the summary):
  samples.csv   one row per measured operation (raw data, for charts and re-analysis)
  summary.csv   per format and operation: sizes, latency percentiles, ratios vs JSON
  summary.md    the same as a readable table
  env.json      machine, versions, broker/CSE location and the exact arguments

Examples:
  python tools/bench.py codec --label laptop
  python tools/bench.py e2e --n 300 --label laptop-local          # needs make broker + make cse
  GRPB_BROKER_HOST=deeps-macbook-air.local python tools/bench.py e2e --label pi-wifi   # on a Pi
  python tools/bench.py e2e --n 20 --no-save                      # quick check, nothing written
  python tools/bench.py report results/*
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import socket
import statistics
import sys
import threading
import time
import timeit
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from grpb.config import Config
from grpb.onem2m.client import SERIALIZATIONS, Notification, Onem2mClient, _codec

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from onem2m_samples import ALL as SAMPLES  # noqa: E402  (real primitives captured from ACME)

CONTENT = {
    "plain": "23.5",
    "reading": json.dumps({"sensor": "s1", "celsius": 23.51, "humidity": 41.2, "battery": 87,
                           "ts": 1794350000}, separators=(",", ":")),
}


# --- helpers ----------------------------------------------------------------------------------


def mqtt_packet_bytes(topic_len: int, payload_len: int) -> int:
    """Size of an MQTT 5 QoS 1 PUBLISH packet without properties: fixed header + remaining length
    varint + topic length (2) + topic + packet id (2) + property length (1) + payload."""
    remaining = 2 + topic_len + 2 + 1 + payload_len
    varint = 1 if remaining < 128 else 2 if remaining < 16384 else 3
    return 1 + varint + remaining


def pct(values: list[float], q: int) -> float:
    if len(values) < 2:
        return values[0] if values else float("nan")
    return statistics.quantiles(values, n=100, method="inclusive")[q - 1]


def out_dir(label: str, kind: str) -> Path:
    d = ROOT / "results" / f"{datetime.now():%Y%m%d-%H%M%S}-{kind}-{label}"
    d.mkdir(parents=True, exist_ok=False)
    return d


def env_info(args: argparse.Namespace, cfg: Config) -> dict:
    import google.protobuf
    import paho.mqtt

    import grpb
    try:
        import cbor2
        cbor_version = getattr(cbor2, "__version__", "installed")
    except ImportError:
        cbor_version = None
    model = ""
    try:
        model = Path("/proc/device-tree/model").read_text().strip("\x00\n")
    except OSError:
        pass
    return {
        "time": datetime.now().isoformat(timespec="seconds"),
        "host": socket.gethostname(), "platform": platform.platform(), "machine": platform.machine(),
        "device_model": model, "cpu_count": os.cpu_count(), "python": platform.python_version(),
        "grpb": grpb.__version__, "protobuf": google.protobuf.__version__, "paho_mqtt": paho.mqtt.__version__,
        "cbor2": cbor_version, "broker": f"{cfg.broker_host}:{cfg.broker_port}", "cse_id": cfg.cse_id,
        "args": {k: v for k, v in vars(args).items() if k != "func"},
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def markdown_table(rows: list[dict], cols: list[tuple[str, str]]) -> str:
    def fmt(v: Any) -> str:
        return f"{v:.2f}" if isinstance(v, float) else str(v)
    head = "| " + " | ".join(title for _, title in cols) + " |"
    sep = "|" + "|".join("---:" if i else "---" for i in range(len(cols))) + "|"
    body = ["| " + " | ".join(fmt(r.get(k, "")) for k, _ in cols) + " |" for r in rows]
    return "\n".join([head, sep, *body])


def finish(args: argparse.Namespace, kind: str, cfg: Config, samples: list[dict], summary: list[dict],
           md: str) -> None:
    print(md)
    if not args.save:
        print("\nnot saved (--no-save)")
        return
    d = out_dir(args.label, kind)
    (d / "env.json").write_text(json.dumps(env_info(args, cfg), indent=2))
    write_csv(d / "samples.csv", samples)
    write_csv(d / "summary.csv", summary)
    (d / "summary.md").write_text(md + "\n")
    print(f"\nresults: {d.relative_to(ROOT)}/")


# --- codec ------------------------------------------------------------------------------------


def cmd_codec(args: argparse.Namespace) -> None:
    cfg = Config.from_env()
    formats = [f for f in args.formats.split(",") if f]
    codecs = {f: _codec(f) for f in formats}
    samples, summary = [], []
    for name, prim in SAMPLES.items():
        sizes = {}
        for f in formats:
            enc, dec = codecs[f]
            data = enc(prim)
            assert dec(data) == prim, f"{f} does not round-trip {name}"
            n_enc = timeit.Timer(lambda: enc(prim)).autorange()[0]
            enc_us = min(timeit.repeat(lambda: enc(prim), number=n_enc, repeat=5)) / n_enc * 1e6
            n_dec = timeit.Timer(lambda: dec(data)).autorange()[0]
            dec_us = min(timeit.repeat(lambda: dec(data), number=n_dec, repeat=5)) / n_dec * 1e6
            sizes[f] = len(data)
            samples.append({"primitive": name, "format": f, "bytes": len(data),
                            "encode_us": round(enc_us, 2), "decode_us": round(dec_us, 2)})
    for f in formats:
        rows = [s for s in samples if s["format"] == f]
        json_rows = [s for s in samples if s["format"] == "json"]
        total, total_json = sum(r["bytes"] for r in rows), sum(r["bytes"] for r in json_rows)
        summary.append({
            "format": f, "primitives": len(rows), "total_bytes": total,
            "size_vs_json": round(total / total_json, 3) if total_json else "",
            "median_encode_us": round(statistics.median(r["encode_us"] for r in rows), 2),
            "median_decode_us": round(statistics.median(r["decode_us"] for r in rows), 2),
        })
    per_prim = []
    for name in SAMPLES:
        row = {"primitive": name}
        for f in formats:
            row[f] = next(s["bytes"] for s in samples if s["primitive"] == name and s["format"] == f)
        if "json" in formats and "pb" in formats:
            row["pb_vs_json"] = f"{row['pb'] / row['json']:.0%}"
        per_prim.append(row)
    md = ("## Codec: size and CPU on real ACME primitives\n\n"
          + markdown_table(summary, [("format", "format"), ("total_bytes", "bytes, all primitives"),
                                     ("size_vs_json", "size vs JSON"), ("median_encode_us", "encode µs (median)"),
                                     ("median_decode_us", "decode µs (median)")])
          + "\n\n### Bytes per primitive\n\n"
          + markdown_table(per_prim, [("primitive", "primitive"), *((f, f) for f in formats),
                                      *([("pb_vs_json", "pb/json")] if "pb_vs_json" in per_prim[0] else [])]))
    finish(args, "codec", cfg, samples, summary, md)


# --- end to end -------------------------------------------------------------------------------


class Device:
    """One AE per format, with a container and a subscription that notifies the AE itself."""

    def __init__(self, fmt: str, cfg: Config, run_id: str) -> None:
        self.fmt = fmt
        self.name = f"bench{fmt}{run_id}"
        self.notes: dict[str, Notification] = {}
        self._note_cv = threading.Condition()
        self.client = Onem2mClient(f"C{self.name}", serialization=fmt, host=cfg.broker_host,
                                   port=cfg.broker_port, cse_id=cfg.cse_id, timeout=cfg.request_timeout,
                                   on_notify=self._on_notify).connect()
        self.cnt = f"{cfg.cse_name}/{self.name}/data"
        c = self.client
        self._check(c.request(1, cfg.cse_name, ty=2, pc={"m2m:ae": {
            "rn": self.name, "api": "Ngrpb.bench", "rr": True, "srv": ["5"],
            "poa": [c.poa], "csz": [c.media_type]}}), 2001, "register AE")
        self._check(c.request(1, f"{cfg.cse_name}/{self.name}", ty=3,
                              pc={"m2m:cnt": {"rn": "data", "mni": 100}}), 2001, "create container")
        self._check(c.request(1, self.cnt, ty=23, pc={"m2m:sub": {"rn": "sub", "nu": [c.originator],
                                                                   "enc": {"net": [3]}}}), 2001, "subscribe")
        self._cse_name = cfg.cse_name

    @staticmethod
    def _check(r: Any, rsc: int, what: str) -> None:
        if r.rsc != rsc:
            raise SystemExit(f"{what} failed: rsc={r.rsc} {r.pc}")

    def _on_notify(self, n: Notification) -> None:
        rep = n.primitive.get("pc", {}).get("m2m:sgn", {}).get("nev", {}).get("rep", {})
        con = rep.get("m2m:cin", {}).get("con")
        tag = rep.get("m2m:cin", {}).get("lbl", [None])[0]
        if con is not None and tag:
            with self._note_cv:
                self.notes[tag] = n
                self._note_cv.notify_all()

    def wait_note(self, tag: str, timeout: float) -> Notification | None:
        with self._note_cv:
            self._note_cv.wait_for(lambda: tag in self.notes, timeout)
            return self.notes.pop(tag, None)

    def close(self) -> None:
        try:
            self.client.request(4, f"{self._cse_name}/{self.name}")
        finally:
            self.client.close()


def cmd_e2e(args: argparse.Namespace) -> None:
    cfg = Config.from_env()
    formats = [f for f in args.formats.split(",") if f]
    content = CONTENT[args.content]
    run_id = uuid.uuid4().hex[:6]
    print(f"e2e: {formats} x {args.n} (+{args.warmup} warm-up) via {cfg.broker_host}:{cfg.broker_port}, "
          f"content={args.content!r}", flush=True)
    devices = {f: Device(f, cfg, run_id) for f in formats}
    samples: list[dict] = []
    try:
        for i in range(args.warmup + args.n):
            measured = i >= args.warmup
            for f in formats:  # interleaved: drift affects every format equally
                d = devices[f]
                tag = f"i{i}"
                t_send = time.perf_counter()
                r = d.client.request(1, d.cnt, ty=4, pc={"m2m:cin": {"cnf": "application/json:0", "con": content,
                                                                     "lbl": [tag]}})
                note = d.wait_note(tag, cfg.request_timeout)
                if measured:
                    samples.append(row(f, "create_cin", i, r, note, t_send))
                r = d.client.request(2, f"{d.cnt}/la")
                if measured:
                    samples.append(row(f, "retrieve_la", i, r, None, None))
            if measured and (i - args.warmup + 1) % max(1, args.n // 10) == 0:
                print(f"  {i - args.warmup + 1}/{args.n}", flush=True)
    finally:
        for d in devices.values():
            d.close()
    summary = summarize(samples, formats)
    md = (f"## End to end: {args.label} ({args.n} iterations, content={args.content!r})\n\n"
          + markdown_table(summary, [
              ("op", "operation"), ("format", "format"), ("n", "n"),
              ("req_bytes", "request B"), ("resp_bytes", "response B"), ("notify_bytes", "notification B"),
              ("exchange_wire_bytes", "wire B/exchange"), ("wire_vs_json", "wire vs JSON"),
              ("rtt_median_ms", "RTT median ms"), ("rtt_p95_ms", "p95"), ("rtt_p99_ms", "p99"),
              ("notify_median_ms", "notify median ms"), ("errors", "errors")])
          + "\n\nwire B/exchange = MQTT PUBLISH packets for request + response (+ notification), "
            "including topics; PUBACKs are the same size for every format and are left out.")
    finish(args, "e2e", cfg, samples, summary, md)


def row(fmt: str, op: str, i: int, r: Any, note: Notification | None, t_send: float | None) -> dict:
    return {
        "format": fmt, "op": op, "iteration": i, "rsc": r.rsc,
        "req_bytes": r.req_bytes, "resp_bytes": r.resp_bytes,
        "req_wire_bytes": mqtt_packet_bytes(r.req_topic_bytes, r.req_bytes),
        "resp_wire_bytes": mqtt_packet_bytes(r.resp_topic_bytes, r.resp_bytes),
        "rtt_ms": round(r.rtt_ms, 3),
        "notify_bytes": note.size if note else "",
        "notify_wire_bytes": mqtt_packet_bytes(note.topic_bytes, note.size) if note else "",
        "notify_ms": round((note.received - t_send) * 1000, 3) if note and t_send else "",
    }


def summarize(samples: list[dict], formats: list[str]) -> list[dict]:
    out = []
    for op in dict.fromkeys(s["op"] for s in samples):
        json_wire = None
        for f in formats:
            rows = [s for s in samples if s["op"] == op and s["format"] == f]
            ok = [s for s in rows if s["rsc"] in (2000, 2001)]
            rtts = [s["rtt_ms"] for s in ok]
            notes = [s for s in ok if s["notify_ms"] != ""]
            wire = statistics.mean(s["req_wire_bytes"] + s["resp_wire_bytes"]
                                   + (s["notify_wire_bytes"] or 0) for s in ok)
            if f == "json":
                json_wire = wire
            out.append({
                "op": op, "format": f, "n": len(ok), "errors": len(rows) - len(ok),
                "req_bytes": round(statistics.mean(s["req_bytes"] for s in ok), 1),
                "resp_bytes": round(statistics.mean(s["resp_bytes"] for s in ok), 1),
                "notify_bytes": round(statistics.mean(s["notify_bytes"] for s in notes), 1) if notes else "",
                "exchange_wire_bytes": round(wire, 1),
                "wire_vs_json": round(wire / json_wire, 3) if json_wire else "",
                "rtt_median_ms": round(statistics.median(rtts), 2),
                "rtt_p95_ms": round(pct(rtts, 95), 2), "rtt_p99_ms": round(pct(rtts, 99), 2),
                "rtt_mean_ms": round(statistics.mean(rtts), 2),
                "notify_median_ms": round(statistics.median(s["notify_ms"] for s in notes), 2) if notes else "",
                "notify_p95_ms": round(pct([s["notify_ms"] for s in notes], 95), 2) if notes else "",
                "notifications_missing": len(ok) - len(notes) if op == "create_cin" else "",
            })
    return out


# --- report -----------------------------------------------------------------------------------


def cmd_report(args: argparse.Namespace) -> None:
    rows = []
    for d in map(Path, args.runs):
        if not (d / "summary.csv").exists():
            continue
        env = json.loads((d / "env.json").read_text())
        with (d / "summary.csv").open() as f:
            for r in csv.DictReader(f):
                rows.append({"run": d.name, "host": env.get("device_model") or env["host"], **r})
    if not rows:
        raise SystemExit("no runs with summary.csv given")
    e2e = [r for r in rows if "op" in r and r.get("op")]
    codec = [r for r in rows if "total_bytes" in r and r.get("total_bytes")]
    parts = []
    if codec:
        parts.append("## Codec runs\n\n" + markdown_table(codec, [
            ("run", "run"), ("host", "host"), ("format", "format"), ("size_vs_json", "size vs JSON"),
            ("median_encode_us", "encode µs"), ("median_decode_us", "decode µs")]))
    if e2e:
        parts.append("## End-to-end runs\n\n" + markdown_table(e2e, [
            ("run", "run"), ("host", "host"), ("op", "operation"), ("format", "format"), ("n", "n"),
            ("exchange_wire_bytes", "wire B/exchange"), ("wire_vs_json", "vs JSON"),
            ("rtt_median_ms", "RTT median ms"), ("rtt_p95_ms", "p95"), ("notify_median_ms", "notify ms")]))
    md = "\n\n".join(parts)
    print(md)
    if args.out:
        Path(args.out).write_text(md + "\n")
        print(f"\nwrote {args.out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(required=True)
    for name, fn in (("codec", cmd_codec), ("e2e", cmd_e2e)):
        p = sub.add_parser(name)
        p.add_argument("--formats", default=",".join(SERIALIZATIONS), help="comma list of json,cbor,pb")
        p.add_argument("--label", default=socket.gethostname().split(".")[0], help="name for this run")
        p.add_argument("--save", action=argparse.BooleanOptionalAction, default=True,
                       help="write the data points to results/ (default) or, with --no-save, only print the summary")
        p.set_defaults(func=fn)
        if name == "e2e":
            p.add_argument("--n", type=int, default=200, help="measured iterations per format")
            p.add_argument("--warmup", type=int, default=20, help="unmeasured iterations first")
            p.add_argument("--content", choices=sorted(CONTENT), default="reading",
                           help="cin content: 'reading' (small JSON object) or 'plain' ('23.5')")
    p = sub.add_parser("report")
    p.add_argument("runs", nargs="+", help="results/<run> directories")
    p.add_argument("--out", help="also write the merged table to this file")
    p.set_defaults(func=cmd_report)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
