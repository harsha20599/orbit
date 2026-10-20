"""macOS: dial rotation via the buds' output volume (CoreAudio).

Thin backend for orbit.core.volume_dial.VolumeDial. CoreAudio has no
"who changed it" context, so our own sets are recognised by value: a change
landing on the level we just set, within OURS_S, is ours.
"""
from __future__ import annotations

import logging
import threading
import time

from orbit.core.events import Capability
from orbit.core.volume_dial import VolumeDial
from orbit.platform.base import Emit, RotationSource
from orbit.platform.mac import coreaudio as ca

log = logging.getLogger("orbit.volume")
trace = logging.getLogger("orbit.trace")

OURS_S = 0.5
OURS_EPS = 0.004


class MacVolumeRotationSource(RotationSource):
    name = "coreaudio-volume"
    capabilities = frozenset({Capability.ROTATE})

    def __init__(self, match: str):
        self.match = match
        self.dial: VolumeDial | None = None
        self._dev: int | None = None
        self._listener = None
        self._devices_listener = None
        self._our: tuple[float, float] | None = None   # (level, time) of our last set
        self._rebind = threading.Event()
        self._stop = threading.Event()

    # ---- RotationSource
    def start(self, emit: Emit):
        self.dial = VolumeDial(self, emit, self.name)
        try:
            self._devices_listener = ca.add_devices_listener(self._rebind.set)
        except OSError:
            log.exception("device-list listener failed; reconnects need a restart")
        self._bind()
        self.dial.start()
        threading.Thread(target=self._device_loop, name="coreaudio-devices", daemon=True).start()

    def stop(self):
        if self.dial:
            self.dial.stop()
        self._stop.set()
        self._rebind.set()
        if self._listener:
            ca.remove_volume_listener(self._listener)
            self._listener = None
        if self._devices_listener:
            ca.remove_devices_listener(self._devices_listener)
            self._devices_listener = None

    def set_passthrough(self, on):
        if self.dial:
            self.dial.set_passthrough(on)

    def set_duck(self, factor):
        if self.dial:
            self.dial.set_duck(factor)

    def level(self):
        return self.dial.level() if self.dial else None

    def nudge(self, steps):
        if self.dial:
            self.dial.nudge(steps)

    def last_activity(self) -> float:
        return self.dial.last_activity() if self.dial else 0.0

    def describe(self):
        return f"{self.name} on {ca.name(self._dev) if self._dev else 'no device yet'}"

    # ---- LevelBackend
    def get_level(self):
        return ca.get_volume(self._dev) if self._dev else None

    def set_level(self, level):
        if self._dev:
            self._our = (level, time.monotonic())
            ca.set_volume(self._dev, level)

    # ---- CoreAudio
    def _on_volume(self):              # HAL thread
        lvl = self.get_level()
        if lvl is None or not self.dial:
            return
        ours = bool(self._our and abs(lvl - self._our[0]) < OURS_EPS
                    and time.monotonic() - self._our[1] < OURS_S)
        trace.debug("mac  vol=%5.1f %s", lvl * 100, "ours" if ours else "")
        try:
            self.dial.on_level(lvl, ours)
        except Exception:
            log.exception("dial update failed")

    def _bind(self):
        if self._listener:
            ca.remove_volume_listener(self._listener)
            self._listener = None
        self._dev = ca.find_output(self.match)
        if self._dev is None:
            log.warning("no output device matching '%s' — rotation unavailable until it connects", self.match)
            return
        self._listener = ca.add_volume_listener(self._dev, self._on_volume)
        if self.dial:
            self.dial.rebase()
        log.info("rotation bound to '%s' (level %.0f%%)", ca.name(self._dev), (self.get_level() or 0) * 100)

    def _device_loop(self):
        while not self._stop.is_set():
            self._rebind.wait()
            if self._stop.is_set():
                return
            self._rebind.clear()
            time.sleep(0.5)          # the buds' device appears before its volume control is ready
            try:
                self._bind()
            except Exception:
                log.exception("rebind failed")
