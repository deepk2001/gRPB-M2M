#!/usr/bin/env bash
# Generate Python message classes (_pb2), type stubs (.pyi) and gRPC stubs (_pb2_grpc).
#   proto/          -> library wire format, e.g. proto/grpb/wire.proto -> grpb/wire_pb2.py
#   examples/proto/ -> sample apps, e.g. .../grpb_examples/temperature/temperature.proto
#                      -> examples/grpb_examples/temperature/temperature_pb2*.py
set -euo pipefail
cd "$(dirname "$0")/.."

PY=${PY:-.venv/bin/python}

# Library: messages only, no gRPC service stubs.
find proto -name '*.proto' -print0 | xargs -0 "$PY" -m grpc_tools.protoc -Iproto --python_out=. --pyi_out=.

# Sample apps: messages and service stubs.
find examples/proto -name '*.proto' -print0 | xargs -0 "$PY" -m grpc_tools.protoc -Iexamples/proto \
  --python_out=examples --pyi_out=examples --grpc_python_out=examples

echo "generated: $(find grpb examples/grpb_examples -name '*_pb2*.py' | tr '\n' ' ')"
