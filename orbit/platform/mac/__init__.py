"""macOS backend (see docs/research-macos.md for the why behind each choice).

Sources
  MacVolumeRotationSource  rotation  (CoreAudio VirtualMainVolume of the buds' output)
  MacMediaButtonSource     clicks    (MPRemoteCommandCenter while Orbit is "now playing")
  hold                     not observable on macOS: the wheel opens with double press

Output
  MacOutput  Quartz CGEvent keys/scroll (needs Accessibility), AppleScript media
             forwarding to Spotify/Music, DisplayServices / m1ddc brightness, `open`.

Not available on macOS: hiding the system volume HUD, Windows-style window centering,
pressing buttons inside other apps.
"""
from __future__ import annotations

from orbit.platform.base import Platform


class MacPlatform(Platform):
    name = "mac"

    def create_sources(self, cfg):
        from orbit.platform.mac.input_media import MacMediaButtonSource
        from orbit.platform.mac.input_volume import MacVolumeRotationSource
        from orbit.platform.mac.overlay import make_agent_app

        make_agent_app()
        return [MacVolumeRotationSource(cfg["device"]["audio_endpoint_match"]), MacMediaButtonSource()]

    def create_key_capture(self, router):
        from orbit.platform.mac.input_keys import MacKeyCapture
        return MacKeyCapture(router)

    def create_output(self, cfg):
        from orbit.platform.mac.output import MacOutput
        from orbit.platform.mac.overlay import ensure_accessibility

        ensure_accessibility(prompt=True)
        return MacOutput()

    def is_elevated(self):
        return True          # nothing on macOS needs admin

    def relaunch_elevated(self, argv):
        return False
