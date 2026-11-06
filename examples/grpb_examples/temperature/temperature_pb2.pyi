from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class Reading(_message.Message):
    __slots__ = ("sensor_id", "celsius", "timestamp", "seq")
    SENSOR_ID_FIELD_NUMBER: _ClassVar[int]
    CELSIUS_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    sensor_id: str
    celsius: float
    timestamp: int
    seq: int
    def __init__(self, sensor_id: _Optional[str] = ..., celsius: _Optional[float] = ..., timestamp: _Optional[int] = ..., seq: _Optional[int] = ...) -> None: ...

class ReportAck(_message.Message):
    __slots__ = ("seq", "total_stored")
    SEQ_FIELD_NUMBER: _ClassVar[int]
    TOTAL_STORED_FIELD_NUMBER: _ClassVar[int]
    seq: int
    total_stored: int
    def __init__(self, seq: _Optional[int] = ..., total_stored: _Optional[int] = ...) -> None: ...

class GetLatestRequest(_message.Message):
    __slots__ = ("sensor_id",)
    SENSOR_ID_FIELD_NUMBER: _ClassVar[int]
    sensor_id: str
    def __init__(self, sensor_id: _Optional[str] = ...) -> None: ...

class WatchRequest(_message.Message):
    __slots__ = ("sensor_id",)
    SENSOR_ID_FIELD_NUMBER: _ClassVar[int]
    sensor_id: str
    def __init__(self, sensor_id: _Optional[str] = ...) -> None: ...
