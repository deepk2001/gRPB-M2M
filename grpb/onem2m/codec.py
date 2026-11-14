"""oneM2M primitive dictionaries <-> Protobuf bytes (onem2m.proto), losslessly.

    data = encode({"op": 1, "to": "cse-in/ae/temp", "fr": "Cae", "rqi": "1", "rvi": "5", "ty": 4,
                   "pc": {"m2m:cin": {"con": "23.5"}}})
    assert decode(data) == {...the same dictionary...}

Modelled attributes become typed Protobuf fields. Anything else (unknown attributes, values of
an unexpected type, empty lists, other timestamp formats) is carried as compact JSON in the
`ext` field of the same object, so decode(encode(d)) == d for any JSON-compatible primitive.

This file is used unchanged by the device library (grpb.onem2m.codec) and by the patched ACME
CSE (acmecse/etc/ProtoCodec.py); keep it free of imports from either package.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

from . import onem2m_pb2 as pb

__all__ = ["encode", "decode", "MEDIA_TYPE"]

MEDIA_TYPE = "application/vnd.onem2m-res+protobuf"

STR, INT, BOOL, TS, STRS, INTS = range(6)

_COMMON = {"rn": STR, "ri": STR, "pi": STR, "ty": INT, "ct": TS, "lt": TS, "et": TS, "lbl": STRS}
_SPECS: dict[str, dict[str, int]] = {
    "AE": {**_COMMON, "acpi": STRS, "api": STR, "aei": STR, "rr": BOOL, "srv": STRS, "poa": STRS, "csz": STRS},
    "Container": {**_COMMON, "acpi": STRS, "st": INT, "mni": INT, "mbs": INT, "cni": INT, "cbs": INT,
                  "mia": INT, "cr": STR},
    "ContentInstance": {**_COMMON, "cnf": STR, "con": STR, "cs": INT, "st": INT, "cr": STR},
    "Subscription": {**_COMMON, "acpi": STRS, "nu": STRS, "nct": INT, "cr": STR, "exc": INT},
}
_PRIMITIVE = {"op": INT, "to": STR, "fr": STR, "rqi": STR, "ty": INT, "rvi": STR, "rsc": INT,
              "ot": TS, "rqet": TS, "drt": INT, "rcn": INT}
_SGN = {"sur": STR, "vrq": BOOL, "cr": STR}

# "m2m:..." wrapper -> (oneof field name, message class)
_RESOURCES = {"m2m:ae": ("ae", pb.AE), "m2m:cnt": ("cnt", pb.Container),
              "m2m:cin": ("cin", pb.ContentInstance), "m2m:sub": ("sub", pb.Subscription)}
_WRAPPER_OF = {field: wrapper for wrapper, (field, _) in _RESOURCES.items()}

_TS_RE = re.compile(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2}),(\d{6})")
_EPOCH = datetime(1970, 1, 1)
_US = timedelta(microseconds=1)
_UINT32_MAX = 2**32 - 1


# --- scalar conversion ----------------------------------------------------------------------


def _convert(kind: int, v: Any) -> tuple[bool, Any]:
    """(True, wire value) if v fits the modelled kind exactly, else (False, None)."""
    if kind == STR:
        return type(v) is str, v
    if kind == INT:
        return type(v) is int and 0 <= v <= _UINT32_MAX, v
    if kind == BOOL:
        return type(v) is bool, v
    if kind == TS:
        if type(v) is not str:
            return False, None
        us = _ts_us(v)
        return us is not None, us
    if kind == STRS:
        return type(v) is list and len(v) > 0 and all(type(x) is str for x in v), v
    if kind == INTS:
        return (type(v) is list and len(v) > 0
                and all(type(x) is int and 0 <= x <= _UINT32_MAX for x in v)), v
    raise AssertionError(kind)


@lru_cache(maxsize=4096)  # resources repeat the same timestamps (ct == lt, shared et)
def _ts_us(v: str) -> int | None:
    if not (m := _TS_RE.fullmatch(v)):
        return None
    try:
        dt = datetime(*(int(g) for g in m.groups()))
    except ValueError:
        return None
    return (dt - _EPOCH) // _US


@lru_cache(maxsize=4096)
def _ts_str(us: int) -> str:
    d = _EPOCH + timedelta(microseconds=us)
    return (f"{d.year:04d}{d.month:02d}{d.day:02d}T{d.hour:02d}{d.minute:02d}{d.second:02d},"
            f"{d.microsecond:06d}")


def _json(v: Any) -> bytes:
    return json.dumps(v, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


# --- generic object <-> message ------------------------------------------------------------


def _fill(msg: Any, d: dict, spec: dict[str, int], extra: dict | None = None) -> None:
    """Copy modelled keys of d into msg; the rest (plus `extra`) goes to msg.ext as JSON."""
    rest = dict(extra) if extra else {}
    for k, v in d.items():
        kind = spec.get(k)
        ok, wire = _convert(kind, v) if kind is not None else (False, None)
        if not ok:
            rest[k] = v
        elif kind in (STRS, INTS):
            getattr(msg, k).extend(wire)
        else:
            setattr(msg, k, wire)
    if rest:
        msg.ext = _json(rest)


def _read(msg: Any, spec: dict[str, int]) -> dict:
    d: dict = {}
    for fd, v in msg.ListFields():  # only fields that are set, in C
        kind = spec.get(fd.name)
        if kind is None:
            continue  # ext and oneof members are handled by the callers
        if kind == TS:
            d[fd.name] = _ts_str(v)
        elif kind in (STRS, INTS):
            d[fd.name] = list(v)
        else:
            d[fd.name] = v
    if msg.ext:
        d.update(json.loads(msg.ext))
    return d


# --- resources --------------------------------------------------------------------------------


def _encode_resource(wrapper: str, d: dict) -> Any:
    _, cls = _RESOURCES[wrapper]
    msg = cls()
    spec = _SPECS[cls.DESCRIPTOR.name]
    if cls is pb.Subscription and "enc" in d:
        enc = d["enc"]
        # enc = {"net": [...]} is the common case; anything richer stays in ext
        if type(enc) is dict and set(enc) == {"net"} and _convert(INTS, enc["net"])[0]:
            msg.net.extend(enc["net"])
            d = {k: v for k, v in d.items() if k != "enc"}
    _fill(msg, d, spec)
    return msg


def _decode_resource(msg: Any) -> dict:
    d = _read(msg, _SPECS[msg.DESCRIPTOR.name])
    if isinstance(msg, pb.Subscription) and msg.net:
        d["enc"] = {"net": list(msg.net)}
    return d


def _resource_wrapper(v: Any) -> tuple[str, dict] | None:
    """('m2m:cin', {...}) if v is a single modelled resource wrapper, else None."""
    if type(v) is dict and len(v) == 1:
        (key, val), = v.items()
        if key in _RESOURCES and type(val) is dict:
            return key, val
    return None


# --- notifications ----------------------------------------------------------------------------


def _encode_sgn(d: dict) -> pb.Notification:
    msg = pb.Notification()
    nev = d.get("nev")
    rest = {k: v for k, v in d.items() if k != "nev"}
    modelled = False
    if type(nev) is dict and nev and set(nev) <= {"net", "rep"}:
        net_ok = "net" not in nev or _convert(INT, nev["net"])[0]
        rep = _resource_wrapper(nev["rep"]) if "rep" in nev else None
        if net_ok and ("rep" not in nev or rep):
            if "net" in nev:
                msg.net = nev["net"]
            if rep:
                field, _ = _RESOURCES[rep[0]]
                getattr(msg, field).CopyFrom(_encode_resource(*rep))
            modelled = True
    _fill(msg, rest, _SGN, extra=None if modelled or "nev" not in d else {"nev": nev})
    return msg


def _decode_sgn(msg: pb.Notification) -> dict:
    d = _read(msg, _SGN)
    rep_field = msg.WhichOneof("rep")
    if msg.HasField("net") or rep_field:
        nev: dict = {}
        if msg.HasField("net"):
            nev["net"] = msg.net
        if rep_field:
            nev["rep"] = {_WRAPPER_OF[rep_field]: _decode_resource(getattr(msg, rep_field))}
        d["nev"] = nev
    return d


# --- primitives -------------------------------------------------------------------------------


def encode(primitive: dict) -> bytes:
    """Serialize a oneM2M primitive dictionary (request, response or notification)."""
    msg = pb.Primitive()
    rest = {k: v for k, v in primitive.items() if k != "pc"}
    if "pc" in primitive:
        pc = primitive["pc"]
        if res := _resource_wrapper(pc):
            field, _ = _RESOURCES[res[0]]
            getattr(msg, field).CopyFrom(_encode_resource(*res))
        elif type(pc) is dict and len(pc) == 1 and type(pc.get("m2m:sgn")) is dict:
            msg.sgn.CopyFrom(_encode_sgn(pc["m2m:sgn"]))
        elif type(pc) is dict and len(pc) == 1 and type(pc.get("m2m:dbg")) is str:
            msg.dbg = pc["m2m:dbg"]
        else:
            msg.pc_json = _json(pc)
    _fill(msg, rest, _PRIMITIVE)
    return msg.SerializeToString()


def decode(data: bytes) -> dict:
    """Parse Protobuf bytes back into the oneM2M primitive dictionary."""
    msg = pb.Primitive.FromString(data)
    d = _read(msg, _PRIMITIVE)
    match msg.WhichOneof("pc"):
        case None:
            pass
        case "sgn":
            d["pc"] = {"m2m:sgn": _decode_sgn(msg.sgn)}
        case "dbg":
            d["pc"] = {"m2m:dbg": msg.dbg}
        case "pc_json":
            d["pc"] = json.loads(msg.pc_json)
        case field:
            d["pc"] = {_WRAPPER_OF[field]: _decode_resource(getattr(msg, field))}
    return d
