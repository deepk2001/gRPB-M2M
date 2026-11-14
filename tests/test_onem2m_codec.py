"""The Protobuf codec must reproduce every primitive exactly, modelled or not."""

from __future__ import annotations

import json

import pytest

from grpb.onem2m import codec, onem2m_pb2

from onem2m_samples import ALL

EDGE_CASES = {
    "empty": {},
    "unknown primitive params": {"op": 2, "to": "x", "rt": {"rtv": 1}, "fc": {"fu": 1, "ty": [4]}, "rcn": 4},
    "unknown pc wrapper": {"rsc": 2000, "pc": {"m2m:uril": ["/id-in/a", "/id-in/b"]}},
    "two pc wrappers": {"pc": {"m2m:cin": {"con": "a"}, "m2m:cnt": {"rn": "b"}}},
    "empty pc": {"op": 1, "pc": {}},
    "non-string con": {"pc": {"m2m:cin": {"con": {"c": 23.5, "ok": True}}}},
    "numeric con": {"pc": {"m2m:cin": {"con": 23.5}}},
    "empty list": {"pc": {"m2m:cnt": {"lbl": []}}},
    "zero and false values": {"rsc": 0, "pc": {"m2m:ae": {"rr": False, "rn": "", "ty": 0}}},
    "timestamp without fraction": {"pc": {"m2m:cnt": {"et": "20311109T214309"}}},
    "invalid timestamp": {"ot": "20261332T250000,000000"},
    "big and negative ints": {"rsc": 2**40, "ty": -1, "pc": {"m2m:cnt": {"mni": 2**33}}},
    "bool where int expected": {"ty": True},
    "unknown resource attribute": {"pc": {"m2m:cin": {"con": "x", "or": "http://onto", "at": ["/remote"]}}},
    "rich enc": {"pc": {"m2m:sub": {"nu": ["C"], "enc": {"net": [1, 3], "chty": [4]}}}},
    "enc with empty net": {"pc": {"m2m:sub": {"enc": {"net": []}}}},
    "verification request": {"op": 5, "pc": {"m2m:sgn": {"vrq": True, "sur": "/id-in/sub1", "cr": "Cae"}}},
    "sgn with unmodelled nev": {"pc": {"m2m:sgn": {"nev": {"net": 3, "rep": {"m2m:grp": {"mid": []}}}}}},
    "sgn with empty nev": {"pc": {"m2m:sgn": {"nev": {}}}},
    "sgn nev without rep": {"pc": {"m2m:sgn": {"nev": {"net": 4}, "sur": "/x"}}},
    "sgn deletion notice": {"pc": {"m2m:sgn": {"sud": True, "sur": "/x"}}},
    "unicode": {"pc": {"m2m:cin": {"con": "température 23,5 °C ✓", "lbl": ["ort:Zürich"]}}},
    "pre-1970 timestamp": {"pc": {"m2m:cnt": {"ct": "19691231T235959,999999"}}},
}


@pytest.mark.parametrize("name", sorted(ALL) + sorted(EDGE_CASES))
def test_round_trip(name):
    original = ALL.get(name) or EDGE_CASES[name]
    data = codec.encode(original)
    assert isinstance(data, bytes)
    assert codec.decode(data) == original


def test_modelled_samples_need_no_json_fallback():
    """The captured traffic is fully covered by typed fields, i.e. this is real Protobuf, not JSON in disguise."""
    for name, prim in ALL.items():
        msg = onem2m_pb2.Primitive.FromString(codec.encode(prim))
        assert not msg.ext and msg.WhichOneof("pc") != "pc_json", name
        for sub in (msg.ae, msg.cnt, msg.cin, msg.sub, msg.sgn):
            assert not sub.ext, name


def test_smaller_than_json_and_cbor():
    cbor2 = pytest.importorskip("cbor2")
    for name, prim in ALL.items():
        pb_size = len(codec.encode(prim))
        json_size = len(json.dumps(prim, separators=(",", ":")).encode())
        assert pb_size < len(cbor2.dumps(prim)) < json_size, name


def test_garbage_raises():
    with pytest.raises(Exception):
        codec.decode(b"\xff\xff\xff")


def test_acme_copy_matches_library():
    """ACME runs a copy of this codec (scripts/patch-acme.sh); the two must never drift apart."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    etc = root / "vendor" / "acme" / "acmecse" / "etc"
    if not (etc / "ProtoCodec.py").exists():
        pytest.skip("ACME not patched (make acme-patch)")
    assert (etc / "ProtoCodec.py").read_bytes() == (root / "grpb/onem2m/codec.py").read_bytes()
    assert (etc / "onem2m_pb2.py").read_bytes() == (root / "grpb/onem2m/onem2m_pb2.py").read_bytes()
