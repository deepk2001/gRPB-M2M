"""The temperature sample app, unchanged, over both transports: gRPB-M2M (MQTT) and plain gRPC."""

from __future__ import annotations

import threading
import uuid
from concurrent import futures

import grpc
import pytest

import grpb
from grpb_examples.temperature import temperature_pb2 as pb
from grpb_examples.temperature import temperature_pb2_grpc as pb_grpc
from grpb_examples.temperature.hub import Hub


@pytest.fixture(params=["mqtt", "grpc"])
def stub_and_hub(request, broker):
    hub = Hub()
    if request.param == "mqtt":
        sid = f"hub-{uuid.uuid4().hex[:8]}"
        server = grpb.MqttServer(sid, broker.host, broker.port)
        pb_grpc.add_TemperatureServiceServicer_to_server(hub, server)
        server.start()
        assert server.wait_ready(5)
        channel = grpb.MqttChannel(sid, broker.host, broker.port)
    else:
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
        pb_grpc.add_TemperatureServiceServicer_to_server(hub, server)
        port = server.add_insecure_port("127.0.0.1:0")
        server.start()
        channel = grpc.insecure_channel(f"127.0.0.1:{port}")
    yield pb_grpc.TemperatureServiceStub(channel), hub
    hub.close_watchers()
    channel.close()
    server.stop(0).wait(5)


def rpc_code(fn) -> grpc.StatusCode:
    with pytest.raises(grpc.RpcError) as ei:
        fn()
    return ei.value.code()


def test_get_latest_before_any_reading(stub_and_hub):
    stub, _ = stub_and_hub
    assert rpc_code(lambda: stub.GetLatest(pb.GetLatestRequest(sensor_id="s1"), timeout=5)) is grpc.StatusCode.NOT_FOUND


def test_report_get_and_watch(stub_and_hub):
    stub, hub = stub_and_hub
    stream = stub.WatchReadings(pb.WatchRequest(sensor_id="s1"), timeout=10)
    received: list[pb.Reading] = []
    got_all = threading.Event()

    def consume() -> None:
        for r in stream:
            received.append(r)
            if len(received) == 3:
                got_all.set()
                return

    threading.Thread(target=consume, daemon=True).start()
    for _ in range(100):  # the watcher must be registered before we report
        if hub._watchers:
            break
        threading.Event().wait(0.05)

    acks = [stub.ReportReading(pb.Reading(sensor_id="s1", celsius=20.0 + i, timestamp=1, seq=i), timeout=5)
            for i in (1, 2, 3)]
    stub.ReportReading(pb.Reading(sensor_id="s2", celsius=30.0, timestamp=1, seq=1), timeout=5)
    assert [a.seq for a in acks] == [1, 2, 3] and acks[-1].total_stored == 3

    latest = stub.GetLatest(pb.GetLatestRequest(sensor_id="s1"), timeout=5)
    assert latest.seq == 3 and latest.celsius == pytest.approx(23.0)

    assert got_all.wait(5)
    assert [r.seq for r in received] == [1, 2, 3] and all(r.sensor_id == "s1" for r in received)
    stream.cancel()


def test_invalid_readings_rejected(stub_and_hub):
    stub, _ = stub_and_hub
    assert rpc_code(lambda: stub.ReportReading(pb.Reading(sensor_id="s1", celsius=999.0), timeout=5)) \
        is grpc.StatusCode.INVALID_ARGUMENT
    assert rpc_code(lambda: stub.ReportReading(pb.Reading(celsius=20.0), timeout=5)) \
        is grpc.StatusCode.INVALID_ARGUMENT
