"""Windows: dial rotation via the buds' render-endpoint volume.

Thin backend for orbit.core.volume_dial.VolumeDial (all click logic lives there).
IAudioEndpointVolumeCallback reports every change with an event-context GUID; our
own sets carry OUR_CONTEXT, which is how we tell them from the dial's.
"""
from __future__ import annotations

import ctypes
import logging
import threading
import time
import uuid
import warnings

import comtypes
from pycaw.callbacks import AudioEndpointVolumeCallback, MMNotificationClient
from pycaw.pycaw import AudioUtilities

from orbit.core.events import Capability
from orbit.core.volume_dial import VolumeDial
from orbit.platform.base import Emit, RotationSource

log = logging.getLogger("orbit.volume")
trace = logging.getLogger("orbit.trace")
warnings.filterwarnings("ignore", module="pycaw")

OUR_CONTEXT = comtypes.GUID("{" + str(uuid.UUID("5f0c2a1e-6d3b-4c9a-9a47-0b1e7a1d1a11")) + "}")


class _VolCb(AudioEndpointVolumeCallback):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def on_notify(self, new_volume, new_mute, event_context, channels, channel_volumes):
        ours = event_context.contents == OUR_CONTEXT
        trace.debug("win  vol=%5.1f %s", new_volume * 100, "ours" if ours else "")
        self.owner.dial.on_level(new_volume, ours)


class _DevCb(MMNotificationClient):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def on_device_state_changed(self, *a):
        self.owner._rebind.set()

    def on_device_added(self, *a):
        self.owner._rebind.set()

    def on_device_removed(self, *a):
        self.owner._rebind.set()

    def on_default_device_changed(self, *a): ...
    def on_property_value_changed(self, *a): ...


class VolumeRotationSource(RotationSource):
    name = "avrcp-volume"
    capabilities = frozenset({Capability.ROTATE})

    def __init__(self, match: str):
        self.match = match.lower()
        self.dial: VolumeDial | None = None
        self._dev = None            # (AudioDevice, callback)
        self._rebind = threading.Event()
        self._stop = threading.Event()
        self._dev_cb = None

    # ---- RotationSource
    def start(self, emit: Emit):
        self.dial = VolumeDial(self, emit, self.name)
        threading.Thread(target=self._device_loop, name="volume-devices", daemon=True).start()

    def stop(self):
        if self.dial:
            self.dial.stop()
        self._stop.set()
        self._rebind.set()

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
        return f"{self.name} on {self._dev[0].FriendlyName if self._dev else 'no device yet'}"

    # ---- LevelBackend (called from the dial's worker thread)
    def thread_init(self):
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)

    def get_level(self):
        try:
            return self._dev[0].EndpointVolume.GetMasterVolumeLevelScalar() if self._dev else None
        except Exception:
            return None

    def set_level(self, level):
        if self._dev:
            self._dev[0].EndpointVolume.SetMasterVolumeLevelScalar(level, ctypes.byref(OUR_CONTEXT))

    # ---- device binding
    def _bind(self):
        if self._dev:
            try:
                self._dev[0].EndpointVolume.UnregisterControlChangeNotify(self._dev[1])
            except Exception:
                pass
            self._dev = None
        coll = AudioUtilities.GetDeviceEnumerator().EnumAudioEndpoints(0, 1)  # eRender, ACTIVE
        for i in range(coll.GetCount()):
            dev = AudioUtilities.CreateDevice(coll.Item(i))
            if self.match in (dev.FriendlyName or "").lower():
                cb = _VolCb(self)
                dev.EndpointVolume.RegisterControlChangeNotify(cb)
                self._dev = (dev, cb)
                break
        if self._dev:
            self.dial.rebase()
            log.info("rotation bound to '%s' (level %.0f%%)", self._dev[0].FriendlyName, (self.get_level() or 0) * 100)
        else:
            log.warning("no active audio output matching '%s' — dial rotation unavailable until it connects", self.match)

    def _device_loop(self):
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        self._dev_cb = _DevCb(self)
        AudioUtilities.GetDeviceEnumerator().RegisterEndpointNotificationCallback(self._dev_cb)
        try:
            self._bind()
        except Exception:
            log.exception("bind failed")
        self.dial.start()
        while not self._stop.is_set():
            self._rebind.wait()
            if self._stop.is_set():
                break
            self._rebind.clear()
            time.sleep(0.3)  # let the driver settle after connect
            try:
                self._bind()
            except Exception:
                log.exception("bind failed")
