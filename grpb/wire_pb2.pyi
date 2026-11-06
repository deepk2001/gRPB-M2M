from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Frame(_message.Message):
    __slots__ = ("kind", "call_id", "method_id", "payload", "code", "details", "timeout_ms", "metadata")
    class Kind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        KIND_UNSPECIFIED: _ClassVar[Frame.Kind]
        REQUEST: _ClassVar[Frame.Kind]
        RESPONSE: _ClassVar[Frame.Kind]
        STREAM_MESSAGE: _ClassVar[Frame.Kind]
        STREAM_END: _ClassVar[Frame.Kind]
        CANCEL: _ClassVar[Frame.Kind]
    KIND_UNSPECIFIED: Frame.Kind
    REQUEST: Frame.Kind
    RESPONSE: Frame.Kind
    STREAM_MESSAGE: Frame.Kind
    STREAM_END: Frame.Kind
    CANCEL: Frame.Kind
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    KIND_FIELD_NUMBER: _ClassVar[int]
    CALL_ID_FIELD_NUMBER: _ClassVar[int]
    METHOD_ID_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    DETAILS_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_MS_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    kind: Frame.Kind
    call_id: int
    method_id: int
    payload: bytes
    code: int
    details: str
    timeout_ms: int
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, kind: _Optional[_Union[Frame.Kind, str]] = ..., call_id: _Optional[int] = ..., method_id: _Optional[int] = ..., payload: _Optional[bytes] = ..., code: _Optional[int] = ..., details: _Optional[str] = ..., timeout_ms: _Optional[int] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...
