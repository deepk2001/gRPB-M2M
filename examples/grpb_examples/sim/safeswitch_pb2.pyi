from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class Command(_message.Message):
    __slots__ = ("actuator_id", "seq", "issued_us", "on")
    ACTUATOR_ID_FIELD_NUMBER: _ClassVar[int]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    ISSUED_US_FIELD_NUMBER: _ClassVar[int]
    ON_FIELD_NUMBER: _ClassVar[int]
    actuator_id: str
    seq: int
    issued_us: int
    on: bool
    def __init__(self, actuator_id: _Optional[str] = ..., seq: _Optional[int] = ..., issued_us: _Optional[int] = ..., on: _Optional[bool] = ...) -> None: ...

class State(_message.Message):
    __slots__ = ("actuator_id", "seq", "on", "applied_us")
    ACTUATOR_ID_FIELD_NUMBER: _ClassVar[int]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    ON_FIELD_NUMBER: _ClassVar[int]
    APPLIED_US_FIELD_NUMBER: _ClassVar[int]
    actuator_id: str
    seq: int
    on: bool
    applied_us: int
    def __init__(self, actuator_id: _Optional[str] = ..., seq: _Optional[int] = ..., on: _Optional[bool] = ..., applied_us: _Optional[int] = ...) -> None: ...
