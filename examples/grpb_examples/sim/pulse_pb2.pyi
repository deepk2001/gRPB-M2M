from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class Sample(_message.Message):
    __slots__ = ("node_id", "seq", "sent_us", "accel", "heart_rate")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    SENT_US_FIELD_NUMBER: _ClassVar[int]
    ACCEL_FIELD_NUMBER: _ClassVar[int]
    HEART_RATE_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    seq: int
    sent_us: int
    accel: _containers.RepeatedScalarFieldContainer[float]
    heart_rate: float
    def __init__(self, node_id: _Optional[str] = ..., seq: _Optional[int] = ..., sent_us: _Optional[int] = ..., accel: _Optional[_Iterable[float]] = ..., heart_rate: _Optional[float] = ...) -> None: ...

class Ack(_message.Message):
    __slots__ = ("seq",)
    SEQ_FIELD_NUMBER: _ClassVar[int]
    seq: int
    def __init__(self, seq: _Optional[int] = ...) -> None: ...

class WatchRequest(_message.Message):
    __slots__ = ("node_id",)
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    def __init__(self, node_id: _Optional[str] = ...) -> None: ...
