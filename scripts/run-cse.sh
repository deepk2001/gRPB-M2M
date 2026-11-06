#!/usr/bin/env bash
# Run the ACME CSE in the foreground. Runtime data (logs, DB) goes to runtime/cse/.
# Extra arguments are passed to ACME, e.g. --log-level info.
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p runtime/cse
cp config/acme.ini runtime/cse/acme.ini
exec .venv/bin/acmecse --base-directory runtime/cse "$@"
