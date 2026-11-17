#!/usr/bin/env bash
# Collect the full evidence set on this machine (ideally the Raspberry Pi): the three simulations over
# every format / transport, several fleet sizes and rates, and several emulated networks; then charts.
#
#   make broker; make cse ARGS="--headless --log-level warn"     # in other terminals
#   scripts/run-evidence.sh                 # full set (about 2 hours on a Pi 4 with all networks)
#   QUICK=1 scripts/run-evidence.sh         # dry run: short runs, LAN only (about 10 minutes)
#   DUR=30 NETS=lan,4g scripts/run-evidence.sh
#
# Output: results/<time>-evidence-<label>/ with one sweep folder per experiment and charts/.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=${PY:-.venv/bin/python}
SIM="$PY -m grpb_examples.sim"
LABEL=${LABEL:-$(hostname -s)}
QUICK=${QUICK:-0}
if [[ "$QUICK" == 1 ]]; then
  DUR=${DUR:-10}; NETS=${NETS:-lan}
  FARM_NODES=10,50; PULSE_HZ=10,40; SS_DUR=20; SS_FAIL=5; SS_OUT=6
else
  DUR=${DUR:-60}; NETS=${NETS:-lan,wifi,4g,constrained}
  FARM_NODES=10,50,200; PULSE_HZ=5,20,50; SS_DUR=45; SS_FAIL=10; SS_OUT=15
fi
if [[ "$(uname)" != Linux && "$NETS" != lan ]]; then
  echo "network emulation needs Linux (tc netem); measuring on LAN only here" >&2
  NETS=lan
fi
if [[ "$NETS" != lan ]] && ! { [[ $EUID == 0 ]] || sudo -n true 2>/dev/null; }; then
  echo "network emulation needs passwordless sudo for tc (default on Raspberry Pi OS)" >&2
  exit 1
fi

HOST=${GRPB_BROKER_HOST:-127.0.0.1}
CSE=${GRPB_CSE_HTTP:-http://$HOST:8080}
if ! curl -sf -o /dev/null -H "X-M2M-Origin: CAdmin" -H "X-M2M-RI: chk" -H "X-M2M-RVI: 5" "$CSE/cse-in"; then
  echo "CSE not reachable at $CSE: start it with: make cse ARGS=\"--headless --log-level warn\"" >&2
  exit 1
fi

OUT="results/$(date +%Y%m%d-%H%M%S)-evidence-$LABEL"
mkdir -p "$OUT"
export GRPB_RESULTS="$OUT"
echo "evidence -> $OUT  (runs of ${DUR}s, networks: $NETS)"

# 1. FarmNet: bytes, scale and CSE load per format; JSON interop.
$SIM sweep farmnet --label "$LABEL" --vary format=json,cbor,pb --vary nodes=$FARM_NODES --vary netem=$NETS \
  -- --interval 5 --duration "$DUR" --warmup 10

# 2. PulseWatch: streaming throughput and delay per transport.
$SIM sweep pulse --label "$LABEL" --vary transport=grpb,grpc,json --vary hz=$PULSE_HZ --vary netem=$NETS \
  -- --nodes 10 --viewers 3 --duration "$DUR" --warmup 5

# 3. SafeSwitch: failure handling per transport (LAN and the first emulated network).
SS_NETS=lan
[[ "$NETS" == *,* ]] && SS_NETS="lan,$(echo "$NETS" | cut -d, -f2)"
$SIM sweep safeswitch --label "$LABEL" --vary transport=grpb,grpc,json --vary scenario=crash,freeze,none \
  --vary netem=$SS_NETS -- --actuators 20 --groups 4 --duration "$SS_DUR" --fail-at "$SS_FAIL" --outage "$SS_OUT"

$SIM plot "$OUT"/*-sweep-* --out "$OUT/charts" || echo "(charts skipped: pip install matplotlib)"
echo
echo "done: $OUT"
ls "$OUT"
