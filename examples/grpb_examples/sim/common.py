"""Shared pieces of the simulations: command-line options, results folders, CPU/network sampling
and network emulation (tc netem).

Every run writes results/<time>-<app>-<label>/ (unless --no-save):
  samples.csv   one row per measured operation (raw data points)
  events.csv    what the runner did and when (failures injected, restarts, network changes)
  resources.csv CPU and memory of the simulator, broker, CSE and hub, once per second
  summary.csv   one row of headline numbers for this run (sweeps concatenate these)
  summary.md    the same as a readable table
  env.json      machine, versions, network profile and the exact arguments
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import shutil
import socket
import statistics
import subprocess
import sys
import threading
import time
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import psutil
except ImportError:  # optional: resource sampling is skipped without it
    psutil = None

# --- network emulation ----------------------------------------------------------------------

# One-way settings applied to the loopback interface. On a single Pi every hop (node -> broker,
# broker -> CSE or hub, and back) crosses loopback, so each hop gets this delay, loss and rate.
NETEM_PROFILES: dict[str, str | None] = {
    "lan": None,                                              # no emulation
    "wifi": "delay 2ms 1ms loss 0.5%",
    "4g": "delay 25ms 10ms loss 1%",
    "constrained": "delay 50ms 20ms loss 2% rate 1mbit",     # congested cellular / weak Wi-Fi
    "poor": "delay 100ms 30ms loss 3% rate 256kbit",          # edge of coverage
}


def _loopback() -> str:
    return "lo" if sys.platform.startswith("linux") else "lo0"


def _tc(*args: str) -> None:
    cmd = ["tc", *args] if os.geteuid() == 0 else ["sudo", "-n", "tc", *args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"network emulation failed: {' '.join(cmd)}\n{r.stderr.strip()}\n"
                         "netem needs Linux (e.g. the Pi) and passwordless sudo; use --netem lan elsewhere")


class Netem:
    """Context manager: apply a profile (or a raw netem spec) to loopback, always cleared on exit."""

    def __init__(self, profile: str) -> None:
        self.profile = profile
        self.spec = NETEM_PROFILES.get(profile, profile)
        if self.spec and not sys.platform.startswith("linux"):
            raise SystemExit(f"--netem {profile} needs Linux (tc netem); on this machine use --netem lan")
        if self.spec and not shutil.which("tc"):
            raise SystemExit("tc not found: sudo apt install iproute2")

    def set(self, spec: str | None) -> None:
        if spec:
            _tc("qdisc", "replace", "dev", _loopback(), "root", "netem", *spec.split())
        else:
            self.clear()

    def clear(self) -> None:
        if sys.platform.startswith("linux") and shutil.which("tc"):
            cmd = ["tc"] if os.geteuid() == 0 else ["sudo", "-n", "tc"]
            subprocess.run([*cmd, "qdisc", "del", "dev", _loopback(), "root"], capture_output=True)

    def __enter__(self) -> Netem:
        self.set(self.spec)
        return self

    def __exit__(self, *exc: Any) -> None:
        if self.spec:
            self.clear()


# --- resources ------------------------------------------------------------------------------


def find_pids() -> dict[str, int]:
    """PIDs of the broker and the CSE on this machine, if running."""
    found: dict[str, int] = {}
    if psutil is None:
        return found
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name, cmd = p.info["name"] or "", " ".join(p.info["cmdline"] or [])
        except (psutil.Error, TypeError):
            continue
        if "mosquitto" in name and "broker" not in found:
            found["broker"] = p.info["pid"]
        elif "acmecse" in cmd and "cse" not in found:
            found["cse"] = p.info["pid"]
    return found


class Sampler(threading.Thread):
    """Samples CPU % (of one core) and memory of named processes once per interval, plus system CPU."""

    def __init__(self, pids: dict[str, int], interval: float = 1.0) -> None:
        super().__init__(daemon=True)
        self.interval = interval
        self.rows: list[dict] = []
        self._stop_evt = threading.Event()
        self._procs: dict[str, Any] = {}
        self.available = psutil is not None
        if not self.available:
            return
        for name, pid in {"sim": os.getpid(), **pids}.items():
            try:
                proc = psutil.Process(pid)
                proc.cpu_percent(None)  # prime
                self._procs[name] = proc
            except psutil.Error:
                pass
        psutil.cpu_percent(None)

    def add(self, name: str, pid: int) -> None:
        if self.available:
            try:
                proc = psutil.Process(pid)
                proc.cpu_percent(None)
                self._procs[name] = proc
            except psutil.Error:
                pass

    def run(self) -> None:
        if not self.available:
            return
        t0 = time.monotonic()
        while not self._stop_evt.wait(self.interval):
            row: dict[str, Any] = {"t": round(time.monotonic() - t0, 2), "system_cpu": psutil.cpu_percent(None)}
            for name, proc in list(self._procs.items()):
                try:
                    with proc.oneshot():
                        cpu = proc.cpu_percent(None)
                        for child in proc.children(recursive=True):
                            try:
                                cpu += child.cpu_percent(None)
                            except psutil.Error:
                                pass
                        row[f"{name}_cpu"] = round(cpu, 1)
                        row[f"{name}_rss_mb"] = round(proc.memory_info().rss / 2**20, 1)
                except psutil.Error:
                    row[f"{name}_cpu"] = ""
            self.rows.append(row)

    def stop(self) -> None:
        self._stop_evt.set()
        if self.is_alive():
            self.join(2)

    def means(self, skip_s: float = 0.0) -> dict[str, float]:
        """Mean of every *_cpu / system_cpu column after the warm-up."""
        rows = [r for r in self.rows if r["t"] >= skip_s] or self.rows
        out: dict[str, float] = {}
        for key in dict.fromkeys(k for r in rows for k in r):
            if key.endswith("_cpu"):
                vals = [r[key] for r in rows if r.get(key) not in ("", None)]
                if vals:
                    out[f"{key}_mean"] = round(statistics.mean(vals), 1)
        return out


def loopback_bytes() -> int | None:
    """Bytes sent on loopback so far (every hop, TCP/IP headers included); None without psutil."""
    if psutil is None:
        return None
    nic = psutil.net_io_counters(pernic=True).get(_loopback())
    return nic.bytes_sent if nic else None


# --- statistics -----------------------------------------------------------------------------


def pct(values: list[float], q: float) -> float | str:
    if not values:
        return ""
    if len(values) == 1:
        return round(values[0], 3)
    s = sorted(values)
    k = (len(s) - 1) * q / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 3)


def mean(values: Iterable[float]) -> float | str:
    vals = list(values)
    return round(statistics.mean(vals), 3) if vals else ""


def now_us() -> int:
    return time.time_ns() // 1000


# --- command line and results ---------------------------------------------------------------


def add_args(ap: argparse.ArgumentParser, *, duration: float, warmup: float) -> None:
    g = ap.add_argument_group("run")
    g.add_argument("--duration", type=float, default=duration, help="measured seconds (after the warm-up)")
    g.add_argument("--warmup", type=float, default=warmup, help="seconds run first and not measured")
    g.add_argument("--netem", default="lan",
                   help=f"network profile on loopback: {', '.join(NETEM_PROFILES)}, or a raw netem spec (Linux)")
    g.add_argument("--label", default=socket.gethostname().split(".")[0], help="name for this run")
    g.add_argument("--save", action=argparse.BooleanOptionalAction, default=True,
                   help="write the data points to the results folder (default) or only print the summary")
    g.add_argument("--results-dir", default=os.getenv("GRPB_RESULTS", "results"), help="where runs are written")
    g.add_argument("--quiet", action="store_true", help="no progress lines")


class Run:
    """Collects one run's data points and writes them out at the end."""

    def __init__(self, app: str, args: argparse.Namespace) -> None:
        self.app, self.args = app, args
        self.samples: list[dict] = []
        self.events: list[dict] = []
        self._lock = threading.Lock()
        self.t0 = time.monotonic()           # start of the warm-up
        self.t_measure = self.t0 + args.warmup
        self.wall0 = time.time()

    def t(self) -> float:
        """Seconds since the start of the measured window (negative during the warm-up)."""
        return time.monotonic() - self.t_measure

    def measuring(self) -> bool:
        return time.monotonic() >= self.t_measure

    def add(self, row: dict) -> None:
        with self._lock:
            self.samples.append(row)

    def event(self, what: str, **detail: Any) -> None:
        row = {"t": round(self.t(), 3), "wall_us": now_us(), "event": what, **detail}
        with self._lock:
            self.events.append(row)
        self.log(f"[{row['t']:7.2f}s] {what} {' '.join(f'{k}={v}' for k, v in detail.items())}")

    def log(self, msg: str) -> None:
        if not self.args.quiet:
            sys.stdout.write(msg + "\n")
            sys.stdout.flush()

    def env(self, extra: dict | None = None) -> dict:
        import google.protobuf
        import grpc
        import paho.mqtt

        import grpb
        model = ""
        try:
            model = Path("/proc/device-tree/model").read_text().strip("\x00\n")
        except OSError:
            pass
        return {
            "app": self.app, "time": datetime.fromtimestamp(self.wall0).isoformat(timespec="seconds"),
            "host": socket.gethostname(), "platform": platform.platform(), "machine": platform.machine(),
            "device_model": model, "cpu_count": os.cpu_count(), "python": platform.python_version(),
            "grpb": grpb.__version__, "grpcio": grpc.__version__, "protobuf": google.protobuf.__version__,
            "paho_mqtt": paho.mqtt.__version__, "psutil": getattr(psutil, "__version__", None),
            "netem": {"profile": self.args.netem, "spec": NETEM_PROFILES.get(self.args.netem, self.args.netem),
                      "applies_to": "every loopback hop"},
            "args": {k: v for k, v in vars(self.args).items() if not callable(v)},
            **(extra or {}),
        }

    def finish(self, summary: dict, columns: list[tuple[str, str]], *, resources: list[dict] | None = None,
               env_extra: dict | None = None, notes: str = "") -> Path | None:
        md = (f"## {self.app}: {self.args.label}\n\n" + table([summary], columns)
              + (f"\n\n{notes}" if notes else ""))
        print("\n" + md, flush=True)
        if not self.args.save:
            print("\nnot saved (--no-save)")
            return None
        d = Path(self.args.results_dir) / f"{datetime.now():%Y%m%d-%H%M%S}-{self.app}-{self.args.label}"
        d.mkdir(parents=True, exist_ok=False)
        (d / "env.json").write_text(json.dumps(self.env(env_extra), indent=2, default=str))
        write_csv(d / "samples.csv", self.samples)
        write_csv(d / "events.csv", self.events)
        write_csv(d / "resources.csv", resources or [])
        write_csv(d / "summary.csv", [summary])
        (d / "summary.md").write_text(md + "\n")
        print(f"\nresults: {d}/", flush=True)
        return d


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def table(rows: list[dict], cols: list[tuple[str, str]]) -> str:
    def fmt(v: Any) -> str:
        return f"{v:.2f}" if isinstance(v, float) else str(v)
    head = "| " + " | ".join(t for _, t in cols) + " |"
    sep = "|" + "|".join("---:" if i else "---" for i in range(len(cols))) + "|"
    body = ["| " + " | ".join(fmt(r.get(k, "")) for k, _ in cols) + " |" for r in rows]
    return "\n".join([head, sep, *body])


def sleep_until(deadline: float, stop: threading.Event) -> bool:
    """Wait until a monotonic deadline; False if stopped first."""
    delay = deadline - time.monotonic()
    return not stop.wait(delay) if delay > 0 else not stop.is_set()
