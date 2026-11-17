"""Run one app over a grid of settings and collect every run's headline numbers in one table.

    python -m grpb_examples.sim sweep farmnet --vary format=json,cbor,pb --vary nodes=10,50,200 \\
        --label pi -- --duration 60 --interval 5

Writes results/<time>-sweep-<app>-<label>/ with runs/ (one full run folder per combination),
combined.csv (one row per run, with the varied settings), combined.md and sweep.json. Each run is a
separate process, so one failure doesn't stop the sweep. Charts: python -m grpb_examples.sim plot <dir>.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from . import common


def main(args: argparse.Namespace) -> None:
    vary: list[tuple[str, list[str]]] = []
    for v in args.vary:
        key, _, values = v.partition("=")
        if not values:
            raise SystemExit(f"--vary expects key=v1,v2 (got {v!r})")
        vary.append((key.strip().lstrip("-"), [x.strip() for x in values.split(",") if x.strip()]))
    fixed = list(args.fixed)
    combos = list(itertools.product(*(vals for _, vals in vary))) or [()]
    d = Path(args.results_dir) / f"{datetime.now():%Y%m%d-%H%M%S}-sweep-{args.app}-{args.label}"
    (d / "runs").mkdir(parents=True)
    (d / "sweep.json").write_text(json.dumps({
        "app": args.app, "vary": dict(vary), "fixed": fixed, "repeat": args.repeat, "host": socket.gethostname(),
        "started": datetime.now().isoformat(timespec="seconds")}, indent=2))
    total = len(combos) * args.repeat
    print(f"sweep {args.app}: {len(combos)} combinations x {args.repeat} repeat(s) = {total} runs -> {d}", flush=True)

    rows: list[dict] = []
    n = 0
    for rep in range(args.repeat):        # repeats outermost: slow drift hits every combination alike
        for combo in combos:
            n += 1
            settings = dict(zip((k for k, _ in vary), combo))
            label = "-".join(f"{k}{v}" for k, v in settings.items()).replace(":", "_").replace(" ", "") or "run"
            label = f"{label}-r{rep}"
            cmd = [sys.executable, "-m", "grpb_examples.sim", args.app, *fixed,
                   *(x for k, v in settings.items() for x in (f"--{k}", v)),
                   "--label", label, "--results-dir", str(d / "runs"), "--quiet"]
            print(f"[{n}/{total}] {args.app} {' '.join(f'{k}={v}' for k, v in settings.items())} (repeat {rep})",
                  flush=True)
            before = set((d / "runs").iterdir())
            t0 = time.monotonic()
            r = subprocess.run(cmd, env=os.environ.copy(), capture_output=True, text=True)
            new = sorted(set((d / "runs").iterdir()) - before)
            row = {"run": new[-1].name if new else "", "repeat": rep, **{f"set_{k}": v for k, v in settings.items()},
                   "seconds": round(time.monotonic() - t0, 1)}
            if r.returncode != 0 or not new or not (new[-1] / "summary.csv").exists():
                row["error"] = (r.stderr.strip().splitlines() or ["failed"])[-1][:200]
                print(f"    FAILED: {row['error']}", flush=True)
            else:
                with (new[-1] / "summary.csv").open() as f:
                    row.update(next(csv.DictReader(f)))
            rows.append(row)
            common.write_csv(d / "combined.csv", rows)   # rewrite as we go: a partial sweep is still usable
            time.sleep(args.pause)

    cols = [(k, k) for k in rows[0] if k.startswith("set_")] if rows else []
    extra = [c for c in (args.show or SHOW[args.app]).split(",") if c]
    md = f"## Sweep: {args.app} ({args.label})\n\n" + common.table(rows, [*cols, *((c, c) for c in extra), ("error", "error")])
    (d / "combined.md").write_text(md + "\n")
    print("\n" + md + f"\n\nsweep: {d}/", flush=True)


SHOW = {
    "farmnet": "achieved_per_s,errors,device_link_B_per_reading,fleet_MB_per_day,rtt_p50_ms,rtt_p95_ms,"
               "interop_ok,cse_cpu_mean",
    "pulse": "achieved_per_s,publish_errors,delivery_ratio,delay_p50_ms,delay_p95_ms,delay_p99_ms,"
             "device_link_B_per_sample,hub_cpu_mean",
    "safeswitch": "latency_p50_ms,outage_fast_fail,outage_timed_out,controller_blocked_s,fails_fast_after_ms,"
                  "recovery_ms,stale_executions,stale_max_late_s,executed_but_reported_failed",
}


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("sweep", help="run an app over a grid of settings", description=__doc__,
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("app", choices=("farmnet", "pulse", "safeswitch"))
    p.add_argument("--vary", action="append", default=[], help="key=v1,v2,... (repeatable)")
    p.add_argument("--repeat", type=int, default=1, help="run every combination this many times")
    p.add_argument("--pause", type=float, default=2.0, help="seconds between runs")
    p.add_argument("--label", default=socket.gethostname().split(".")[0])
    p.add_argument("--results-dir", default=os.getenv("GRPB_RESULTS", "results"))
    p.add_argument("--show", default="", help="comma list of summary columns to print in the table")
    p.set_defaults(func=main, fixed=[])   # options after "--" go to every run (split off in __main__)
