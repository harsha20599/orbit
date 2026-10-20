"""Windows: the built-in screen's brightness (laptops), through WMI.

WmiMonitorBrightness / WmiMonitorBrightnessMethods (root\\wmi) control the internal
panel without admin. External monitors don't support it (Twinkle Tray, DDC/CI, handles
those). One PowerShell process stays open and takes commands on stdin, so each step
costs a few milliseconds instead of starting PowerShell every time.
"""
from __future__ import annotations

import logging
import subprocess
import threading

log = logging.getLogger("orbit.brightness")

_GET = "try { (Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness -ErrorAction Stop | " \
       "Select-Object -First 1).CurrentBrightness } catch { 'none' }"
_SET = "try {{ Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightnessMethods -ErrorAction Stop | " \
       "ForEach-Object {{ Invoke-CimMethod -InputObject $_ -MethodName WmiSetBrightness " \
       "-Arguments @{{Timeout=1; Brightness=[byte]{v}}} | Out-Null }}; 'ok' }} catch {{ 'none' }}"
_END = "__orbit_end__"


class InternalBrightness:
    def __init__(self):
        self._p: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self.supported: bool | None = None       # None: not asked yet

    def _run(self, cmd: str) -> str:
        with self._lock:
            if self._p is None or self._p.poll() is not None:
                self._p = subprocess.Popen(
                    ["powershell", "-NoProfile", "-NoLogo", "-NonInteractive", "-Command", "-"],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, bufsize=1, creationflags=0x08000000)          # CREATE_NO_WINDOW
            self._p.stdin.write(f"{cmd}; '{_END}'\n")
            self._p.stdin.flush()
            out = []
            for line in self._p.stdout:
                line = line.strip()
                if line == _END:
                    break
                if line:
                    out.append(line)
            return out[-1] if out else ""

    def get(self) -> float | None:
        if self.supported is False:
            return None
        try:
            r = self._run(_GET)
            v = float(r)
        except (ValueError, OSError):
            v = None
        if self.supported is None:
            self.supported = v is not None
            log.info("built-in screen brightness: %s", "yes" if self.supported else "not on this computer")
        return v

    def set(self, value: float) -> bool:
        if self.supported is None:
            self.get()
        if not self.supported:
            return False
        try:
            return self._run(_SET.format(v=int(round(max(0, min(100, value)))))) == "ok"
        except OSError:
            return False

    def close(self):
        with self._lock:
            if self._p and self._p.poll() is None:
                self._p.kill()
