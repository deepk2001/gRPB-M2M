"""Charts from simulation results, ready for slides.

    python -m grpb_examples.sim plot results/<sweep-or-run> [more dirs...] [--out charts/]

Reads combined.csv (sweeps) or summary.csv (single runs), averages repeats, and writes PNGs per app
into <first dir>/charts/ (or --out). Needs matplotlib: pip install "grpb-examples[plot]".
"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

# Per comparison: series column -> value -> (colour, label). gRPB-M2M is always the blue one.
STYLE = {
    "format": {"json": ("#8a8f98", "JSON"), "cbor": ("#e08a2c", "CBOR"), "pb": ("#2563eb", "Protobuf (gRPB-M2M)")},
    "transport": {"json": ("#e08a2c", "JSON over MQTT"), "grpc": ("#8a8f98", "gRPC (HTTP/2)"),
                  "grpb": ("#2563eb", "gRPB-M2M (MQTT)")},
}


def color(col: str, s: str) -> str | None:
    return STYLE.get(col, {}).get(s, (None, s))[0]


def series_label(col: str, s: str) -> str:
    return STYLE.get(col, {}).get(s, (None, s))[1]


def order(col: str, values: set) -> list:
    known = list(STYLE.get(col, {}))
    return sorted(values, key=lambda v: known.index(v) if v in known else 99)


def num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load(dirs: list[Path]) -> list[dict]:
    rows = []
    for d in dirs:
        for name in ("combined.csv", "summary.csv"):
            f = d / name
            if f.exists():
                with f.open() as fh:
                    rows += [r for r in csv.DictReader(fh) if r.get("app") and not r.get("error")]
                break
    return rows


def agg(rows: list[dict], keys: tuple[str, ...], y: str) -> dict[tuple, float]:
    groups: dict[tuple, list[float]] = defaultdict(list)
    for r in rows:
        v = num(r.get(y))
        if v is not None:
            groups[tuple(r.get(k, "") for k in keys)].append(v)
    return {k: statistics.mean(v) for k, v in groups.items()}


def line(plt: Any, rows: list[dict], x: str, y: str, series: str, title: str, ylabel: str, xlabel: str,
         out: Path, logy: bool = False) -> None:
    facets = sorted({r.get("netem", "") for r in rows})
    fig, axes = plt.subplots(1, len(facets), figsize=(5.2 * len(facets), 3.8), squeeze=False, sharey=True)
    for ax, facet in zip(axes[0], facets):
        data = agg([r for r in rows if r.get("netem", "") == facet], (series, x), y)
        for s in order(series, {k[0] for k in data}):
            pts = sorted((num(k[1]), v) for k, v in data.items() if k[0] == s and num(k[1]) is not None)
            if pts:
                ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", lw=2, color=color(series, s),
                        label=series_label(series, s))
        ax.set_title(f"network: {facet}" if len(facets) > 1 else "", fontsize=10)
        ax.set_xlabel(xlabel)
        ax.grid(alpha=0.3)
        if logy:
            ax.set_yscale("log")
    axes[0][0].set_ylabel(ylabel)
    axes[0][0].legend(frameon=False)
    fig.suptitle(title, fontsize=12, fontweight="bold", x=0.02, ha="left")
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def bars(plt: Any, rows: list[dict], x: str, series: str, y: str, title: str, ylabel: str, out: Path,
         ratio_to: str | None = None, missing_label: str = "") -> None:
    data = agg(rows, (x, series), y)
    raw = {(r.get(x, ""), r.get(series, "")): r.get(y) for r in rows}
    xs = sorted({k[0] for k in raw})
    ss = order(series, {k[1] for k in raw})
    fig, ax = plt.subplots(figsize=(max(5.0, 1.6 * len(xs) * len(ss) / 2 + 2), 3.8))
    w = 0.8 / max(1, len(ss))
    missing = []
    for j, s in enumerate(ss):
        for i, xv in enumerate(xs):
            v = data.get((xv, s))
            pos = i + (j - (len(ss) - 1) / 2) * w
            if v is None:
                if missing_label and (xv, s) in raw:
                    missing.append((pos, s))
                continue
            ax.bar(pos, v, w * 0.92, color=color(series, s), label=series_label(series, s) if i == 0 else None)
            note = f"{v:,.0f}" if v >= 10 else f"{v:.2g}"
            if ratio_to and data.get((xv, ratio_to)) and s != ratio_to:
                note += f"\n{v / data[(xv, ratio_to)]:.2f}×"
            ax.text(pos, v, note, ha="center", va="bottom", fontsize=8)
    ax.set_xticks(range(len(xs)), [str(v) for v in xs])
    ax.set_xlim(-0.5, len(xs) - 0.5)
    ax.margins(y=0.18)
    top = ax.get_ylim()[1] or 1.0
    for pos, s in missing:
        ax.bar(pos, top * 0.12, w * 0.92, color="none", edgecolor=color(series, s), hatch="///", lw=1,
               label=series_label(series, s))
        ax.text(pos, top * 0.13, missing_label, ha="center", va="bottom", fontsize=8)
    ax.set_ylim(0, top * 1.12)   # room for the legend above the tallest bar
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=12, fontweight="bold", loc="left")
    ax.grid(axis="y", alpha=0.3)
    handles, labels = ax.get_legend_handles_labels()
    seen = dict(zip(labels, handles))   # one entry per series, even when some of its bars are "missing"
    ax.legend(seen.values(), seen.keys(), frameon=False, ncols=len(seen), loc="upper center",
              bbox_to_anchor=(0.5, 1.0))
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def main(args: argparse.Namespace) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        raise SystemExit('matplotlib is needed for charts: pip install "grpb-examples[plot]"')
    dirs = [Path(d) for d in args.dirs]
    rows = load(dirs)
    if not rows:
        raise SystemExit("no summary.csv / combined.csv with results found")
    out = Path(args.out) if args.out else dirs[0] / "charts"
    out.mkdir(parents=True, exist_ok=True)
    made = []
    by_app: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["app"] == "pulse":   # everything the infrastructure spends: hub (if any) + broker
            parts = [num(r.get("hub_cpu_mean")), num(r.get("broker_cpu_mean"))]
            r["infra_cpu"] = sum(v for v in parts if v is not None)
        by_app[r["app"]].append(r)

    if rows := by_app.get("farmnet"):
        bars(plt, rows, "netem", "format", "device_link_B_per_reading",
             "Bytes on the device link per reading", "bytes (request + response)", out / "farmnet_bytes.png",
             ratio_to="json")
        line(plt, rows, "nodes", "fleet_MB_per_day", "format", "Fleet data volume per day", "MB / day",
             "sensors", out / "farmnet_fleet_mb_day.png")
        line(plt, rows, "nodes", "rtt_p95_ms", "format", "Request round trip, 95th percentile", "ms",
             "sensors", out / "farmnet_rtt_p95.png")
        line(plt, rows, "nodes", "cse_cpu_mean", "format", "CSE CPU load", "% of one core", "sensors",
             out / "farmnet_cse_cpu.png")
        made += ["farmnet_bytes", "farmnet_fleet_mb_day", "farmnet_rtt_p95", "farmnet_cse_cpu"]
    if rows := by_app.get("pulse"):
        line(plt, rows, "hz", "delay_p95_ms", "transport", "Sensor-to-viewer delay, 95th percentile", "ms",
             "samples per second per node", out / "pulse_delay_p95.png")
        line(plt, rows, "offered_per_s", "achieved_per_s", "transport", "Throughput: achieved vs offered",
             "samples / s achieved", "samples / s offered", out / "pulse_throughput.png")
        line(plt, rows, "hz", "infra_cpu", "transport", "Infrastructure CPU: hub + broker", "% of one core",
             "samples per second per node", out / "pulse_infra_cpu.png")
        line(plt, rows, "hz", "sim_cpu_mean", "transport", "Device-side CPU: all sensors + viewers",
             "% of one core", "samples per second per node", out / "pulse_device_cpu.png")
        links = [{"transport": r["transport"], "link": link, "B": r.get(col, "")}
                 for r in rows for link, col in (("sensor uplink", "device_link_B_per_sample"),
                                                 ("viewer downlink", "viewer_B_per_sample"))]
        bars(plt, links, "link", "transport", "B", "MQTT bytes per sample on each device's link", "bytes",
             out / "pulse_bytes.png", ratio_to="json", missing_label="n/a")
        made += ["pulse_delay_p95", "pulse_throughput", "pulse_infra_cpu", "pulse_device_cpu", "pulse_bytes"]
    if rows := by_app.get("safeswitch"):
        failing = [r for r in rows if r.get("scenario") != "none"]
        bars(plt, rows, "scenario", "transport", "stale_executions",
             "Stale commands executed after the controller gave up", "commands", out / "safeswitch_stale.png")
        bars(plt, failing, "scenario", "transport", "fails_fast_after_ms",
             "Time until calls to a dead actuator fail fast", "ms", out / "safeswitch_fail_fast.png",
             missing_label="never")
        bars(plt, failing, "scenario", "transport", "controller_blocked_s",
             "Controller time stuck waiting on dead actuators", "seconds", out / "safeswitch_blocked.png")
        bars(plt, failing, "scenario", "transport", "recovery_ms",
             "Recovery: first success after the actuator is back", "ms", out / "safeswitch_recovery.png")
        made += ["safeswitch_stale", "safeswitch_fail_fast", "safeswitch_blocked", "safeswitch_recovery"]
    print(f"charts in {out}/: {', '.join(m + '.png' for m in made)}")


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("plot", help="PNG charts from sweep or run folders", description=__doc__,
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("dirs", nargs="+")
    p.add_argument("--out", help="folder for the PNGs (default: <first dir>/charts)")
    p.set_defaults(func=main)
