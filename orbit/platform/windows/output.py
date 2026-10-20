"""Windows Output: SendInput keys/scroll, media forwarding, launching."""
from __future__ import annotations

import asyncio
import ctypes
import ctypes.wintypes as wt
import logging
import os
import threading
import time

from orbit.platform.base import Output

log = logging.getLogger("orbit.output")
user32 = ctypes.WinDLL("user32", use_last_error=True)

VK = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "cmd": 0x5B,
    "tab": 0x09, "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "plus": 0xBB, "equals": 0xBB, "minus": 0xBD, "comma": 0xBC, "period": 0xBE, "slash": 0xBF,
    "semicolon": 0xBA, "quote": 0xDE, "backquote": 0xC0, "lbracket": 0xDB, "rbracket": 0xDD,
    "backslash": 0xDC, "printscreen": 0x2C, "capslock": 0x14, "menu": 0x5D,
    "volumeup": 0xAF, "volumedown": 0xAE, "mute": 0xAD,
    "playpause": 0xB3, "nexttrack": 0xB0, "prevtrack": 0xB1, "stop": 0xB2,
}
VK.update({f"f{i}": 0x6F + i for i in range(1, 25)})
VK.update({c: ord(c.upper()) for c in "abcdefghijklmnopqrstuvwxyz0123456789"})
EXTENDED = {0x5B, 0x2E, 0x2D, 0x24, 0x23, 0x21, 0x22, 0x25, 0x26, 0x27, 0x28, 0x5D, 0x2C}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _U)]


ORBIT_TAG = 0x0B17D1A1  # dwExtraInfo marker so our own input is recognisable


def _key(vk, up=False):
    i = INPUT(type=1)
    i.u.ki = KEYBDINPUT(vk, 0, (2 if up else 0) | (1 if vk in EXTENDED else 0), 0, ORBIT_TAG)
    return i


def _send(*inputs):
    arr = (INPUT * len(inputs))(*inputs)
    if user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT)) != len(inputs):
        log.warning("SendInput blocked (err %d) — target may be elevated or secure desktop", ctypes.get_last_error())


def vk_of(name: str) -> int:
    name = name.strip().lower()
    if name not in VK:
        raise ValueError(f"unknown key '{name}'")
    return VK[name]


def _best(name: str, candidates):
    """Exact name, else starts with it, else contains it (case-insensitive)."""
    n = name.lower()
    items = [(c, label.lower()) for c, label in candidates]
    for test in (lambda l: l == n, lambda l: l.startswith(n), lambda l: n in l):
        hits = [c for c, label in items if test(label)]
        if hits:
            return min(hits, key=lambda c: len(str(c)))
    return None


def find_start_menu_app(name: str):
    roots = [os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
             os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")]
    from pathlib import Path
    links = [(p, p.stem) for root in roots if os.path.isdir(root) for p in Path(root).rglob("*.lnk")
             if "uninstall" not in p.stem.lower()]
    return _best(name, links)


_store_apps: list | None = None


def find_store_app(name: str):
    """AppID of an installed Store / packaged app (Get-StartApps), cached."""
    global _store_apps
    if _store_apps is None:
        import json
        import subprocess
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                  "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"],
                                 capture_output=True, text=True, timeout=15, creationflags=0x08000000).stdout
            rows = json.loads(out) if out.strip() else []
            _store_apps = [(r["AppID"], r["Name"]) for r in (rows if isinstance(rows, list) else [rows])]
        except Exception:
            log.exception("Get-StartApps failed")
            _store_apps = []
    return _best(name, _store_apps)


class WindowsOutput(Output):
    def __init__(self, media_source=None):
        self.media_source = media_source
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, name="media-forward", daemon=True).start()
        self._mgr = None

    # ---------------- keys
    def keys(self, combo):
        vks = [vk_of(k) for k in combo.split("+")] if combo.strip() != "+" else [VK["plus"]]
        _send(*[_key(v) for v in vks], *[_key(v, True) for v in reversed(vks)])

    def key_down(self, key):
        _send(_key(vk_of(key)))

    def key_up(self, key):
        _send(_key(vk_of(key), True))

    # ---------------- scroll
    def scroll(self, notches, horizontal=False):
        i = INPUT(type=0)
        amount = int(-notches * 120) if not horizontal else int(notches * 120)
        i.u.mi = MOUSEINPUT(0, 0, ctypes.c_uint32(amount).value, 0x01000 if horizontal else 0x0800, 0, ORBIT_TAG)
        _send(i)

    # ---------------- media (to the real player, never to ourselves)
    def media(self, command):
        asyncio.run_coroutine_threadsafe(self._media(command), self._loop)

    async def _media(self, command):
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as M,
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as S)
        if self._mgr is None:
            self._mgr = await M.request_async()
        own = getattr(self.media_source, "own_aumid", None)
        others = [s for s in self._mgr.get_sessions() if s.source_app_user_model_id != own]
        if not others:
            log.info("media:%s — no other player open", command)
            return
        playing = [s for s in others if s.get_playback_info().playback_status == S.PLAYING]
        target = (playing or others)[0]
        fn = {"play_pause": target.try_toggle_play_pause_async, "next": target.try_skip_next_async,
              "previous": target.try_skip_previous_async, "stop": target.try_stop_async}.get(command)
        if not fn:
            log.error("unknown media command '%s'", command)
            return
        await fn()
        log.info("media:%s -> %s", command, target.source_app_user_model_id)
        if self.media_source and command == "play_pause":
            await asyncio.sleep(0.6)   # the player grabs media focus when it starts; take it back
            threading.Thread(target=self.media_source.ensure_focus, daemon=True).start()

    # ---------------- launch
    def launch(self, target):
        """A path, URL or command, or an app by name ("Spotify", "DaVinci Resolve"):
        looked up in the Start menu and the installed Store apps. Off the UI thread."""
        threading.Thread(target=self._launch, args=(target,), daemon=True).start()

    def _launch(self, target):
        import shutil
        import subprocess
        t = target.strip()
        try:
            if os.path.exists(t) or "://" in t or ":\\" in t:
                os.startfile(t)
                return
            exe = shutil.which(t) or shutil.which(t + ".exe")
            if exe:
                subprocess.Popen([exe])
                return
            lnk = find_start_menu_app(t)
            if lnk:
                os.startfile(lnk)
                log.info("launch %s -> %s", t, lnk)
                return
            app_id = find_store_app(t)
            if app_id:
                subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"])
                log.info("launch %s -> %s", t, app_id)
                return
            subprocess.Popen(t, shell=True)                       # last resort: let the shell try
        except OSError:
            log.exception("could not open '%s'", t)

    def center_window(self, title, timeout=1.5, max_w=1000, max_h=800):
        """Wait for a small foreground window with this title (e.g. Claude's Quick Entry,
        which otherwise opens wherever it was last left) and put it in the middle of the
        screen under the cursor, a little above centre."""
        deadline = time.monotonic() + timeout
        r = wt.RECT()
        while time.monotonic() < deadline:
            h = user32.GetForegroundWindow()
            n = user32.GetWindowTextLengthW(h)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, buf, n + 1)
            user32.GetWindowRect(h, ctypes.byref(r))
            w, hh = r.right - r.left, r.bottom - r.top
            if buf.value == title and 0 < w <= max_w and 0 < hh <= max_h:
                break
            time.sleep(0.04)
        else:
            log.info("center:%s — no such window appeared", title)
            return
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        mon = user32.MonitorFromPoint(pt, 2)  # MONITOR_DEFAULTTONEAREST

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]

        mi = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        user32.GetMonitorInfoW(mon, ctypes.byref(mi))
        wa = mi.rcWork
        x = wa.left + (wa.right - wa.left - w) // 2
        y = wa.top + int((wa.bottom - wa.top) * 0.30) - hh // 4
        # SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
        user32.SetWindowPos(h, 0, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010)

    # ---------------- brightness (via Twinkle Tray, so its slider stays in sync)
    TWINKLE = os.path.expandvars(r"%LOCALAPPDATA%\Programs\twinkle-tray\Twinkle Tray.exe")

    def _twinkle(self, *args) -> str:
        import subprocess
        if not os.path.exists(self.TWINKLE):
            return ""
        r = subprocess.run([self.TWINKLE, *args], capture_output=True, text=True, timeout=5,
                           creationflags=0x08000000)  # CREATE_NO_WINDOW
        return r.stdout

    _internal = None

    def _builtin(self):
        if self._internal is None:
            from orbit.platform.windows.brightness import InternalBrightness
            type(self)._internal = InternalBrightness()
        return self._internal

    def brightness_get(self):
        """The laptop's own screen if it has one (WMI), else the monitors Twinkle Tray drives."""
        v = self._builtin().get()
        if v is not None:
            return v
        import re
        out = re.sub(r"\x1b\[[0-9;]*m", "", self._twinkle("--List"))
        vals = [int(v) for v in re.findall(r"Brightness:\s*(\d+)", out)]
        return sum(vals) / len(vals) if vals else None

    def brightness_set(self, value):
        self._builtin().set(value)                            # built-in screen (laptops)
        self._twinkle("--All", f"--Set={int(round(value))}")  # external monitors, when Twinkle Tray is there

    def press_app_button(self, app_title: str, name_pattern: str):
        """Bring an app's main window forward and press a button in it by its accessible
        name (UI Automation, like a screen reader). Runs off the UI thread."""
        threading.Thread(target=self._press_app_button, args=(app_title, name_pattern), daemon=True).start()

    def _press_app_button(self, app_title, name_pattern):
        import re

        import uiautomation as auto

        with auto.UIAutomationInitializerInThread():
            wins = [w for w in auto.GetRootControl().GetChildren() if w.Name == app_title]
            if not wins:
                log.info("press_app_button: no '%s' window", app_title)
                return
            main = max(wins, key=lambda w: w.BoundingRectangle.width() * w.BoundingRectangle.height())
            h = main.NativeWindowHandle
            if user32.IsIconic(h):
                user32.ShowWindow(h, 9)  # SW_RESTORE
            # Alt tap lets a background process take foreground (foreground-lock rule)
            _send(_key(VK["alt"]), _key(VK["alt"], True))
            user32.SetForegroundWindow(h)
            rx = re.compile(name_pattern, re.I)
            btn = main.ButtonControl(searchDepth=60, Compare=lambda c, d: bool(rx.search(c.Name or "")))
            if not btn.Exists(maxSearchSeconds=1.5):
                log.info("press_app_button: no button matching %r in %s", name_pattern, app_title)
                return
            try:
                btn.GetInvokePattern().Invoke()
                log.info("pressed '%s' in %s", btn.Name, app_title)
            except Exception:
                btn.Click(simulateMove=False)
                log.info("clicked '%s' in %s", btn.Name, app_title)

    def active_window_title(self):
        h = user32.GetForegroundWindow()
        n = user32.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(h, buf, n + 1)
        return buf.value
