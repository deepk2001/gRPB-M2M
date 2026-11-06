"""MQTT topic layout, modelled on oneM2M's MQTT binding (TS-0010) with a "pb" format segment."""

from __future__ import annotations

import zlib

DEFAULT_PREFIX = "grpb"
FORMAT = "pb"


def check_id(kind: str, value: str) -> str:
    """Endpoint IDs become topic levels, so they must not contain MQTT separators or wildcards."""
    if not value or any(c in value for c in "/+#") or "\x00" in value:
        raise ValueError(f"invalid {kind} {value!r}: must be non-empty without '/', '+', '#'")
    return value


def request(prefix: str, client_id: str, server_id: str) -> str:
    return f"{prefix}/req/{client_id}/{server_id}/{FORMAT}"


def response(prefix: str, client_id: str, server_id: str) -> str:
    return f"{prefix}/resp/{client_id}/{server_id}/{FORMAT}"


def presence(prefix: str, endpoint_id: str) -> str:
    return f"{prefix}/presence/{endpoint_id}"


def requests_for(prefix: str, server_id: str) -> str:
    """Subscription filter for every client's requests to one server."""
    return request(prefix, "+", server_id)


def client_of_request(prefix: str, topic: str) -> str | None:
    """Client ID from a request topic, or None if the topic is not a request topic."""
    head = f"{prefix}/req/"
    if not topic.startswith(head):
        return None
    parts = topic[len(head):].split("/")
    return parts[0] if len(parts) == 3 and parts[2] == FORMAT else None


def method_id(full_method: str) -> int:
    """Compact method identifier sent on the wire instead of the full "/pkg.Service/Method" name."""
    return zlib.crc32(full_method.encode("utf-8"))
