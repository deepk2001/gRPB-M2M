"""M2: the patched ACME CSE speaks Protobuf over MQTT, alongside JSON and CBOR.

Each test runs a real device workflow against ACME through the test broker.
"""

from __future__ import annotations

import json
import threading
import urllib.request
import uuid

import paho.mqtt.client as mqtt
import pytest
from paho.mqtt.enums import CallbackAPIVersion

from grpb.onem2m import codec
from grpb.onem2m.client import SERIALIZATIONS, Notification, Onem2mClient

pytest.importorskip("cbor2")


def ae_pc(name: str, c: Onem2mClient) -> dict:
    return {"m2m:ae": {"rn": name, "api": "Ngrpb.test", "rr": True, "srv": ["5"],
                       "poa": [c.poa], "csz": [c.media_type]}}


def http_get(acme, path: str) -> dict:
    req = urllib.request.Request(f"{acme.http}/{path}", headers={
        "X-M2M-Origin": "CAdmin", "X-M2M-RI": uuid.uuid4().hex[:8], "X-M2M-RVI": "5", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)


@pytest.fixture
def device(acme, request):
    """Registered AE with a container, in the serialization given by the test parameter."""
    fmt = request.param
    name = f"t{fmt}{uuid.uuid4().hex[:6]}"
    notes: list[Notification] = []
    got = threading.Event()

    def on_notify(n: Notification) -> None:
        notes.append(n)
        got.set()

    c = Onem2mClient(f"C{name}", serialization=fmt, host=acme.broker.host, port=acme.broker.port,
                     on_notify=on_notify).connect()
    r = c.request(1, acme.cse_name, ty=2, pc=ae_pc(name, c))
    assert r.rsc == 2001, r.primitive
    assert c.request(1, f"{acme.cse_name}/{name}", ty=3, pc={"m2m:cnt": {"rn": "temp", "mni": 50}}).rsc == 2001
    yield c, name, notes, got
    c.request(4, f"{acme.cse_name}/{name}")
    c.close()


@pytest.mark.parametrize("device", SERIALIZATIONS, indirect=True)
def test_device_workflow(acme, device):
    c, name, notes, got = device
    cnt = f"{acme.cse_name}/{name}/temp"

    r = c.request(1, cnt, ty=23, pc={"m2m:sub": {"rn": "sub", "nu": [c.originator], "enc": {"net": [3]}}})
    assert r.rsc == 2001, r.primitive

    r = c.request(1, cnt, ty=4, pc={"m2m:cin": {"cnf": "text/plain:0", "con": "23.5"}})
    assert r.rsc == 2001 and r.pc["m2m:cin"]["con"] == "23.5"
    assert r.pc["m2m:cin"]["ct"].startswith("20")  # timestamps survive the round trip as strings

    assert got.wait(5), "no notification"
    sgn = notes[0].primitive["pc"]["m2m:sgn"]
    assert notes[0].primitive["op"] == 5
    assert sgn["nev"]["rep"]["m2m:cin"]["con"] == "23.5"

    r = c.request(2, f"{cnt}/la")
    assert r.rsc == 2000 and r.pc["m2m:cin"]["con"] == "23.5"

    r = c.request(3, cnt, pc={"m2m:cnt": {"lbl": ["room:lab"]}})
    assert r.rsc == 2004 and r.pc["m2m:cnt"]["lbl"] == ["room:lab"]

    r = c.request(2, f"{acme.cse_name}/{name}/nothing")
    assert r.rsc == 4004 and "m2m:dbg" in r.pc

    # Interop: an unmodified HTTP/JSON client reads what this device wrote.
    assert http_get(acme, f"{cnt}/la")["m2m:cin"]["con"] == "23.5"


@pytest.mark.parametrize("device", ["pb"], indirect=True)
def test_protobuf_on_the_wire(acme, device):
    """Responses and notifications really are Protobuf on .../pb topics, not JSON."""
    c, name, notes, got = device
    seen: list[tuple[str, bytes]] = []
    spy = mqtt.Client(CallbackAPIVersion.VERSION2)
    spy.on_message = lambda cl, ud, m: seen.append((m.topic, m.payload))
    spy.connect(acme.broker.host, acme.broker.port)
    spy.subscribe("/oneM2M/#")
    spy.loop_start()
    try:
        threading.Event().wait(0.3)
        cnt = f"{acme.cse_name}/{name}/temp"
        c.request(1, cnt, ty=23, pc={"m2m:sub": {"rn": "sub", "nu": [c.originator], "enc": {"net": [3]}}})
        c.request(1, cnt, ty=4, pc={"m2m:cin": {"con": "42"}})
        assert got.wait(5)
        threading.Event().wait(0.3)
    finally:
        spy.loop_stop()
        spy.disconnect()
    mine = [(t, p) for t, p in seen if c.originator in t]
    assert mine and all(t.endswith("/pb") for t, _ in mine)
    for t, p in mine:
        assert not p.lstrip().startswith(b"{"), f"JSON on {t}"
        codec.decode(p)  # parses as onem2m.Primitive
    assert any(t.startswith(f"/oneM2M/req/{acme.cse_id}/{c.originator}/") for t, _ in mine), "no pb notification"


def test_cross_format_notification(acme):
    """A JSON AE subscribed to a container that a Protobuf AE writes gets JSON notifications."""
    got = threading.Event()
    notes: list[Notification] = []
    name_pb, name_js = f"xpb{uuid.uuid4().hex[:6]}", f"xjs{uuid.uuid4().hex[:6]}"
    with Onem2mClient(f"C{name_pb}", serialization="pb", host=acme.broker.host, port=acme.broker.port) as w, \
         Onem2mClient(f"C{name_js}", serialization="json", host=acme.broker.host, port=acme.broker.port,
                      on_notify=lambda n: (notes.append(n), got.set())) as r:
        assert w.request(1, acme.cse_name, ty=2, pc=ae_pc(name_pb, w)).rsc == 2001
        assert r.request(1, acme.cse_name, ty=2, pc=ae_pc(name_js, r)).rsc == 2001
        cnt = f"{acme.cse_name}/{name_pb}/temp"
        assert w.request(1, f"{acme.cse_name}/{name_pb}", ty=3, pc={"m2m:cnt": {"rn": "temp"}}).rsc == 2001
        assert r.request(1, cnt, ty=23, pc={"m2m:sub": {"rn": "s", "nu": [r.originator],
                                                        "enc": {"net": [3]}}}).rsc == 2001
        assert w.request(1, cnt, ty=4, pc={"m2m:cin": {"con": "from-protobuf"}}).rsc == 2001
        assert got.wait(5)
        assert notes[0].primitive["pc"]["m2m:sgn"]["nev"]["rep"]["m2m:cin"]["con"] == "from-protobuf"
        w.request(4, f"{acme.cse_name}/{name_pb}")
        r.request(4, f"{acme.cse_name}/{name_js}")


def test_garbage_protobuf_does_not_break_the_cse(acme):
    raw = mqtt.Client(CallbackAPIVersion.VERSION2)
    raw.connect(acme.broker.host, acme.broker.port)
    raw.loop_start()
    raw.publish(f"/oneM2M/req/Cjunk/{acme.cse_id}/pb", b"\xff\xff\xff\x01", qos=1).wait_for_publish(2)
    raw.loop_stop()
    raw.disconnect()
    with Onem2mClient(f"Cafter{uuid.uuid4().hex[:6]}", serialization="pb", host=acme.broker.host,
                      port=acme.broker.port) as c:
        assert c.request(2, acme.cse_name).rsc == 2000
