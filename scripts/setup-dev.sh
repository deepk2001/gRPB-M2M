#!/usr/bin/env bash
# One-time setup for the machine that hosts the broker and the CSE (macOS or Linux laptop).
# It also lets this machine act as a simulated Pi.
set -euo pipefail
cd "$(dirname "$0")/.."

ACME_TAG=2026.05.1

if [[ ! -d vendor/acme ]]; then
  echo "==> Cloning ACME CSE $ACME_TAG into vendor/acme"
  git clone -q --depth 1 --branch "$ACME_TAG" https://github.com/ankraft/ACME-oneM2M-CSE.git vendor/acme
fi

if ! command -v mosquitto >/dev/null && [[ ! -x /opt/homebrew/opt/mosquitto/sbin/mosquitto && ! -x /usr/local/opt/mosquitto/sbin/mosquitto ]]; then
  echo "==> Installing Mosquitto"
  if command -v brew >/dev/null; then
    brew install mosquitto
  elif command -v apt-get >/dev/null; then
    sudo apt-get install -y mosquitto mosquitto-clients
    sudo systemctl disable --now mosquitto  # we run our own instance with config/mosquitto.conf
  else
    echo "Install Mosquitto manually, then rerun." >&2; exit 1
  fi
fi

if ! command -v uv >/dev/null; then
  echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2; exit 1
fi

echo "==> Creating .venv (Python 3.13) with the library, the sample apps, the CSE and dev tools"
uv venv --python 3.13 --allow-existing .venv
uv pip install --python .venv -e . -e ./examples -e ./vendor/acme --group dev

echo "==> Done. Next: 'make test', then 'make broker' and 'make hub' / 'make sensor' / 'make fan'."
