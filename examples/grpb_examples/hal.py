"""Hardware abstraction for the demo devices.

The sample app only talks to a TemperatureSensor and a Relay. On a real Raspberry Pi these
map to a DS18B20 1-Wire sensor and a GPIO pin (relay or LED); anywhere else, or with
GRPB_SIM=1, they are simulated. The framework code above this layer is identical in both
cases, which is what lets a laptop stand in for a Pi.

Run `python -m grpb_examples.hal` for a quick self-check of whichever backend gets picked.
"""

from __future__ import annotations

import glob
import math
import os
import random
import time
from pathlib import Path
from typing import Protocol


class TemperatureSensor(Protocol):
    def read_celsius(self) -> float: ...


class Relay(Protocol):
    @property
    def is_on(self) -> bool: ...
    def set(self, on: bool) -> None: ...


def is_raspberry_pi() -> bool:
    try:
        return "raspberry pi" in Path("/proc/device-tree/model").read_text().lower()
    except OSError:
        return False


def use_simulator() -> bool:
    forced = os.getenv("GRPB_SIM")
    if forced is not None:
        return forced not in ("0", "false", "no")
    return not is_raspberry_pi()


# --- Simulated hardware ----------------------------------------------------------------


class SimTemperatureSensor:
    """A slow sine wave around `base` plus noise, so a threshold gets crossed in both directions.

    Different `seed`s give different phases, so several simulated sensors don't move in lockstep.
    """

    def __init__(self, base: float = 24.0, swing: float = 4.0, period_s: float = 120.0,
                 noise: float = 0.2, seed: int | None = None) -> None:
        self._base, self._swing, self._period, self._noise = base, swing, period_s, noise
        self._rng = random.Random(seed)
        self._phase = self._rng.uniform(0, 2 * math.pi)
        self._t0 = time.monotonic()

    def read_celsius(self) -> float:
        t = time.monotonic() - self._t0
        value = self._base + self._swing * math.sin(2 * math.pi * t / self._period + self._phase)
        return round(value + self._rng.gauss(0, self._noise), 2)


class SimRelay:
    def __init__(self, name: str = "relay") -> None:
        self._name = name
        self._on = False

    @property
    def is_on(self) -> bool:
        return self._on

    def set(self, on: bool) -> None:
        if on != self._on:
            print(f"[sim] {self._name} -> {'ON' if on else 'OFF'}")
        self._on = on


# --- Real Raspberry Pi hardware --------------------------------------------------------


class Ds18b20Sensor:
    """DS18B20 on the 1-Wire bus (enable with `dtoverlay=w1-gpio` in /boot/firmware/config.txt)."""

    def __init__(self, device_glob: str = "/sys/bus/w1/devices/28-*/temperature") -> None:
        matches = sorted(glob.glob(device_glob))
        if not matches:
            raise RuntimeError(f"no DS18B20 found at {device_glob}; is the w1-gpio overlay enabled?")
        self._path = Path(matches[0])

    def read_celsius(self) -> float:
        return round(int(self._path.read_text().strip()) / 1000.0, 2)


class GpioRelay:
    """A relay module or LED on a BCM GPIO pin, driven through gpiozero."""

    def __init__(self, pin: int) -> None:
        from gpiozero import OutputDevice  # imported lazily: only installed with the [pi] extra

        self._dev = OutputDevice(pin, active_high=True, initial_value=False)

    @property
    def is_on(self) -> bool:
        return bool(self._dev.value)

    def set(self, on: bool) -> None:
        self._dev.on() if on else self._dev.off()


# --- Factories -------------------------------------------------------------------------


def make_sensor(seed: int | None = None) -> TemperatureSensor:
    if use_simulator():
        return SimTemperatureSensor(seed=seed)
    return Ds18b20Sensor()


def make_relay(pin: int | None = None) -> Relay:
    if use_simulator():
        return SimRelay()
    return GpioRelay(pin if pin is not None else int(os.getenv("GRPB_RELAY_PIN", "17")))


if __name__ == "__main__":
    backend = "simulator" if use_simulator() else "Raspberry Pi hardware"
    print(f"HAL backend: {backend}")
    sensor, relay = make_sensor(seed=1), make_relay()
    for _ in range(3):
        print(f"temperature: {sensor.read_celsius()} °C")
        time.sleep(0.5)
    relay.set(True)
    relay.set(False)
    print("HAL self-check OK")
