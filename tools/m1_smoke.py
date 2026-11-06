"""Milestone M1 smoke test: plain JSON over MQTT against an unmodified ACME.

Run it from the laptop or from a Pi. It proves that the broker, the CSE's MQTT binding and
the device's network setup all work before any Protobuf code is involved:

  1. CREATE an AE        (JSON over MQTT)
  2. CREATE a container  (JSON over MQTT)
  3. CREATE a reading    (JSON over MQTT)
  4. READ it back over HTTP/JSON (the interoperability path the dashboard will use)
  5. DELETE the AE       (JSON over MQTT), so reruns start clean

Usage:  python tools/m1_smoke.py            # everything on localhost
        GRPB_BROKER_HOST=192.168.1.20 python tools/m1_smoke.py   # from a Pi
"""

from __future__ import annotations

import json
import sys
import threading
import urllib.request
import uuid

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from grpb.config import Config

# oneM2M operation codes and resource types (TS-0004)
OP_CREATE, OP_RETRIEVE, OP_DELETE = 1, 2, 4
TY_AE, TY_CNT, TY_CIN = 2, 3, 4


class JsonMqttClient:
    """Minimal oneM2M request/response over MQTT (TS-0010), matched by rqi."""

    def __init__(self, cfg: Config, originator: str) -> None:
        self.cfg, self.originator = cfg, originator
        self.req_topic = f"/oneM2M/req/{originator}/{cfg.cse_id}/json"
        self.resp_topic = f"/oneM2M/resp/{originator}/{cfg.cse_id}/json"
        self._pending: dict[str, tuple[threading.Event, list[dict]]] = {}
        self._subscribed = threading.Event()
        self._client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=originator)
        self._client.on_connect = self._on_connect
        self._client.on_subscribe = lambda *_: self._subscribed.set()
        self._client.on_message = self._on_message

    def __enter__(self) -> JsonMqttClient:
        self._client.connect(self.cfg.broker_host, self.cfg.broker_port)
        self._client.loop_start()
        if not self._subscribed.wait(5):
            raise TimeoutError(f"no MQTT connection to {self.cfg.broker_host}:{self.cfg.broker_port}")
        return self

    def __exit__(self, *exc: object) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        client.subscribe(self.resp_topic, qos=1)

    def _on_message(self, client, userdata, msg) -> None:
        body = json.loads(msg.payload)
        waiter = self._pending.get(body.get("rqi", ""))
        if waiter:
            waiter[1].append(body)
            waiter[0].set()

    def request(self, op: int, to: str, ty: int | None = None, pc: dict | None = None) -> dict:
        rqi = uuid.uuid4().hex[:12]
        req: dict = {"op": op, "to": to, "fr": self.originator, "rqi": rqi, "rvi": "5"}
        if ty is not None:
            req["ty"] = ty
        if pc is not None:
            req["pc"] = pc
        done, box = threading.Event(), []
        self._pending[rqi] = (done, box)
        try:
            self._client.publish(self.req_topic, json.dumps(req), qos=1)
            if not done.wait(self.cfg.request_timeout):
                raise TimeoutError(f"no response to rqi={rqi}; is ACME running with [mqtt] enable=true?")
            return box[0]
        finally:
            del self._pending[rqi]


def expect(resp: dict, rsc: int, what: str) -> dict:
    ok = resp.get("rsc") == rsc
    print(f"  {'OK ' if ok else 'FAIL'} {what}: rsc={resp.get('rsc')}")
    if not ok:
        print(json.dumps(resp, indent=2))
        sys.exit(1)
    return resp


def http_get(cfg: Config, path: str, originator: str) -> dict:
    req = urllib.request.Request(f"{cfg.cse_http}/{path}", headers={
        "X-M2M-Origin": originator,
        "X-M2M-RI": uuid.uuid4().hex[:12],
        "X-M2M-RVI": "5",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=cfg.request_timeout) as r:
        return json.load(r)


def main() -> None:
    cfg = Config.from_env()
    originator = f"Cgrpb-smoke-{uuid.uuid4().hex[:6]}"
    ae, cnt = "grpbSmoke", "temperature"
    print(f"broker {cfg.broker_host}:{cfg.broker_port}  CSE {cfg.cse_id}/{cfg.cse_name}  as {originator}")

    with JsonMqttClient(cfg, originator) as c:
        expect(c.request(OP_CREATE, cfg.cse_name, TY_AE,
                         {"m2m:ae": {"rn": ae, "api": "Ngrpb.smoke", "rr": False, "srv": ["5"]}}),
               2001, "create AE")
        try:
            expect(c.request(OP_CREATE, f"{cfg.cse_name}/{ae}", TY_CNT, {"m2m:cnt": {"rn": cnt}}),
                   2001, "create container")
            expect(c.request(OP_CREATE, f"{cfg.cse_name}/{ae}/{cnt}", TY_CIN,
                             {"m2m:cin": {"cnf": "application/json:0", "con": json.dumps({"celsius": 23.5})}}),
                   2001, "create contentInstance")

            latest = http_get(cfg, f"{cfg.cse_name}/{ae}/{cnt}/la", originator)
            con = json.loads(latest["m2m:cin"]["con"])
            ok = con == {"celsius": 23.5}
            print(f"  {'OK ' if ok else 'FAIL'} read back over HTTP/JSON: {con}")
            if not ok:
                sys.exit(1)
        finally:
            expect(c.request(OP_DELETE, f"{cfg.cse_name}/{ae}"), 2002, "delete AE")

    print("M1 smoke test passed")


if __name__ == "__main__":
    main()
