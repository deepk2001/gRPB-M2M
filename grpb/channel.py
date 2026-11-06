"""Client side: a channel that generated gRPC stubs accept in place of grpc.insecure_channel().

    channel = grpb.MqttChannel("hub", host="192.168.1.20")
    stub = temperature_pb2_grpc.TemperatureServiceStub(channel)
    ack = stub.ReportReading(reading, timeout=5)        # unary
    for r in stub.WatchReadings(request): ...           # server streaming

Errors are raised as grpc.RpcError with the usual code() and details(), so code written
against gRPC over HTTP/2 keeps working unchanged.
"""

from __future__ import annotations

import itertools
import logging
import math
import queue
import threading
import time
import uuid
from collections.abc import Callable
from concurrent import futures
from typing import Any
from urllib.parse import urlparse

import grpc

from . import topics
from ._endpoint import Endpoint
from .wire_pb2 import Frame

log = logging.getLogger("grpb")

_POLL_S = 0.25  # how often blocked calls re-check deadlines and server presence


class MqttRpcError(grpc.RpcError):
    """A failed call. Same accessors as the errors raised by grpcio."""

    def __init__(self, code: grpc.StatusCode, details: str) -> None:
        super().__init__(f"{code.name}: {details}")
        self._code, self._details = code, details

    def code(self) -> grpc.StatusCode:
        return self._code

    def details(self) -> str:
        return self._details

    def initial_metadata(self) -> tuple:
        return ()

    def trailing_metadata(self) -> tuple:
        return ()

    def debug_error_string(self) -> str:
        return str(self)


_CODES = {c.value[0]: c for c in grpc.StatusCode}


def _status(code_value: int) -> grpc.StatusCode:
    return _CODES.get(code_value, grpc.StatusCode.UNKNOWN)


class _Pending:
    """Replies for one in-flight call, filled by the network thread."""

    def __init__(self) -> None:
        self.frames: queue.Queue[Frame] = queue.Queue()


class MqttChannel:
    """A gRPC-compatible channel to one server (by server ID) through an MQTT broker.

    Args:
        server_id: the ID the MqttServer was started with.
        host, port: the MQTT broker.
        client_id: this device's ID (also its MQTT client ID); random if omitted.
        prefix: topic prefix shared with the server.
        presence_grace: after connecting, how long to wait for the server's retained presence
            before treating an unknown server as offline.
    """

    def __init__(self, server_id: str, host: str = "127.0.0.1", port: int = 1883, *,
                 client_id: str | None = None, prefix: str = topics.DEFAULT_PREFIX,
                 keepalive: int = 15, presence_grace: float = 1.0) -> None:
        self.server_id = topics.check_id("server_id", server_id)
        self.client_id = topics.check_id("client_id", client_id or f"grpb-{uuid.uuid4().hex[:10]}")
        self._prefix = prefix
        self._req_topic = topics.request(prefix, self.client_id, server_id)
        self._presence_topic = topics.presence(prefix, server_id)
        self._presence_grace = presence_grace

        self._lock = threading.Lock()
        self._calls: dict[int, _Pending] = {}
        self._ids = itertools.count(1)
        self._server_online: bool | None = None
        self._ready_at = 0.0
        self._closed = False
        self._executor: futures.ThreadPoolExecutor | None = None

        self._ep = Endpoint(
            self.client_id, host, port,
            subscriptions=[topics.response(prefix, self.client_id, server_id), self._presence_topic],
            on_message=self._on_message,
            # If this device dies, the server hears "offline" and cancels its streams.
            will=(topics.presence(prefix, self.client_id), b"offline", False),
            on_ready=self._on_ready,
            keepalive=keepalive,
        )
        self._ep.start()

    @classmethod
    def from_url(cls, url: str, **kwargs: Any) -> MqttChannel:
        """mqtt://host[:port]/server-id"""
        u = urlparse(url)
        if u.scheme != "mqtt" or not u.hostname or not u.path.strip("/"):
            raise ValueError(f"expected mqtt://host[:port]/server-id, got {url!r}")
        return cls(u.path.strip("/"), u.hostname, u.port or 1883, **kwargs)

    # --- grpc.Channel interface used by generated stubs ------------------------------------

    def unary_unary(self, method: str, request_serializer: Callable | None = None,
                    response_deserializer: Callable | None = None, _registered_method: bool = False):
        return _UnaryUnary(self, method, request_serializer, response_deserializer)

    def unary_stream(self, method: str, request_serializer: Callable | None = None,
                     response_deserializer: Callable | None = None, _registered_method: bool = False):
        return _UnaryStream(self, method, request_serializer, response_deserializer)

    def stream_unary(self, method: str, *args: Any, **kwargs: Any):
        return _Unsupported(method)

    def stream_stream(self, method: str, *args: Any, **kwargs: Any):
        return _Unsupported(method)

    def subscribe(self, callback: Callable, try_to_connect: bool = False) -> None:
        raise NotImplementedError("connectivity subscriptions are not supported by MqttChannel")

    def unsubscribe(self, callback: Callable) -> None:
        raise NotImplementedError("connectivity subscriptions are not supported by MqttChannel")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with self._lock:
            pending, self._calls = list(self._calls.values()), {}
        for p in pending:
            p.frames.put(Frame(kind=Frame.STREAM_END, code=grpc.StatusCode.CANCELLED.value[0],
                               details="channel closed"))
        if self._ep.ready.is_set():
            # A clean disconnect does not fire the Last Will, so announce it ourselves.
            self._ep.publish(topics.presence(self._prefix, self.client_id), b"offline").wait_for_publish(2)
        self._ep.close()
        if self._executor:
            self._executor.shutdown(wait=False)

    def __enter__(self) -> MqttChannel:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- internals -------------------------------------------------------------------------

    def _on_ready(self) -> None:
        self._ready_at = time.monotonic()

    def _on_message(self, topic: str, payload: bytes) -> None:
        if topic == self._presence_topic:
            online = payload == b"online"
            if online != self._server_online:
                log.info("server %r is %s", self.server_id, "online" if online else "offline")
            self._server_online = online
            return
        frame = Frame.FromString(payload)
        with self._lock:
            pending = self._calls.get(frame.call_id)
        if pending:
            pending.frames.put(frame)

    def _server_usable(self) -> bool:
        return self._ep.ready.is_set() and self._server_online is True

    def _await_ready(self, deadline: float | None, wait_for_ready: bool) -> None:
        """Block until broker and server are reachable, or raise like gRPC would."""
        while True:
            if self._closed:
                raise MqttRpcError(grpc.StatusCode.CANCELLED, "channel closed")
            if self._server_usable():
                return
            now = time.monotonic()
            if not wait_for_ready:
                if self._ep.settled.is_set() and not self._ep.ready.is_set():
                    raise MqttRpcError(grpc.StatusCode.UNAVAILABLE,
                                       f"MQTT broker {self._ep.host}:{self._ep.port} unreachable")
                if self._ep.ready.is_set() and (
                        self._server_online is False
                        or (self._server_online is None and now - self._ready_at >= self._presence_grace)):
                    raise MqttRpcError(grpc.StatusCode.UNAVAILABLE, f"server {self.server_id!r} is offline")
            if deadline is not None and now >= deadline:
                raise MqttRpcError(grpc.StatusCode.DEADLINE_EXCEEDED, "deadline exceeded while connecting")
            time.sleep(_POLL_S if deadline is None else max(0.0, min(_POLL_S, deadline - now)))

    def _start_call(self, method: str, payload: bytes, timeout: float | None,
                    metadata: Any, wait_for_ready: bool | None) -> tuple[int, _Pending, float | None]:
        deadline = time.monotonic() + timeout if timeout is not None else None
        self._await_ready(deadline, bool(wait_for_ready))
        call_id = next(self._ids)
        pending = _Pending()
        with self._lock:
            self._calls[call_id] = pending
        frame = Frame(kind=Frame.REQUEST, call_id=call_id, method_id=topics.method_id(method), payload=payload,
                      timeout_ms=int(timeout * 1000) if timeout is not None else 0,
                      metadata=dict(metadata or ()))
        self._ep.publish(self._req_topic, frame.SerializeToString(),
                         expiry_s=math.ceil(timeout) if timeout is not None else None)
        return call_id, pending, deadline

    def _next_frame(self, pending: _Pending, deadline: float | None) -> Frame:
        """Wait for the next reply; fails if the deadline passes or the server goes away."""
        while True:
            now = time.monotonic()
            if deadline is not None and now >= deadline:
                raise MqttRpcError(grpc.StatusCode.DEADLINE_EXCEEDED, "deadline exceeded")
            try:
                return pending.frames.get(timeout=_POLL_S if deadline is None else min(_POLL_S, deadline - now))
            except queue.Empty:
                pass
            if self._closed:
                raise MqttRpcError(grpc.StatusCode.CANCELLED, "channel closed")
            if not self._server_usable():
                # The server (or our broker link) dropped while the call was in flight.
                raise MqttRpcError(grpc.StatusCode.UNAVAILABLE, f"server {self.server_id!r} went offline")

    def _end_call(self, call_id: int, cancel: bool) -> None:
        with self._lock:
            self._calls.pop(call_id, None)
        if cancel and self._ep.ready.is_set():
            self._ep.publish(self._req_topic, Frame(kind=Frame.CANCEL, call_id=call_id).SerializeToString())

    def _submit(self, fn: Callable, *args: Any) -> futures.Future:
        with self._lock:
            if self._executor is None:
                self._executor = futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="grpb-future")
        return self._executor.submit(fn, *args)


class _UnaryUnary:
    def __init__(self, ch: MqttChannel, method: str, ser: Callable | None, deser: Callable | None) -> None:
        self._ch, self._method = ch, method
        self._ser = ser or (lambda b: b)
        self._deser = deser or (lambda b: b)

    def __call__(self, request: Any, timeout: float | None = None, metadata: Any = None,
                 credentials: Any = None, wait_for_ready: bool | None = None, compression: Any = None) -> Any:
        ch = self._ch
        call_id, pending, deadline = ch._start_call(self._method, self._ser(request), timeout, metadata, wait_for_ready)
        done = False
        try:
            frame = ch._next_frame(pending, deadline)
            done = True
        finally:
            ch._end_call(call_id, cancel=not done)
        if frame.code:
            raise MqttRpcError(_status(frame.code), frame.details)
        return self._deser(frame.payload)

    def with_call(self, request: Any, timeout: float | None = None, metadata: Any = None, **kwargs: Any):
        return self(request, timeout=timeout, metadata=metadata, **kwargs), None

    def future(self, request: Any, timeout: float | None = None, metadata: Any = None, **kwargs: Any) -> futures.Future:
        return self._ch._submit(lambda: self(request, timeout=timeout, metadata=metadata, **kwargs))


class _UnaryStream:
    def __init__(self, ch: MqttChannel, method: str, ser: Callable | None, deser: Callable | None) -> None:
        self._ch, self._method = ch, method
        self._ser = ser or (lambda b: b)
        self._deser = deser or (lambda b: b)

    def __call__(self, request: Any, timeout: float | None = None, metadata: Any = None,
                 credentials: Any = None, wait_for_ready: bool | None = None, compression: Any = None) -> _StreamCall:
        return _StreamCall(self._ch, self._method, self._ser(request), self._deser, timeout, metadata, wait_for_ready)


class _StreamCall(MqttRpcError):
    """Iterator over a server stream. Like grpcio's call object, it is also the error raised
    when the stream ends badly, and it can be cancelled from another thread."""

    def __init__(self, ch: MqttChannel, method: str, payload: bytes, deser: Callable,
                 timeout: float | None, metadata: Any, wait_for_ready: bool | None) -> None:
        super().__init__(grpc.StatusCode.OK, "")
        self._ch, self._method, self._payload, self._deser = ch, method, payload, deser
        self._timeout, self._metadata, self._wait_for_ready = timeout, metadata, wait_for_ready
        self._call_id: int | None = None
        self._pending: _Pending | None = None
        self._deadline: float | None = None
        self._finished = False
        self._cancelled = False
        self._callbacks: list[Callable] = []

    def __iter__(self) -> _StreamCall:
        return self

    def __next__(self) -> Any:
        if self._finished:
            if self._code is grpc.StatusCode.OK:
                raise StopIteration
            raise self
        try:
            if self._pending is None:
                self._call_id, self._pending, self._deadline = self._ch._start_call(
                    self._method, self._payload, self._timeout, self._metadata, self._wait_for_ready)
            while True:
                if self._cancelled:
                    raise MqttRpcError(grpc.StatusCode.CANCELLED, "cancelled by client")
                frame = self._ch._next_frame(self._pending, self._deadline)
                if frame.kind == Frame.STREAM_MESSAGE:
                    return self._deser(frame.payload)
                if frame.kind in (Frame.STREAM_END, Frame.RESPONSE):
                    self._finish(_status(frame.code), frame.details, cancel=False)
                    return self.__next__()
        except MqttRpcError as e:
            self._finish(e.code(), e.details(), cancel=True)
            raise self from None

    def _finish(self, code: grpc.StatusCode, details: str, cancel: bool) -> None:
        if self._finished:
            return
        self._finished = True
        self._code, self._details = code, details
        self.args = (f"{code.name}: {details}",)
        if self._call_id is not None:
            self._ch._end_call(self._call_id, cancel=cancel)
        for cb in self._callbacks:
            cb()

    def cancel(self) -> bool:
        """Stop the stream: tells the server now; a blocked iteration raises CANCELLED."""
        if self._finished:
            return False
        self._cancelled = True
        if self._pending is not None and self._call_id is not None:
            self._ch._end_call(self._call_id, cancel=True)
            self._pending.frames.put(Frame(kind=Frame.STREAM_END, code=grpc.StatusCode.CANCELLED.value[0],
                                           details="cancelled by client"))
        else:
            self._finish(grpc.StatusCode.CANCELLED, "cancelled by client", cancel=False)
        return True

    def is_active(self) -> bool:
        return not self._finished

    def time_remaining(self) -> float | None:
        return None if self._deadline is None else max(0.0, self._deadline - time.monotonic())

    def add_callback(self, callback: Callable) -> bool:
        if self._finished:
            return False
        self._callbacks.append(callback)
        return True


class _Unsupported:
    """Client streaming is not implemented over MQTT yet; fail at call time, not stub creation."""

    def __init__(self, method: str) -> None:
        self._method = method

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise MqttRpcError(grpc.StatusCode.UNIMPLEMENTED,
                           f"{self._method}: client-streaming calls are not supported over MQTT yet")
