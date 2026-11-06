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
    conf.write_text(f"listener {port} 127.0.0.1\nallow_anonymous true\npersistence false\n")
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
