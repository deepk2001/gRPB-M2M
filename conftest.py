"""Shared test fixtures: a private Mosquitto broker on a free port."""

from __future__ import annotations

import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

_CANDIDATES = ("/opt/homebrew/opt/mosquitto/sbin/mosquitto", "/usr/local/opt/mosquitto/sbin/mosquitto",
               "/usr/sbin/mosquitto")


@dataclass
class Broker:
    host: str
    port: int


def _find_mosquitto() -> str | None:
    return shutil.which("mosquitto") or next((p for p in _CANDIDATES if Path(p).exists()), None)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def broker(tmp_path_factory: pytest.TempPathFactory):
    exe = _find_mosquitto()
    if exe is None:
        pytest.skip("mosquitto not installed")
    port = _free_port()
    conf = tmp_path_factory.mktemp("mosquitto") / "test.conf"
    conf.write_text(f"listener {port} 127.0.0.1\nmax_topic_alias 1000\nallow_anonymous true\npersistence false\n")
    proc = subprocess.Popen([exe, "-c", str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 5
    while True:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            if time.monotonic() > deadline or proc.poll() is not None:
                proc.kill()
                pytest.fail("mosquitto did not start")
            time.sleep(0.05)
    yield Broker("127.0.0.1", port)
    proc.terminate()
    proc.wait(5)


@dataclass
class Cse:
    broker: Broker
    http: str           # e.g. http://127.0.0.1:54321
    cse_id: str = "id-in"
    cse_name: str = "cse-in"


@pytest.fixture(scope="session")
def acme(broker: Broker, tmp_path_factory: pytest.TempPathFactory):
    """The patched ACME CSE, on the test broker and a free HTTP port (config/acme.ini otherwise)."""
    import importlib.util
    import sys
    import urllib.request

    if importlib.util.find_spec("acmecse") is None:
        pytest.skip("acmecse not installed (make setup)")
    base = tmp_path_factory.mktemp("acme")
    http_port = _free_port()
    ini = (Path(__file__).parent / "config" / "acme.ini").read_text()
    ini = ini.replace("httpPort=8080", f"httpPort={http_port}").replace("port=1883", f"port={broker.port}")
    ini = ini.replace("logLevel=debug", "logLevel=warning")
    (base / "acme.ini").write_text(ini)
    log = open(base / "acme.out", "w")
    proc = subprocess.Popen([sys.executable, "-m", "acmecse", "--base-directory", str(base), "--headless"],
                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    http = f"http://127.0.0.1:{http_port}"
    deadline = time.monotonic() + 60
    while True:
        try:
            req = urllib.request.Request(f"{http}/cse-in", headers={
                "X-M2M-Origin": "CAdmin", "X-M2M-RI": "probe", "X-M2M-RVI": "5", "Accept": "application/json"})
            urllib.request.urlopen(req, timeout=1).close()
            break
        except OSError:
            if time.monotonic() > deadline or proc.poll() is not None:
                proc.kill()
                pytest.fail(f"ACME did not start; see {base / 'acme.out'}")
            time.sleep(0.25)
    time.sleep(1.0)  # HTTP comes up before the MQTT binding has subscribed
    yield Cse(broker, http)
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
