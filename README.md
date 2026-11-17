# gRPB-M2M

Run your generated gRPC stubs and servicers **over MQTT** with Protobuf encoding, for IoT
devices such as the Raspberry Pi. You keep the typed `.proto` contract and the code that
`grpcio-tools` generates. Only the channel and the server object change, so the same
application code runs over plain gRPC (HTTP/2) or over an MQTT broker.

It also brings Protobuf to **oneM2M**: `grpb.onem2m` encodes oneM2M primitives in Protobuf,
and a small patch teaches the ACME CSE a new `pb` serialization next to JSON and CBOR. See
[context.md](context.md) for the design.

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
| Stale requests (arriving after the client's deadline) refused, not executed | yes (`clock_skew_ms=500`; needs roughly synced clocks, `None` disables) |
| Traffic counters: `channel.stats()`, `server.stats()` | exact MQTT bytes and messages per connection |
| MQTT 5 topic aliases, both directions | yes, on by default (`topic_aliases=False` turns off); about 40 B saved per message |
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
- **Topic aliases:** after the first message on a topic, client and broker replace the topic string
  with a 2-byte number (MQTT 5), in both directions. Aliases are reset on every reconnect. Mosquitto
  allows 10 per client by default; `config/mosquitto.conf` raises that to 1000 for servers with many clients.
- **Expiry:** requests carry an MQTT 5 message expiry, so the broker never delivers a stale
  request. This needs no clock sync between devices.

## oneM2M with Protobuf (ACME)

[proto/grpb/onem2m/onem2m.proto](proto/grpb/onem2m/onem2m.proto) models the common primitive
parameters and the AE, container, content instance, subscription and notification resources
as typed fields. Anything it doesn't model travels losslessly as compact JSON in an `ext`
field, so `decode(encode(p)) == p` for every primitive. The proposed media type is
`application/vnd.onem2m-res+protobuf`, which is our proposal, not an official oneM2M type.

```python
from grpb.onem2m.client import Onem2mClient      # JSON, CBOR (pip install "grpb-m2m[cbor]") or Protobuf

with Onem2mClient("Csensor1", serialization="pb", host="broker.local") as c:
    c.request(1, "cse-in", ty=2, pc={"m2m:ae": {"rn": "sensor1", "api": "Nsensor", "rr": True, "srv": ["5"],
                                              "poa": [c.poa], "csz": [c.media_type]}})
    c.request(1, "cse-in/sensor1", ty=3, pc={"m2m:cnt": {"rn": "temp"}})
    r = c.request(1, "cse-in/sensor1/temp", ty=4, pc={"m2m:cin": {"con": "23.5"}})
```

Registering with `csz` set to the Protobuf media type makes ACME send that AE's notifications in
Protobuf too. HTTP/JSON clients keep reading the same resources unchanged.

**The ACME patch** ([patches/acme-protobuf.patch](patches/acme-protobuf.patch), about 25 lines)
adds the `PROTOBUF` serialization, the `pb` MQTT topic segment and the media type, and calls the
shared codec. [scripts/patch-acme.sh](scripts/patch-acme.sh) applies it to ACME 2026.05.1 and
copies the codec in (`make setup` runs it; `make acme-patch` reruns it). A test fails if the two
copies of the codec ever differ.

## Collecting evidence: Protobuf vs JSON vs CBOR

```sh
make bench ARGS="codec --label laptop"           # size + CPU per format, real ACME primitives, no network
make cse ARGS="--headless --log-level warn"      # (with make broker) quiet logs: debug hex-dumps binary formats
make bench ARGS="e2e --n 300 --label laptop"     # device -> broker -> ACME -> device, formats interleaved
make bench ARGS="report results/* --out results/REPORT.md"
```

Each run writes `results/<time>-<kind>-<label>/` with `samples.csv` (every measurement),
`summary.csv`, `summary.md` and `env.json` (machine, versions, broker, arguments). Add `--no-save`
to only print the summary, e.g. for a quick check: `make bench ARGS="e2e --n 20 --no-save"`. Run the same
commands on a Pi (`GRPB_BROKER_HOST=<laptop>`) to measure over Wi-Fi and on constrained CPUs.

## Simulations: three apps, many nodes, one Pi

[docs/SIMULATIONS.md](docs/SIMULATIONS.md) describes three mock applications that run many simulated
nodes on one Raspberry Pi and record a data point for every claim:

| App | Shows | Compares |
|---|---|---|
| **FarmNet**: sensor fleet through oneM2M | bytes per reading, fleet MB/day, CSE load, JSON interop | Protobuf vs CBOR vs JSON |
| **PulseWatch**: high-rate streams to several viewers | throughput, delivery, delay | gRPB-M2M vs gRPC/HTTP/2 vs JSON over MQTT |
| **SafeSwitch**: commands while actuators crash or freeze | fail-fast time, controller blocking, stale commands | gRPB-M2M vs gRPC/HTTP/2 vs JSON over MQTT |

```sh
make sim S=farmnet ARGS="--nodes 50 --format pb"     # one run (needs make broker + make cse)
make sim S=safeswitch ARGS="--transport json --scenario freeze"
make dashboard                                        # FarmNet data read back over HTTP/JSON, port 8090
make evidence                                         # every app x format x transport x network, then charts
```

## This repository

```
grpb/                  the library (what pip installs)
proto/grpb/wire.proto  the gRPC-over-MQTT wire format
proto/grpb/onem2m/     oneM2M primitives in Protobuf (codec in grpb/onem2m/)
patches/               the ACME Protobuf patch
results/               benchmark runs (raw samples + summaries)
tests/                 library, codec and ACME tests, against a private Mosquitto and ACME
examples/              grpb-examples package: sample apps, simulations and the Pi hardware layer
  grpb_examples/hal.py             DS18B20 + GPIO relay on a Pi, simulated elsewhere
  grpb_examples/temperature/       hub, sensor, fan; run over --transport mqtt|grpc
  grpb_examples/sim/               FarmNet, PulseWatch, SafeSwitch, sweeps, charts, dashboard
  proto/                           the sample apps' .proto files
  tests/                           the sample app over both transports; the simulations
tools/                 bench.py (evidence), sniff.py (frames on the wire), m1_smoke.py (oneM2M JSON check)
config/, scripts/      broker and ACME config; setup, run and evidence scripts (run-evidence.sh)
vendor/acme            ACME CSE 2026.05.1 (cloned and patched by setup)
```

### Laptop setup

Needs `git`, [`uv`](https://docs.astral.sh/uv/), and Homebrew (macOS) or apt (Linux).

```sh
make setup      # ACME, Mosquitto, .venv (Python 3.13) with library + examples + dev tools
make test       # 77 tests; starts its own broker and ACME
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
