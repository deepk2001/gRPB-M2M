#!/usr/bin/env bash
# One-time setup on a Raspberry Pi (64-bit Raspberry Pi OS, Bookworm or Trixie).
# The Pi only runs device code; the broker and the CSE run on the laptop.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Installing system packages"
sudo apt-get update
# gpiozero/lgpio come from apt: the pip builds need compilers and system headers.
sudo apt-get install -y python3-venv python3-dev python3-gpiozero python3-lgpio mosquitto-clients

echo "==> Creating .venv (with system site-packages, so gpiozero is visible)"
python3 -m venv --system-site-packages .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e . -e ./examples

cat <<'EOF'
==> Done.

Hardware (optional; without it the Pi falls back to the simulator):
  DS18B20 sensor: add 'dtoverlay=w1-gpio' to /boot/firmware/config.txt, reboot,
                  wire data to GPIO4 with a 4.7k pull-up to 3.3V.
  Relay/LED:      BCM GPIO17 by default (override with GRPB_RELAY_PIN).

Point the Pi at the laptop (broker + hub run there), then:
  export GRPB_BROKER_HOST=<laptop LAN IP>
  make hal                      # sensor/relay backend check
  make sensor ARGS="--id pi1"   # report readings to the hub over MQTT
  make fan                      # or drive the relay from the hub's stream
EOF
