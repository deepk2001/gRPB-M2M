#!/usr/bin/env bash
# Run Mosquitto in the foreground with the project's config.
set -euo pipefail
cd "$(dirname "$0")/.."

MOSQUITTO=$(command -v mosquitto || true)
for p in /opt/homebrew/opt/mosquitto/sbin/mosquitto /usr/local/opt/mosquitto/sbin/mosquitto /usr/sbin/mosquitto; do
  [[ -z "$MOSQUITTO" && -x "$p" ]] && MOSQUITTO=$p
done
[[ -n "$MOSQUITTO" ]] || { echo "mosquitto not found; run scripts/setup-dev.sh" >&2; exit 1; }

exec "$MOSQUITTO" -c config/mosquitto.conf
