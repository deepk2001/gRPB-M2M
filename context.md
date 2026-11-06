# Project context: gRPB-M2M (oneM2M hackathon)

## Summary
gRPB-M2M is a hackathon project that brings gRPC-style typed contracts and Protobuf
binary encoding to oneM2M IoT systems, carried over MQTT instead of HTTP/2.
Developers define device data and operations in .proto files; a Python library
generates typed stubs, and each typed call (e.g. ReportReading()) becomes a standard
oneM2M request primitive encoded as Protobuf.

## Team
- Team name: Nittany Nerds (Penn State)
- Lead: Deep Hiren Kotecha (M.S. CSE)
- Members being added: Ruhan Malli (CMPSC), Yi Gao (CMPEN), Tharun
- Project status: planning complete, implementation not started.

## Problem being solved
- oneM2M deployments mostly use text JSON: oversized messages waste bandwidth and
  battery on constrained devices.
- No enforced schema between device and server: format mismatches surface at runtime.
- gRPC/Protobuf solve both in mainstream software, but gRPC needs HTTP/2 (heavy for
  IoT) and has no oneM2M integration.

## Architecture (current plan)
1. Devices: Raspberry Pi (64-bit Raspberry Pi OS), Python, running the gRPB-M2M
   client library. Diverse IoT applications; the sample app is temperature monitoring.
2. Broker: Mosquitto (MQTT).
3. Platform: ACME CSE (open-source Python oneM2M server, github.com/ankraft/ACME-oneM2M-CSE),
   patched to accept Protobuf as a new serialization alongside JSON and CBOR.
   The rest of ACME is unchanged, so existing HTTP/JSON clients read the same data.
4. Fallback (only if the ACME patch fails): an external gateway that translates
   Protobuf-over-MQTT into HTTP/JSON calls against an unmodified ACME.

## Key technical decisions
- Language: Python. Packages: grpcio, grpcio-tools, protobuf, paho-mqtt>=2.0
  (MQTT v5). aiomqtt optional for the fallback gateway.
- Python's grpcio is hardwired to HTTP/2, so we keep the generated stubs and swap the
  transport: a custom "fake channel" object is passed to generated stubs and sends
  calls over MQTT. Fallback: own RPC layer on the generated message classes.
- Topics follow oneM2M's MQTT binding (TS-0010) with a new format segment "pb":
  requests /oneM2M/req/<originator>/<cse-id>/pb, responses /oneM2M/resp/<originator>/<cse-id>/pb,
  first registration via reg_req/reg_resp topics. IDs containing "/" must be encoded.
- Request/response matching uses the oneM2M request ID (rqi) in the message body, not
  MQTT 5 properties (that's how ACME's MQTT binding works). Deadlines use rqet plus a
  local timeout.
- Proposed media type: application/vnd.onem2m-res+protobuf (our proposal, not official).
- Method-to-oneM2M mapping (operation, resource type, target path) is defined with
  custom options on RPC methods in the .proto files.
- Devices register AEs with Protobuf in csz and an mqtt:// point of access, so ACME
  sends them notifications in Protobuf over MQTT.

## ACME patch (pinned to ACME version 2026.05.1)
- acmecse/etc/Types.py: add PROTOBUF to ContentSerializationType (at end of enum);
  short name "pb"; add to supportedContentSerializationsSimple() (gates MQTT topics)
  and supportedContentSerializations() (gates AE csz validation).
- acmecse/etc/RequestUtils.py: Protobuf branches in serializeData()/deserializeData().
- New acmecse/etc/ProtoCodec.py: Protobuf bytes <-> ACME dicts; maps cin <-> m2m:cin
  (Protobuf names can't contain colons); drops unset fields; ignores unmodeled attributes.
- New acmecse/etc/onem2m_pb2.py: generated, checked in.
- Optional: Protobuf logging branch in acmecse/plugins/bindings/MQTTClient.py.

## Schema notes
- onem2m.proto: one Primitive message for requests and responses, fields named after
  oneM2M short names (op, to, fr, rqi, ty, rvi, rsc, rqet, pc). pc is a oneof over AE,
  Container, ContentInstance, Subscription, Notification.
- Use 32-bit integers (Protobuf's dict conversion turns 64-bit ints into strings).

## Device library modules (grpb/)
config, topics, codec, transport (MQTT, pending-calls table keyed by rqi, deadline
sweep), mapping (bindings read from .proto options), channel (fake gRPC channel),
errors (oneM2M rsc -> gRPC status codes), notify (notification dispatcher; must answer
subscription verification requests), provision (idempotent AE/container/subscription
setup), instrument (timing and size hooks for benchmarks).

## Sample app: temperature monitoring
- Sensor Pis call ReportReading(); ACME stores each reading as a contentInstance.
- A oneM2M subscription notifies a fan controller Pi, which applies a threshold with
  hysteresis and drives a relay/LED.
- A plain HTTP/JSON client reads the same data from ACME: the interoperability proof.
- Simulated sensors share the same code as a hardware fallback.

## Evaluation plan
Compare JSON, CBOR and Protobuf over the same broker and patched ACME, plus a plain
gRPC-over-HTTP/2 baseline; optionally ASN.1 unaligned PER for size.
Metrics: bytes per message, median and p99 latency, throughput, delivery after
disconnect/reconnect. Run with broker co-located and on a separate machine.

## Framing rules (keep claims honest)
- All benefits are hypotheses until measured.
- Do not claim gRPB-M2M beats gRPC over HTTP/2 on latency (MQTT adds broker hops);
  it trades some latency for IoT features (offline delivery, Last Will, push
  notifications through NAT).
- Do not claim Protobuf is smaller than ASN.1 PER. The differentiator is typed service
  contracts + mainstream tooling + oneM2M mapping, not serialization alone.
- Standardization claim = "contribution-ready proposal with a reference
  implementation," not a finished standard.
- Prior art to cite: awakesecurity/grpc-mqtt (Haskell), golain-io/mqtt-bridge (Go);
  neither is Python or oneM2M-aware.

## Milestones
M1 ACME runs with MQTT; Pi creates a resource via JSON over MQTT.
M2 Patched ACME accepts a Protobuf CREATE and replies in Protobuf (go/no-go point).
M3 Typed stubs, rqi matching, timeouts, notifications.
M4 Temperature app end to end, including the HTTP/JSON dashboard read.
M5 Benchmarks, charts, draft spec (spec/grpb-m2m-spec.md).

## Glossary
CSE: oneM2M server. AE: application entity (a registered device/app).
cin: contentInstance (one stored reading). sub: subscription. rqi: request ID.
rsc: response status code. rqet: request expiration. csz: an AE's supported
serializations. poa: point of access.