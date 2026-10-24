"""macOS key codes / media keys / mouse buttons -> Orbit inputs, and the swallow
bookkeeping for the event tap. Pure: no PyObjC, so it is testable on any OS.
"""
from __future__ import annotations

from typing import Callable

from orbit.core.controls import key_input, scroll_input
from orbit.platform.mac.keys import FLAGS, KEYCODES

_MODIFIER_NAMES = {"cmd", "shift", "capslock", "alt", "ctrl", "fn"}
KEY_NAMES: dict[int, str] = {}
for _name, _code in KEYCODES.items():           # first name wins: "enter" over "return", "esc" over "escape"
    if _name not in _MODIFIER_NAMES and _code not in KEY_NAMES:
        KEY_NAMES[_code] = _name
KEY_NAMES[0x18] = "equals"

# NX_KEYTYPE_* (IOKit hidsystem/ev_keymap.h): the media keys, as NSSystemDefined events (subtype 8)
NX_KEYS = {0: "volumeup", 1: "volumedown", 7: "mute", 16: "playpause", 17: "nexttrack", 18: "prevtrack"}
NX_SUBTYPE_AUX = 8


def system_key(subtype: int, data1: int) -> tuple[str, bool, bool] | None:
    """(name, down, repeat) for a media-key NSSystemDefined event, else None."""
    if subtype != NX_SUBTYPE_AUX:
        return None
    code = (data1 & 0xFFFF0000) >> 16
    flags = data1 & 0xFFFF
    state = (flags & 0xFF00) >> 8
    name = NX_KEYS.get(code)
    if name is None or state not in (0xA, 0xB):
        return None
    return name, state == 0xA, bool(flags & 0x1)


def mods_of(flags: int) -> set[str]:
    return {n for n, bit in FLAGS.items() if n != "fn" and flags & bit}


def mouse_name(button: int) -> str | None:
    return {2: "mouse:middle", 3: "mouse:back", 4: "mouse:forward"}.get(button)


# NSEventPhase: the gesture's start and end
PHASE_BEGAN, PHASE_ENDED, PHASE_CANCELLED = 0x1, 0x8, 0x10
PINCH = 0.15            # total magnification for a pinch
ROTATE_DEG = 20.0


class Gestures:
    """Trackpad magnify / rotate events (one per frame) -> one gesture at its end."""

    def __init__(self):
        self.mag = 0.0
        self.rot = 0.0

    def magnify(self, value: float, phase: int) -> str | None:
        if phase & PHASE_BEGAN:
            self.mag = 0.0
        self.mag += value
        if phase & (PHASE_ENDED | PHASE_CANCELLED):
            total, self.mag = self.mag, 0.0
            if phase & PHASE_ENDED and abs(total) >= PINCH:
                return "touchpad:pinch-out" if total > 0 else "touchpad:pinch-in"
        return None

    def rotate(self, degrees: float, phase: int) -> str | None:
        if phase & PHASE_BEGAN:
            self.rot = 0.0
        self.rot += degrees
        if phase & (PHASE_ENDED | PHASE_CANCELLED):
            total, self.rot = self.rot, 0.0
            if phase & PHASE_ENDED and abs(total) >= ROTATE_DEG:
                return "touchpad:rotate-left" if total > 0 else "touchpad:rotate-right"   # + = counter-clockwise
        return None


def swipe_input(dx: float, dy: float) -> str | None:
    """NSEventTypeSwipe deltas (±1) -> a swipe. deltaX > 0: the fingers moved left."""
    if dx:
        return "touchpad:swipe-left" if dx > 0 else "touchpad:swipe-right"
    if dy:
        return "touchpad:swipe-up" if dy > 0 else "touchpad:swipe-down"
    return None


class ScrollNotches:
    """Modifier + scroll -> one input per notch; trackpads scroll in fractions of a line."""

    def __init__(self):
        self.acc: dict[str, float] = {}

    def feed(self, vertical: float, horizontal: float, mods: set[str], momentum: bool = False) -> tuple[str | None, int]:
        """momentum: macOS's coasting after a trackpad flick (fingers already lifted). Still
        the input (so it is swallowed, not zooming the page) but no more steps."""
        if vertical:
            d, amount = ("up" if vertical > 0 else "down"), abs(vertical)
        elif horizontal:
            d, amount = ("left" if horizontal > 0 else "right"), abs(horizontal)
        else:
            return None, 0
        inp = scroll_input(d, mods)
        if inp is None:
            return None, 0
        if momentum:
            self.acc = {}
            return inp, 0
        total = self.acc.get(inp, 0.0) + amount
        n = int(total + 1e-9)
        self.acc = {inp: total - n}
        return inp, n


class TapTracker:
    """Swallow decisions for the event tap, with downs and ups kept paired (a key
    swallowed on the way down is swallowed on the way up, whatever changed)."""

    def __init__(self, wants: Callable[[str], bool], key: Callable[[str, bool], bool]):
        self.wants = wants
        self.key_cb = key
        self._swallowed: dict[str, str] = {}

    def key(self, name: str, mods: set[str], down: bool, repeat: bool) -> bool:
        return self._button(name, key_input(name, mods), down)

    def mouse(self, button: int, down: bool) -> bool:
        inp = mouse_name(button)
        return self._button(inp, inp, down) if inp else False

    def release_all(self):
        """Forget every swallowed key (Secure Input, permission lost, wake): their ups may never come."""
        for inp in self._swallowed.values():
            self.key_cb(inp, False)
        self._swallowed.clear()

    def _button(self, ident: str, inp: str, down: bool) -> bool:
        if down:
            if ident in self._swallowed:
                self.key_cb(self._swallowed[ident], True)
                return True
            if self.wants(inp):
                self._swallowed[ident] = inp
                self.key_cb(inp, True)
                return True
            return False
        was = self._swallowed.pop(ident, None)
        if was is None:
            return False
        self.key_cb(was, False)
        return True
