"""oneM2M over MQTT: the Protobuf codec for primitives, and a client that speaks JSON, CBOR or Protobuf."""

from .codec import MEDIA_TYPE, decode, encode

__all__ = ["MEDIA_TYPE", "decode", "encode"]
