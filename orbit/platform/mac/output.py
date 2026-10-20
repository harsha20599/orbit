"""macOS Output: Quartz events for keys/scroll, AppleScript media forwarding,
DisplayServices / m1ddc brightness, `open` for launching.

Posting events needs the Accessibility permission (checked at startup).
"""
from __future__ import annotations

import ctypes
import logging
import shutil
import subprocess
import threading

from orbit.platform.base import Output
from orbit.platform.mac import keys as K

log = logging.getLogger("orbit.output")

PX_PER_NOTCH = 40            # one wheel notch ~ 3 lines on macOS
PLAYERS = ("Spotify", "Music")


class MacOutput(Output):
    def __init__(self):
        from Quartz import CGEventSourceCreate, kCGEventSourceStateHIDSystemState
        self._src = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
        self._held = 0                       # flags of modifiers held via key_down (Cmd for the switcher)
        self._ds = None

    # ---------------- keys
    def _post_key(self, code: int, down: bool, flags: int):
        from Quartz import (CGEventCreateKeyboardEvent, CGEventPost, CGEventSetFlags, CGEventSetIntegerValueField,
                            kCGEventSourceUserData, kCGHIDEventTap)
        from orbit.platform.mac.input_keys import ORBIT_EVENT
        e = CGEventCreateKeyboardEvent(self._src, code, down)
        CGEventSetFlags(e, flags | self._held)
        CGEventSetIntegerValueField(e, kCGEventSourceUserData, ORBIT_EVENT)    # never a control of our own
        CGEventPost(kCGHIDEventTap, e)

    def keys(self, combo):
        mods, flags, main = K.parse(combo)
        acc = 0
        for m, name in zip(mods, [p for p in combo.split("+")][:-1]):
            acc |= K.FLAGS[K.norm(name)]
            self._post_key(m, True, acc)
        self._post_key(main, True, flags)
        self._post_key(main, False, flags)
        for m in reversed(mods):
            self._post_key(m, False, 0)

    def key_down(self, key):
        n = K.norm(key)
        self._held |= K.FLAGS.get(n, 0)
        self._post_key(K.keycode(n), True, 0)

    def key_up(self, key):
        n = K.norm(key)
        self._held &= ~K.FLAGS.get(n, 0)
        self._post_key(K.keycode(n), False, 0)

    # ---------------- scroll (pixel, continuous: smooth in every app)
    def scroll(self, notches, horizontal=False):
        from Quartz import CGEventPost, kCGHIDEventTap
        px = int(round(-notches * PX_PER_NOTCH))          # ours: + = down; CG: + = up
        if px == 0:
            return
        CGEventPost(kCGHIDEventTap, scroll_event(px, horizontal))

    def volume_step(self, n):
        """System output volume by n steps of 1/16 (the volume keys' step)."""
        import subprocess
        delta = round(100 * n / 16)
        script = f"set volume output volume ((output volume of (get volume settings)) + ({delta}))"
        subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ---------------- media: to the real player (we own "now playing", so media keys loop back)
    def media(self, command):
        verb = {"play_pause": "playpause", "next": "next track", "previous": "previous track",
                "stop": "pause"}.get(command)
        if not verb:
            log.error("unknown media command '%s'", command)
            return
        threading.Thread(target=self._media, args=(verb,), daemon=True).start()

    def _media(self, verb):
        for app in PLAYERS:
            script = (f'if application "{app}" is running then\n'
                      f'  tell application "{app}" to {verb}\n'
                      f'  return "ok"\nend if\nreturn ""')
            r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
            if r.stdout.strip() == "ok":
                log.info("media:%s -> %s", verb, app)
                return
        log.info("media:%s — no scriptable player running", verb)

    # ---------------- launch
    def launch(self, target):
        args = ["open", target] if ("/" in target or ":" in target) else ["open", "-a", target]
        subprocess.Popen(args)

    # ---------------- brightness: built-in via DisplayServices, external via m1ddc
    def _displayservices(self):
        if self._ds is None:
            try:
                ds = ctypes.CDLL("/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices")
                ds.DisplayServicesGetBrightness.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_float)]
                ds.DisplayServicesSetBrightness.argtypes = [ctypes.c_uint32, ctypes.c_float]
                self._ds = ds
            except OSError:
                self._ds = False
        return self._ds or None

    @staticmethod
    def _builtin_display():
        from Quartz import CGDisplayIsBuiltin, CGGetActiveDisplayList
        err, ids, n = CGGetActiveDisplayList(16, None, None)
        for d in ids[:n]:
            if CGDisplayIsBuiltin(d):
                return d
        return None

    def brightness_get(self):
        ds, d = self._displayservices(), self._builtin_display()
        if ds and d is not None:
            v = ctypes.c_float()
            if ds.DisplayServicesGetBrightness(d, ctypes.byref(v)) == 0:
                return v.value * 100
        m1 = shutil.which("m1ddc")
        if m1:
            r = subprocess.run([m1, "get", "luminance"], capture_output=True, text=True, timeout=3)
            if r.stdout.strip().isdigit():
                return float(r.stdout.strip())
        return None

    def brightness_set(self, value):
        ds, d = self._displayservices(), self._builtin_display()
        if ds and d is not None:
            ds.DisplayServicesSetBrightness(d, ctypes.c_float(max(0.0, min(1.0, value / 100))))
            return
        m1 = shutil.which("m1ddc")
        if m1:
            subprocess.run([m1, "set", "luminance", str(int(round(value)))], timeout=3)

    # ---------------- not available on macOS (yet)
    def press_app_button(self, app_title, name_pattern):
        log.info("button:%s|%s — not supported on macOS", app_title, name_pattern)

    def center_window(self, title):
        log.info("center:%s — not supported on macOS", title)


def scroll_event(px: int, horizontal: bool = False):
    """A continuous (trackpad-style) pixel scroll at the cursor.

    Built field by field from a plain event instead of CGEventCreateScrollWheelEvent:
    that one is variadic, which is unreliable through the Python bridge on Apple
    Silicon, and it doesn't put the event at the cursor, so the scroll could land
    on the menu bar instead of the window under the pointer.
    """
    import Quartz as Q
    e = Q.CGEventCreate(None)                              # carries the current cursor location
    loc = Q.CGEventGetLocation(e)
    Q.CGEventSetType(e, Q.kCGEventScrollWheel)
    Q.CGEventSetLocation(e, loc)
    lines = max(1, round(abs(px) / 10)) * (1 if px > 0 else -1)
    # Continuous first, then coarse to fine: setting a coarser delta makes Quartz
    # recompute the finer ones, so the exact pixel amount goes in last.
    Q.CGEventSetIntegerValueField(e, Q.kCGScrollWheelEventIsContinuous, 1)
    ax = 2 if horizontal else 1
    Q.CGEventSetIntegerValueField(e, getattr(Q, f"kCGScrollWheelEventDeltaAxis{ax}"), lines)
    Q.CGEventSetDoubleValueField(e, getattr(Q, f"kCGScrollWheelEventFixedPtDeltaAxis{ax}"), float(px))
    Q.CGEventSetIntegerValueField(e, getattr(Q, f"kCGScrollWheelEventPointDeltaAxis{ax}"), px)
    return e

