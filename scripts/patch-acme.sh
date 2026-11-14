#!/usr/bin/env bash
# Add Protobuf ("pb") serialization to the ACME CSE in vendor/acme.
#   1. apply patches/acme-protobuf.patch (enum, serializers, MQTT topics, dependency) if not applied yet
#   2. copy the shared codec from grpb/onem2m/ into acmecse/etc/ (always, so both sides stay in sync)
# Safe to rerun. `scripts/patch-acme.sh --export` writes the current vendor/acme changes back to the patch.
set -euo pipefail
cd "$(dirname "$0")/.."

ACME=vendor/acme
PATCH=patches/acme-protobuf.patch
FILES=(acmecse/etc/Types.py acmecse/etc/RequestUtils.py acmecse/plugins/bindings/MQTTClient.py setup.py requirements.txt)

[[ -d $ACME/.git ]] || { echo "no ACME checkout at $ACME; run scripts/setup-dev.sh" >&2; exit 1; }

if [[ ${1:-} == --export ]]; then
  git -C "$ACME" diff -- "${FILES[@]}" > "$PATCH"
  echo "wrote $PATCH ($(grep -c '^+[^+]' "$PATCH") added lines)"
  exit 0
fi

if git -C "$ACME" apply --reverse --check "../../$PATCH" 2>/dev/null; then
  echo "==> ACME patch already applied"
else
  git -C "$ACME" apply "../../$PATCH"
  echo "==> Applied $PATCH"
fi

cp grpb/onem2m/codec.py "$ACME/acmecse/etc/ProtoCodec.py"
cp grpb/onem2m/onem2m_pb2.py "$ACME/acmecse/etc/onem2m_pb2.py"
echo "==> Synced ProtoCodec.py and onem2m_pb2.py from grpb/onem2m/"
