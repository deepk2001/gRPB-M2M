# gRPB-M2M

Run your generated gRPC stubs and servicers **over MQTT** with Protobuf encoding, for IoT
devices such as the Raspberry Pi. You keep the typed `.proto` contract and the code that
`grpcio-tools` generates. Only the channel and the server object change, so the same
application code runs over plain gRPC (HTTP/2) or over an MQTT broker.

The next step, oneM2M integration (ACME CSE with a Protobuf binding), is planned; see
[context.md](context.md).

## Install

```sh
pip install grpb-m2m              # the library: grpcio, protobuf, paho-mqtt
pip install "grpb-m2m[codegen]"   # plus grpcio-tools, to generate stubs from your .proto files
```

Until it is published, install the wheel built by `make build`:
`pip install dist/grpb_m2m-0.1.0-py3-none-any.whl`.

You need an MQTT broker that both sides can reach, e.g. Mosquitto.

## Use

Generate code from your service as usual:

```sh
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. greeter.proto
```

Server, where you would have used `grpc.server()`:

```python
import grpb
import greeter_pb2 as pb, greeter_pb2_grpc as pb_grpc

class Greeter(pb_grpc.GreeterServicer):
    def Hello(self, request, context):
        return pb.HelloReply(text=f"hello {request.name}")

server = grpb.MqttServer("greeter", host="broker.local")     # server ID + broker
pb_grpc.add_GreeterServicer_to_server(Greeter(), server)
server.start()
server.wait_for_termination()
```

Client, where you would have used `grpc.insecure_channel()`:

```python
with grpb.MqttChannel("greeter", host="broker.local") as channel:
    stub = pb_grpc.GreeterStub(channel)
    print(stub.Hello(pb.HelloRequest(name="Pi"), timeout=5).text)
```

Errors are raised as `grpc.RpcError` with the usual `code()` and `details()`.

### What is supported

| Feature | Status |
|---|---|
| Unary calls, server streaming | yes |
| Client and bidirectional streaming | not yet (raises `UNIMPLEMENTED`) |
| Status codes, `context.abort()`, handler exceptions → `UNKNOWN` | yes |
| Deadlines (`timeout=`), `context.time_remaining()` | yes |
| Invocation metadata | yes (no initial/trailing metadata) |
| `wait_for_ready=True` | waits for the server to come online |
| Cancellation (`call.cancel()`, closed channel, crashed device) | reaches the server; `add_callback` runs |
| `.future()`, `.with_call()` | yes |
| TLS / broker authentication | not yet (use a trusted network) |

### How it works

Each call is a small Protobuf `Frame` ([proto/grpb/wire.proto](proto/grpb/wire.proto))
carrying a call ID, a 4-byte method ID (CRC-32 of the method name), the serialized
message, a status code and a timeout. The topics follow oneM2M's MQTT binding (TS-0010),
with a `pb` format segment:

| Topic | Direction |
|---|---|
| `grpb/req/<client-id>/<server-id>/pb` | requests and cancels, client → server |
| `grpb/resp/<client-id>/<server-id>/pb` | responses and stream items, server → client |
| `grpb/presence/<id>` | `online` / `offline` (retained for servers; MQTT Last Will) |

- **Presence:** a server publishes a retained `online` message, with `offline` as its
  Last Will. Calls fail fast with `UNAVAILABLE` while the server is offline, or wait for it
  with `wait_for_ready=True`.
- **Dead clients:** a device that crashes or loses power triggers its Last Will, and the
  server cancels its open streams.
- **Expiry:** requests carry an MQTT 5 message expiry, so the broker never delivers a stale
  request. This needs no clock sync between devices.

## This repository

```
grpb/                  the library (what pip installs)
proto/grpb/wire.proto  the wire format
tests/                 library tests, against a private Mosquitto
examples/              grpb-examples package: sample apps and the Pi hardware layer
  grpb_examples/hal.py             DS18B20 + GPIO relay on a Pi, simulated elsewhere
  grpb_examples/temperature/       hub, sensor, fan; run over --transport mqtt|grpc
  proto/                           the sample apps' .proto files
  tests/                           the sample app over both transports
tools/                 sniff.py (frames on the wire), m1_smoke.py (oneM2M JSON check)
config/, scripts/      broker and ACME config; setup and run scripts
vendor/acme            ACME CSE 2026.05.1 (cloned by setup, patched for Protobuf later)
```

### Laptop setup

Needs `git`, [`uv`](https://docs.astral.sh/uv/), and Homebrew (macOS) or apt (Linux).

```sh
make setup      # ACME, Mosquitto, .venv (Python 3.13) with library + examples + dev tools
make test       # 25 tests; starts its own broker
make build      # dist/grpb_m2m-0.1.0-py3-none-any.whl and .tar.gz
```

### Temperature demo

```sh
make broker                                        # terminal 1
make hub                                           # terminal 2
make fan    ARGS="--sensor s2 --on 25 --off 23"    # terminal 3
make sensor ARGS="--id s1 --seed 1"                # terminal 4
make sensor ARGS="--id s2 --seed 2"                # terminal 5
make sniff                                         # optional: frames and sizes on the wire
```

Add `T=grpc` to `hub`, `sensor` and `fan` to run the same app over plain gRPC instead,
which needs no broker.

### Raspberry Pi

64-bit Raspberry Pi OS. The broker and the hub run on the laptop.

```sh
git clone <this repo> && cd gRPB-M2M
make setup-pi
export GRPB_BROKER_HOST=<laptop LAN IP>
make hal
make sensor ARGS="--id pi1"
```

With no sensor attached, or with `GRPB_SIM=1`, the Pi uses the simulator.

### oneM2M check (M1)

`make broker`, `make cse`, then `make smoke`: JSON over MQTT into ACME, read back over HTTP.

### Settings (environment variables)

| Variable           | Default                      | Meaning                               |
|--------------------|------------------------------|---------------------------------------|
| `GRPB_BROKER_HOST` | `127.0.0.1`                  | MQTT broker host                      |
| `GRPB_BROKER_PORT` | `1883`                       | MQTT broker port                      |
| `GRPB_SERVER_ID`   | `hub`                        | gRPB-M2M server ID the examples use   |
| `GRPB_TRANSPORT`   | `mqtt`                       | example transport: `mqtt` or `grpc`   |
| `GRPB_GRPC_TARGET` | `<broker host>:50051`        | hub address for `--transport grpc`    |
| `GRPB_CSE_ID`      | `id-in`                      | CSE-ID used in oneM2M MQTT topics     |
| `GRPB_CSE_NAME`    | `cse-in`                     | CSEBase resource name                 |
| `GRPB_CSE_HTTP`    | `http://<broker host>:8080`  | CSE HTTP endpoint (interop reads)     |
| `GRPB_SIM`         | auto (on unless on a Pi)     | force simulator on/off                |
| `GRPB_RELAY_PIN`   | `17`                         | BCM pin of the relay/LED              |

The demo broker allows anonymous connections and ACME's access checks are off. Use them
only on a trusted network.
