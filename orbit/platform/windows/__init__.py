"""Windows backend.

Sources
  VolumeRotationSource   rotation   (AVRCP absolute volume on the buds endpoint)
  MediaButtonSource      clicks     (AVRCP play/pause/next/prev via our own SMTC session)
  BluetoothPacketSource  hold       (HFP AT+BVRA from raw HCI via ETW, admin only)
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path

from orbit.platform.base import Platform
from orbit.platform.windows import etw


def cache_dir() -> Path:
    import os
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Orbit"


class WindowsPlatform(Platform):
    name = "windows"

    def __init__(self):
        self._media = None

    def create_sources(self, cfg):
        from orbit.platform.windows.input_bt import BluetoothPacketSource
        from orbit.platform.windows.input_media import MediaButtonSource
        from orbit.platform.windows.input_volume import VolumeRotationSource

        self._media = MediaButtonSource(cache_dir())
        self._volume = VolumeRotationSource(cfg["device"]["audio_endpoint_match"])
        return [self._volume, self._media, BluetoothPacketSource()]

    def create_services(self, cfg):
        from orbit.platform.windows.flyout import FlyoutSuppressor

        f = FlyoutSuppressor(self._volume.last_activity)
        f.enabled = bool(cfg["ui"]["hide_os_volume_flyout"])
        f.toggle_label = "Hide Windows volume bar"
        return [f]

    def create_key_capture(self, router):
        from orbit.platform.windows.input_keys import WindowsKeyCapture
        return WindowsKeyCapture(router)

    def create_output(self, cfg):
        from orbit.platform.windows.output import WindowsOutput
        return WindowsOutput(media_source=self._media)

    def is_elevated(self):
        return etw.is_admin()

    def relaunch_elevated(self, argv):
        params = subprocess.list2cmdline(argv)
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        return rc > 32
