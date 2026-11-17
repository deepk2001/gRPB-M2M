"""The simulations, run small and fast against a private broker and the patched ACME."""

from __future__ import annotations

import csv
import os
import subprocess
import sys
from pathlib import Path

import pytest


def run_app(tmp_path: Path, env_extra: dict, *args: str) -> dict:
    env = {**os.environ, **env_extra}
    r = subprocess.run([sys.executable, "-m", "grpb_examples.sim", *args, "--results-dir", str(tmp_path),
                        "--label", "test", "--quiet"], env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    runs = sorted(p for p in tmp_path.iterdir() if p.is_dir() and not p.name.startswith("."))
    assert runs, r.stdout
    d = runs[-1]
    for name in ("samples.csv", "summary.csv", "summary.md", "env.json"):
        assert (d / name).exists(), name
    with (d / "summary.csv").open() as f:
        return next(csv.DictReader(f))


@pytest.fixture
def env(broker):
    return {"GRPB_BROKER_HOST": broker.host, "GRPB_BROKER_PORT": str(broker.port)}


@pytest.mark.parametrize("fmt", ["pb", "json"])
def test_farmnet(tmp_path, acme, fmt):
    env = {"GRPB_BROKER_HOST": acme.broker.host, "GRPB_BROKER_PORT": str(acme.broker.port), "GRPB_CSE_HTTP": acme.http}
    s = run_app(tmp_path, env, "farmnet", "--nodes", "3", "--interval", "0.5", "--duration", "2", "--warmup", "0.5",
                "--format", fmt)
    assert int(s["readings"]) >= 6 and s["errors"] == "0"
    assert s["interop_ok"] == "3"                      # written in pb/json, read back over HTTP as JSON
    assert int(s["notifications_missing"]) == 0
    assert float(s["device_link_B_per_reading"]) > 0


@pytest.mark.parametrize("transport", ["grpb", "grpc", "json"])
def test_pulse(tmp_path, env, transport):
    s = run_app(tmp_path, env, "pulse", "--transport", transport, "--nodes", "2", "--hz", "10", "--viewers", "2",
                "--duration", "2", "--warmup", "1")
    assert s["publish_errors"] == "0" and int(s["published"]) >= 30
    assert float(s["delivery_ratio"]) == 1.0


def test_safeswitch_crash_leaves_no_stale_commands(tmp_path, env):
    s = run_app(tmp_path, env, "safeswitch", "--transport", "grpb", "--scenario", "crash", "--actuators", "4",
                "--groups", "2", "--duration", "8", "--warmup", "1", "--fail-at", "2", "--outage", "2",
                "--period", "0.25", "--deadline", "1")
    assert int(s["outage_fast_fail"]) > 0 and s["outage_timed_out"] == "0"
    assert s["stale_executions"] == "0" and s["executed_but_reported_failed"] == "0"
    assert s["recovery_ms"] != ""
