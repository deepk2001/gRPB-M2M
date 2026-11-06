"""Server side: serves generated gRPC servicers over MQTT, in place of grpc.server().

    server = grpb.MqttServer("hub", host="127.0.0.1")
    temperature_pb2_grpc.add_TemperatureServiceServicer_to_server(Hub(), server)
    server.start()
    server.wait_for_termination()

The servicer code is unchanged: it receives the usual (request, context) arguments and can
call context.abort(), add_callback(), is_active(), time_remaining() and so on.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent import futures
from typing import Any

import grpc

from . import topics
from ._endpoint import Endpoint
from .wire_pb2 import Frame

log = logging.getLogger("grpb")

class _Abort(Exception):
    """Raised by context.abort() to unwind the handler."""


class _Context:
    """The grpc.ServicerContext seen by servicer methods."""

    def __init__(self, client_id: str, frame: Frame) -> None:
        self.client_id = client_id
        self._metadata = tuple(frame.metadata.items())
        self._deadline = time.monotonic() + frame.timeout_ms / 1000 if frame.timeout_ms else None
        self._code: grpc.StatusCode | None = None
        self._details = ""
        self._cancelled = threading.Event()
        self._lock = threading.Lock()
        self._callbacks: list[Callable] = []
        self._done = False

    # grpc.ServicerContext API
    def abort(self, code: grpc.StatusCode, details: str) -> None:
        if code is grpc.StatusCode.OK:
            raise ValueError("abort() requires a non-OK status code")
        self._code, self._details = code, details
        raise _Abort()

    def abort_with_status(self, status: Any) -> None:
        self.abort(status.code, status.details)

    def set_code(self, code: grpc.StatusCode) -> None:
        self._code = code

    def set_details(self, details: str) -> None:
        self._details = details

    def code(self) -> grpc.StatusCode | None:
        return self._code

    def details(self) -> str:
        return self._details

    def is_active(self) -> bool:
        return not self._cancelled.is_set() and not self._expired()

    def time_remaining(self) -> float | None:
        return None if self._deadline is None else max(0.0, self._deadline - time.monotonic())

    def cancel(self) -> None:
        self._terminate()

    def add_callback(self, callback: Callable) -> bool:
        with self._lock:
            if self._done:
                return False
            self._callbacks.append(callback)
            return True

    def invocation_metadata(self) -> tuple:
        return self._metadata

    def peer(self) -> str:
        return f"mqtt:{self.client_id}"

    def send_initial_metadata(self, metadata: Any) -> None:
        pass

    def set_trailing_metadata(self, metadata: Any) -> None:
        pass

    def set_compression(self, compression: Any) -> None:
        pass

    def disable_next_message_compression(self) -> None:
        pass

    # internals
    def _expired(self) -> bool:
        return self._deadline is not None and time.monotonic() >= self._deadline

    def _terminate(self) -> None:
        """Mark the call over and run callbacks once (on completion, cancel or client loss)."""
        self._cancelled.set()
        with self._lock:
            if self._done:
                return
            self._done = True
            callbacks, self._callbacks = self._callbacks, []
        for cb in callbacks:
            try:
                cb()
            except Exception:
                log.exception("call termination callback failed")


class MqttServer:
    """A grpc.Server look-alike that receives calls from an MQTT broker.

    Args:
        server_id: the address clients use (MqttChannel(server_id=...)). Run one server per ID.
        host, port: the MQTT broker.
        prefix: topic prefix shared with clients.
        max_workers: concurrent calls; each open server stream holds one worker.
        keepalive: MQTT keepalive in seconds; a crashed server is reported offline after ~1.5x this.
    """

    def __init__(self, server_id: str, host: str = "127.0.0.1", port: int = 1883, *,
                 prefix: str = topics.DEFAULT_PREFIX, max_workers: int = 32, keepalive: int = 15) -> None:
        self.server_id = topics.check_id("server_id", server_id)
        self._prefix = prefix
        self._presence_topic = topics.presence(prefix, server_id)
        self._client_presence_head = topics.presence(prefix, "")
        self._handlers: dict[int, tuple[str, grpc.RpcMethodHandler]] = {}
        self._active: dict[tuple[str, int], _Context] = {}
        self._lock = threading.Lock()
        self._pool = futures.ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=f"grpb-{server_id}")
        self._stopping = False
        self._stopped = threading.Event()

        self._ep = Endpoint(
            f"grpb-server-{server_id}", host, port,
            subscriptions=[topics.requests_for(prefix, server_id), topics.presence(prefix, "+")],
            on_message=self._on_message,
            will=(self._presence_topic, b"offline", True),
            on_ready=lambda: self._ep.publish(self._presence_topic, b"online", retain=True),
            keepalive=keepalive,
        )

    # --- grpc.Server interface used by generated add_*_to_server() ------------------------

    def add_generic_rpc_handlers(self, generic_rpc_handlers: Any) -> None:
        for h in generic_rpc_handlers:
            # grpcio's dictionary handler exposes its methods; register them for fast lookup.
            for name, handler in getattr(h, "_method_handlers", {}).items():
                self._register(name, handler)

    def add_registered_method_handlers(self, service_name: str, method_handlers: dict) -> None:
        for method, handler in method_handlers.items():
            self._register(f"/{service_name}/{method}", handler)

    def add_insecure_port(self, address: str) -> int:
        raise NotImplementedError("MqttServer has no port: pass the broker host/port to MqttServer()")

    def add_secure_port(self, address: str, server_credentials: Any) -> int:
        raise NotImplementedError("MqttServer has no port: pass the broker host/port to MqttServer()")

    def start(self) -> None:
        """Connect to the broker and start serving. Returns immediately; reconnects on its own."""
        self._ep.start()

    def wait_ready(self, timeout: float | None = None) -> bool:
        """Block until connected and subscribed (True), or until timeout (False)."""
        return self._ep.ready.wait(timeout)

    def stop(self, grace: float | None) -> threading.Event:
        """Announce offline, cancel active calls (after `grace` seconds), disconnect."""
        self._stopping = True
        if self._ep.ready.is_set():
            self._ep.publish(self._presence_topic, b"offline", retain=True).wait_for_publish(2)

        def finish() -> None:
            if grace:
                end = time.monotonic() + grace
                while self._active and time.monotonic() < end:
                    time.sleep(0.05)
            with self._lock:
                remaining = list(self._active.values())
            for ctx in remaining:
                ctx._terminate()
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._ep.close()
            self._stopped.set()

        threading.Thread(target=finish, name=f"grpb-{self.server_id}-stop", daemon=True).start()
        return self._stopped

    def wait_for_termination(self, timeout: float | None = None) -> bool:
        return self._stopped.wait(timeout)

    # --- internals -------------------------------------------------------------------------

    def _register(self, name: str, handler: grpc.RpcMethodHandler) -> None:
        mid = topics.method_id(name)
        existing = self._handlers.get(mid)
        if existing and existing[0] != name:
            raise ValueError(f"method id collision between {existing[0]} and {name}; rename one method")
        self._handlers[mid] = (name, handler)

    def _on_message(self, topic: str, payload: bytes) -> None:
        if topic.startswith(self._client_presence_head):
            if payload == b"offline":
                self._client_gone(topic[len(self._client_presence_head):])
            return
        client_id = topics.client_of_request(self._prefix, topic)
        if client_id is None:
            return
        frame = Frame.FromString(payload)
        if frame.kind == Frame.REQUEST:
            if self._stopping:
                self._reply(client_id, Frame(kind=Frame.RESPONSE, call_id=frame.call_id,
                                             code=grpc.StatusCode.UNAVAILABLE.value[0], details="server is stopping"))
                return
            ctx = _Context(client_id, frame)
            with self._lock:
                self._active[(client_id, frame.call_id)] = ctx
            self._pool.submit(self._handle, client_id, frame, ctx)
        elif frame.kind == Frame.CANCEL:
            with self._lock:
                ctx = self._active.get((client_id, frame.call_id))
            if ctx:
                log.debug("call %s/%d cancelled by client", client_id, frame.call_id)
                ctx._terminate()

    def _client_gone(self, client_id: str) -> None:
        with self._lock:
            lost = [ctx for (cid, _), ctx in self._active.items() if cid == client_id]
        if lost:
            log.info("client %s went offline; cancelling %d call(s)", client_id, len(lost))
        for ctx in lost:
            ctx._terminate()

    def _reply(self, client_id: str, frame: Frame) -> None:
        self._ep.publish(topics.response(self._prefix, client_id, self.server_id), frame.SerializeToString())

    def _handle(self, client_id: str, frame: Frame, ctx: _Context) -> None:
        call_id = frame.call_id
        streaming = False

        def end(code: grpc.StatusCode, details: str = "", payload: bytes = b"") -> None:
            if ctx._cancelled.is_set():
                return  # nobody is listening any more
            kind = Frame.STREAM_END if streaming else Frame.RESPONSE
            self._reply(client_id, Frame(kind=kind, call_id=call_id, code=code.value[0], details=details, payload=payload))

        try:
            found = self._handlers.get(frame.method_id)
            if found is None:
                end(grpc.StatusCode.UNIMPLEMENTED, f"unknown method id {frame.method_id:#010x}")
                return
            name, handler = found
            if handler.request_streaming:
                end(grpc.StatusCode.UNIMPLEMENTED, f"{name}: client-streaming calls are not supported over MQTT yet")
                return
            request = handler.request_deserializer(frame.payload) if handler.request_deserializer else frame.payload
            serialize = handler.response_serializer or (lambda m: m)

            if handler.unary_unary:
                response = handler.unary_unary(request, ctx)
                if ctx._code not in (None, grpc.StatusCode.OK):
                    end(ctx._code, ctx._details)
                elif response is None:
                    end(grpc.StatusCode.INTERNAL, f"{name} returned None")
                else:
                    end(grpc.StatusCode.OK, payload=serialize(response))
            else:
                streaming = True
                items = handler.unary_stream(request, ctx)
                try:
                    for item in items:
                        if not ctx.is_active():
                            break
                        self._reply(client_id, Frame(kind=Frame.STREAM_MESSAGE, call_id=call_id, payload=serialize(item)))
                finally:
                    if hasattr(items, "close"):
                        items.close()  # run the generator's cleanup (finally blocks)
                if ctx._expired():
                    end(grpc.StatusCode.DEADLINE_EXCEEDED, "deadline exceeded")
                elif ctx._code not in (None, grpc.StatusCode.OK):
                    end(ctx._code, ctx._details)
                else:
                    end(grpc.StatusCode.OK)
        except _Abort:
            end(ctx._code, ctx._details)
        except Exception as e:
            log.exception("%s: unhandled exception in handler", self.server_id)
            end(grpc.StatusCode.UNKNOWN, f"Exception calling application: {e}")
        finally:
            with self._lock:
                self._active.pop((client_id, call_id), None)
            ctx._terminate()
