"""A oneM2M AE client over MQTT (TS-0010) that speaks JSON, CBOR or Protobuf.

    with Onem2mClient("Csensor1", serialization="pb", host="broker.local") as c:
        c.request(1, "cse-in", ty=2, pc={"m2m:ae": {"rn": "sensor1", "api": "Nsensor", "rr": True,
                                                  "srv": ["5"], "poa": [c.poa], "csz": [c.media_type]}})
        r = c.request(1, "cse-in/sensor1/temp", ty=4, pc={"m2m:cin": {"con": "23.5"}})
        r.rsc, r.pc, r.req_bytes, r.resp_bytes, r.rtt_ms

Notifications the CSE sends to this AE arrive in the AE's serialization; they are answered with
2000 OK automatically and passed to `on_notify`. Every request and notification records its
size on the wire and timing, so the same client drives the benchmarks.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .._endpoint import Endpoint
from . import codec

SERIALIZATIONS = ("json", "cbor", "pb")
MEDIA_TYPES = {"json": "application/json", "cbor": "application/cbor", "pb": codec.MEDIA_TYPE}


def _codec(serialization: str) -> tuple[Callable[[dict], bytes], Callable[[bytes], dict]]:
    if serialization == "json":
        return (lambda d: json.dumps(d, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
                lambda b: json.loads(b))
    if serialization == "cbor":
        import cbor2  # optional dependency: pip install "grpb-m2m[cbor]"
        return cbor2.dumps, cbor2.loads
    if serialization == "pb":
        return codec.encode, codec.decode
    raise ValueError(f"serialization must be one of {SERIALIZATIONS}, got {serialization!r}")


@dataclass
class Response:
    primitive: dict
    req_bytes: int         # MQTT payload size of the request
    resp_bytes: int        # MQTT payload size of the response
    req_topic_bytes: int
    resp_topic_bytes: int
    rtt_ms: float          # publish -> response received

    @property
    def rsc(self) -> int | None:
        return self.primitive.get("rsc")

    @property
    def pc(self) -> Any:
        return self.primitive.get("pc")


@dataclass
class Notification:
    primitive: dict
    size: int              # MQTT payload size
    topic_bytes: int
    received: float = field(default_factory=time.perf_counter)  # perf_counter() timestamp


class Onem2mError(Exception):
    pass


class Onem2mClient:
    """One AE (originator) talking to one CSE through an MQTT broker."""

    def __init__(self, originator: str, *, serialization: str = "pb", host: str = "127.0.0.1",
                 port: int = 1883, cse_id: str = "id-in", topic_prefix: str = "", timeout: float = 10.0,
                 on_notify: Callable[[Notification], None] | None = None, topic_aliases: bool = True) -> None:
        if "/" in originator:
            raise ValueError("originator must not contain '/' (encode SP-relative IDs first)")
        self.originator, self.serialization, self.cse_id = originator, serialization, cse_id
        self.host, self.port, self.timeout = host, port, timeout
        self.media_type = MEDIA_TYPES[serialization]
        self._encode, self._decode = _codec(serialization)
        base = f"{topic_prefix}/oneM2M"
        self._req = f"{base}/req/{originator}/{cse_id}/{serialization}"
        self._resp = f"{base}/resp/{originator}/{cse_id}/{serialization}"
        self._notify_req = f"{base}/req/{cse_id}/{originator}/{serialization}"
        self._notify_resp = f"{base}/resp/{cse_id}/{originator}/{serialization}"
        self._on_notify = on_notify
        self._pending: dict[str, tuple[threading.Event, list]] = {}
        self._lock = threading.Lock()
        self._ep = Endpoint(f"{originator}-{uuid.uuid4().hex[:6]}", host, port,
                            subscriptions=[self._resp, self._notify_req], on_message=self._on_message,
                            topic_aliases=topic_aliases)

    @property
    def poa(self) -> str:
        """Point of access to register, so the CSE sends notifications here over MQTT."""
        return f"mqtt://{self.host}:{self.port}"

    def connect(self, timeout: float = 10.0) -> Onem2mClient:
        self._ep.start()
        if not self._ep.ready.wait(timeout):
            raise Onem2mError(f"cannot reach MQTT broker {self.host}:{self.port}")
        return self

    def close(self) -> None:
        self._ep.close()

    def __enter__(self) -> Onem2mClient:
        return self.connect()

    def __exit__(self, *exc: object) -> None:
        self.close()

    def stats(self) -> dict[str, int]:
        """MQTT messages and bytes this client has sent and received (see Endpoint.stats)."""
        return self._ep.stats()

    def request(self, op: int, to: str, *, ty: int | None = None, pc: Any = None,
                timeout: float | None = None, **params: Any) -> Response:
        """Send one request primitive and wait for its response (matched by rqi)."""
        rqi = uuid.uuid4().hex[:12]
        prim: dict = {"op": op, "to": to, "fr": self.originator, "rqi": rqi, "rvi": "5", **params}
        if ty is not None:
            prim["ty"] = ty
        if pc is not None:
            prim["pc"] = pc
        payload = self._encode(prim)
        waiter: tuple[threading.Event, list] = (threading.Event(), [])
        with self._lock:
            self._pending[rqi] = waiter
        try:
            t0 = time.perf_counter()
            self._ep.publish(self._req, payload)
            if not waiter[0].wait(timeout or self.timeout):
                raise Onem2mError(f"no response to rqi={rqi} within {timeout or self.timeout}s "
                                  f"(is the CSE running with '{self.serialization}' enabled?)")
            rtt = (time.perf_counter() - t0) * 1000
        finally:
            with self._lock:
                self._pending.pop(rqi, None)
        resp, resp_size = waiter[1]
        return Response(resp, len(payload), resp_size, len(self._req), len(self._resp), rtt)

    def _on_message(self, topic: str, payload: bytes) -> None:
        received = time.perf_counter()
        prim = self._decode(payload)
        if topic == self._notify_req:
            # Answer first so the CSE isn't kept waiting, then hand the notification over.
            ok = {"rsc": 2000, "rqi": prim.get("rqi"), "rvi": "5", "fr": self.originator, "to": prim.get("fr")}
            self._ep.publish(self._notify_resp, self._encode(ok))
            if self._on_notify:
                self._on_notify(Notification(prim, len(payload), len(topic), received))
            return
        with self._lock:
            waiter = self._pending.get(prim.get("rqi"))
        if waiter:
            waiter[1].extend((prim, len(payload)))
            waiter[0].set()
