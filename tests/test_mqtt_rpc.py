"""Library tests for gRPB-M2M over a real Mosquitto broker. Handlers use raw bytes (no
serializers), so no generated code is needed; the sample-app tests cover generated stubs."""

from __future__ import annotations

import threading
import time
import uuid

import grpc
import pytest

import grpb

SERVICE = "test.Svc"


def method(name: str) -> str:
    return f"/{SERVICE}/{name}"


def uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class Recorder:
    """Shared state between handlers and assertions."""

    def __init__(self) -> None:
        self.callback_fired = threading.Event()
        self.stream_started = threading.Event()
        self.time_remaining: float | None = None


def build_handlers(rec: Recorder) -> dict[str, grpc.RpcMethodHandler]:
    def echo(req: bytes, ctx) -> bytes:
        return req

    def meta(req: bytes, ctx) -> bytes:
        return ",".join(f"{k}={v}" for k, v in sorted(ctx.invocation_metadata())).encode()

    def fail(req: bytes, ctx) -> bytes:
        ctx.abort(grpc.StatusCode.FAILED_PRECONDITION, "nope")

    def crash(req: bytes, ctx) -> bytes:
        raise RuntimeError("boom")

    def slow(req: bytes, ctx) -> bytes:
        rec.time_remaining = ctx.time_remaining()
        time.sleep(1.5)
        return b"late"

    def count(req: bytes, ctx):
        for i in range(int(req)):
            yield str(i).encode()

    def count_then_fail(req: bytes, ctx):
        yield b"0"
        ctx.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "stream limit")

    def forever(req: bytes, ctx):
        stop = threading.Event()
        ctx.add_callback(lambda: (rec.callback_fired.set(), stop.set()))
        rec.stream_started.set()
        i = 0
        while not stop.wait(0.05):
            i += 1
            yield str(i).encode()

    return {
        "Echo": grpc.unary_unary_rpc_method_handler(echo),
        "Meta": grpc.unary_unary_rpc_method_handler(meta),
        "Fail": grpc.unary_unary_rpc_method_handler(fail),
        "Crash": grpc.unary_unary_rpc_method_handler(crash),
        "Slow": grpc.unary_unary_rpc_method_handler(slow),
        "Count": grpc.unary_stream_rpc_method_handler(count),
        "CountThenFail": grpc.unary_stream_rpc_method_handler(count_then_fail),
        "Forever": grpc.unary_stream_rpc_method_handler(forever),
        "Upload": grpc.stream_unary_rpc_method_handler(lambda it, ctx: b""),
    }


def start_server(broker, server_id: str, rec: Recorder) -> grpb.MqttServer:
    server = grpb.MqttServer(server_id, broker.host, broker.port, keepalive=5)
    server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(SERVICE, build_handlers(rec)),))
    server.start()
    assert server.wait_ready(5)
    return server


@pytest.fixture
def rig(broker):
    """A running server and a connected channel with unique IDs."""
    rec = Recorder()
    sid = uid("srv")
    server = start_server(broker, sid, rec)
    channel = grpb.MqttChannel(sid, broker.host, broker.port, client_id=uid("cli"))
    yield server, channel, rec
    channel.close()
    server.stop(0).wait(5)


def code_of(fn) -> grpc.StatusCode:
    with pytest.raises(grpc.RpcError) as ei:
        fn()
    return ei.value.code()


# --- unary ------------------------------------------------------------------------------


def test_unary_roundtrip(rig):
    _, ch, _ = rig
    assert ch.unary_unary(method("Echo"))(b"hello", timeout=5) == b"hello"
    assert ch.unary_unary(method("Echo"))(b"", timeout=5) == b""


def test_metadata_passthrough(rig):
    _, ch, _ = rig
    out = ch.unary_unary(method("Meta"))(b"", timeout=5, metadata=(("device", "pi-3"), ("fw", "1.2")))
    assert out == b"device=pi-3,fw=1.2"


def test_abort_maps_to_status(rig):
    _, ch, _ = rig
    with pytest.raises(grpc.RpcError) as ei:
        ch.unary_unary(method("Fail"))(b"", timeout=5)
    assert ei.value.code() is grpc.StatusCode.FAILED_PRECONDITION
    assert ei.value.details() == "nope"


def test_handler_exception_is_unknown(rig):
    _, ch, _ = rig
    assert code_of(lambda: ch.unary_unary(method("Crash"))(b"", timeout=5)) is grpc.StatusCode.UNKNOWN


def test_unknown_method_is_unimplemented(rig):
    _, ch, _ = rig
    assert code_of(lambda: ch.unary_unary(method("Nope"))(b"", timeout=5)) is grpc.StatusCode.UNIMPLEMENTED


def test_client_streaming_is_unimplemented(rig):
    _, ch, _ = rig
    assert code_of(lambda: ch.stream_unary(method("Upload"))(iter([b"x"]))) is grpc.StatusCode.UNIMPLEMENTED


def test_deadline_exceeded_and_server_sees_deadline(rig):
    _, ch, rec = rig
    t0 = time.monotonic()
    assert code_of(lambda: ch.unary_unary(method("Slow"))(b"", timeout=0.5)) is grpc.StatusCode.DEADLINE_EXCEEDED
    assert time.monotonic() - t0 < 1.2
    time.sleep(0.2)
    assert rec.time_remaining is not None and 0 < rec.time_remaining <= 0.5


def test_future(rig):
    _, ch, _ = rig
    assert ch.unary_unary(method("Echo")).future(b"f", timeout=5).result(5) == b"f"


def test_concurrent_calls(rig):
    _, ch, _ = rig
    echo = ch.unary_unary(method("Echo"))
    futs = [echo.future(str(i).encode(), timeout=5) for i in range(50)]
    assert [f.result(10) for f in futs] == [str(i).encode() for i in range(50)]


# --- server streaming ---------------------------------------------------------------------


def test_stream_in_order(rig):
    _, ch, _ = rig
    assert list(ch.unary_stream(method("Count"))(b"20", timeout=5)) == [str(i).encode() for i in range(20)]


def test_stream_error_after_items(rig):
    _, ch, _ = rig
    call = ch.unary_stream(method("CountThenFail"))(b"", timeout=5)
    assert next(call) == b"0"
    with pytest.raises(grpc.RpcError) as ei:
        next(call)
    assert ei.value.code() is grpc.StatusCode.RESOURCE_EXHAUSTED


def test_client_cancel_reaches_server(rig):
    _, ch, rec = rig
    call = ch.unary_stream(method("Forever"))(b"")
    assert next(call)
    call.cancel()
    assert rec.callback_fired.wait(3), "server never saw the cancel"
    with pytest.raises(grpc.RpcError) as ei:
        for _ in call:
            pass
    assert ei.value.code() is grpc.StatusCode.CANCELLED


def test_channel_close_cancels_server_stream(broker):
    rec = Recorder()
    sid = uid("srv")
    server = start_server(broker, sid, rec)
    ch = grpb.MqttChannel(sid, broker.host, broker.port)
    call = ch.unary_stream(method("Forever"))(b"")

    def drain() -> None:
        try:
            for _ in call:
                pass
        except grpc.RpcError:
            pass  # CANCELLED once the channel closes

    threading.Thread(target=drain, daemon=True).start()
    assert rec.stream_started.wait(3)
    ch.close()  # announces "offline", like the Last Will does on a crash
    assert rec.callback_fired.wait(3), "server kept streaming to a gone client"
    server.stop(0).wait(5)


def test_server_stop_ends_client_stream(broker):
    rec = Recorder()
    sid = uid("srv")
    server = start_server(broker, sid, rec)
    ch = grpb.MqttChannel(sid, broker.host, broker.port)
    call = ch.unary_stream(method("Forever"))(b"")
    assert next(call)
    server.stop(0).wait(5)
    with pytest.raises(grpc.RpcError) as ei:
        for _ in call:
            pass
    assert ei.value.code() is grpc.StatusCode.UNAVAILABLE
    ch.close()


# --- availability -------------------------------------------------------------------------


def test_offline_server_fails_fast(broker):
    with grpb.MqttChannel(uid("ghost"), broker.host, broker.port) as ch:
        t0 = time.monotonic()
        assert code_of(lambda: ch.unary_unary(method("Echo"))(b"", timeout=10)) is grpc.StatusCode.UNAVAILABLE
        assert time.monotonic() - t0 < 3


def test_wait_for_ready_waits_for_server(broker):
    sid = uid("late")
    with grpb.MqttChannel(sid, broker.host, broker.port) as ch:
        result: dict = {}
        t = threading.Thread(target=lambda: result.update(
            out=ch.unary_unary(method("Echo"))(b"queued", timeout=10, wait_for_ready=True)))
        t.start()
        time.sleep(1.0)
        server = start_server(broker, sid, Recorder())
        t.join(10)
        assert result.get("out") == b"queued"
        server.stop(0).wait(5)


def test_unreachable_broker(tmp_path):
    with grpb.MqttChannel("hub", "127.0.0.1", 1) as ch:  # nothing listens on port 1
        assert code_of(lambda: ch.unary_unary(method("Echo"))(b"", timeout=5)) is grpc.StatusCode.UNAVAILABLE


def test_from_url(broker):
    ch = grpb.MqttChannel.from_url(f"mqtt://{broker.host}:{broker.port}/hub")
    assert (ch.server_id, ch._ep.port) == ("hub", broker.port)
    ch.close()
    with pytest.raises(ValueError):
        grpb.MqttChannel.from_url("http://x/hub")


def test_rejects_ids_with_topic_characters():
    with pytest.raises(ValueError):
        grpb.MqttChannel("a/b")
    with pytest.raises(ValueError):
        grpb.MqttServer("hub+")


def test_stale_request_is_refused_not_executed(broker):
    """A request reaching the server after the client's absolute deadline (e.g. buffered while the
    device was cut off) is answered DEADLINE_EXCEEDED and never executed."""
    import paho.mqtt.client as mqtt
    from paho.mqtt.enums import CallbackAPIVersion

    from grpb import topics
    from grpb.wire_pb2 import Frame

    ran = threading.Event()
    sid = uid("srv")
    server = grpb.MqttServer(sid, broker.host, broker.port)
    server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(SERVICE, {
        "Act": grpc.unary_unary_rpc_method_handler(lambda req, ctx: ran.set() or b"done")}),))
    server.start()
    assert server.wait_ready(5)

    client_id, replies = uid("raw"), []
    got = threading.Event()
    c = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=client_id, protocol=mqtt.MQTTv5)
    c.on_message = lambda cl, u, m: (replies.append(Frame.FromString(m.payload)), got.set())
    c.connect(broker.host, broker.port)
    c.subscribe(topics.response(topics.DEFAULT_PREFIX, client_id, sid), qos=1)
    c.loop_start()
    try:
        time.sleep(0.3)
        stale = Frame(kind=Frame.REQUEST, call_id=1, method_id=topics.method_id(method("Act")), payload=b"x",
                      timeout_ms=2000, deadline_unix_ms=int(time.time() * 1000) - 5000)
        c.publish(topics.request(topics.DEFAULT_PREFIX, client_id, sid), stale.SerializeToString(), qos=1)
        assert got.wait(5)
        assert replies[0].code == grpc.StatusCode.DEADLINE_EXCEEDED.value[0]
        assert not ran.wait(0.5) and server.stale_refused == 1

        # The same call with a live deadline runs normally.
        got.clear()
        fresh = Frame(kind=Frame.REQUEST, call_id=2, method_id=topics.method_id(method("Act")), payload=b"x",
                      timeout_ms=2000, deadline_unix_ms=int(time.time() * 1000) + 2000)
        c.publish(topics.request(topics.DEFAULT_PREFIX, client_id, sid), fresh.SerializeToString(), qos=1)
        assert got.wait(5) and ran.wait(1)
        assert replies[-1].code == 0 and replies[-1].payload == b"done"
    finally:
        c.loop_stop()
        c.disconnect()
        server.stop(0).wait(5)


def test_stats_count_mqtt_bytes(rig):
    server, channel, _ = rig
    before = channel.stats()
    assert channel.unary_unary(method("Echo"))(b"hello", timeout=5) == b"hello"
    after = channel.stats()
    assert after["msgs_out"] - before["msgs_out"] == 1   # the request
    assert after["msgs_in"] - before["msgs_in"] >= 1     # the response (+ maybe the retained presence)
    assert after["bytes_out"] - before["bytes_out"] > len(b"hello") + 20


def test_topic_aliases_shrink_repeat_messages(rig):
    """MQTT 5 topic aliases: after the first request, the topic string is replaced by a 2-byte alias."""
    _, channel, _ = rig
    echo = channel.unary_unary(method("Echo"))
    sizes = []
    for _ in range(3):
        before = channel.stats()["bytes_out"]
        assert echo(b"x", timeout=5) == b"x"
        sizes.append(channel.stats()["bytes_out"] - before)
    topic_len = len(f"grpb/req/{channel.client_id}/{channel.server_id}/pb")
    assert sizes[1] == sizes[2] and sizes[0] - sizes[1] >= topic_len - 3


def test_calls_survive_broker_restart_with_aliases(tmp_path):
    """Aliases belong to one connection; after the broker restarts, both sides must reset them."""
    import subprocess

    from conftest import _find_mosquitto, _free_port
    exe = _find_mosquitto()
    if exe is None:
        pytest.skip("mosquitto not installed")
    port = _free_port()
    conf = tmp_path / "m.conf"
    conf.write_text(f"listener {port} 127.0.0.1\nmax_topic_alias 1000\nallow_anonymous true\npersistence false\n")

    def start():
        p = subprocess.Popen([exe, "-c", str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.5)
        return p

    broker = start()
    sid = uid("srv")
    server = grpb.MqttServer(sid, "127.0.0.1", port, keepalive=5)
    server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(SERVICE, {
        "Echo": grpc.unary_unary_rpc_method_handler(lambda req, ctx: req)}),))
    server.start()
    channel = grpb.MqttChannel(sid, "127.0.0.1", port)
    echo = channel.unary_unary(method("Echo"))
    try:
        for _ in range(3):
            assert echo(b"before", timeout=5, wait_for_ready=True) == b"before"
        broker.terminate()
        broker.wait(5)
        broker = start()
        for _ in range(3):   # reconnect (1-10 s back-off), then aliases are re-established
            assert echo(b"after", timeout=20, wait_for_ready=True) == b"after"
    finally:
        channel.close()
        server.stop(0).wait(5)
        broker.terminate()
        broker.wait(5)
