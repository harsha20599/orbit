"""Windows virtual-key codes -> Orbit key names, and the swallow bookkeeping for the
keyboard / mouse hooks. Pure: no ctypes, so it is testable on any OS.
"""
from __future__ import annotations

from typing import Callable

from orbit.core.controls import key_input, scroll_input

VK_NAMES: dict[int, str] = {
    0x08: "backspace", 0x09: "tab", 0x0D: "enter", 0x13: "pause", 0x14: "capslock", 0x1B: "esc",
    0x20: "space", 0x21: "pageup", 0x22: "pagedown", 0x23: "end", 0x24: "home",
    0x25: "left", 0x26: "up", 0x27: "right", 0x28: "down", 0x2C: "printscreen", 0x2D: "insert", 0x2E: "delete",
    0x5D: "menu",
    0xAD: "mute", 0xAE: "volumedown", 0xAF: "volumeup",
    0xB0: "nexttrack", 0xB1: "prevtrack", 0xB2: "stop", 0xB3: "playpause",
    0xBA: "semicolon", 0xBB: "equals", 0xBC: "comma", 0xBD: "minus", 0xBE: "period", 0xBF: "slash",
    0xC0: "backquote", 0xDB: "lbracket", 0xDC: "backslash", 0xDD: "rbracket", 0xDE: "quote",
}
VK_NAMES.update({0x70 + i: f"f{i + 1}" for i in range(24)})                    # F1..F24
VK_NAMES.update({ord(ch): ch.lower() for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"})
VK_NAMES.update({0x60 + i: f"num{i}" for i in range(10)})                      # numpad digits

# modifiers (generic and left / right): held state only, never a trigger themselves
MOD_VKS: dict[int, str] = {0x10: "shift", 0xA0: "shift", 0xA1: "shift", 0x11: "ctrl", 0xA2: "ctrl", 0xA3: "ctrl",
                          0x12: "alt", 0xA4: "alt", 0xA5: "alt", 0x5B: "win", 0x5C: "win"}

WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105

# dwExtraInfo on every key / mouse event Orbit sends itself (output.py), so the hooks can
# skip exactly those. Not the INJECTED flag: Windows marks keys it makes from HID media
# controls as injected too (a Bluetooth keyboard's volume knob arrives as injected
# VK_VOLUME_UP / DOWN with scan code 0), and those must still reach Orbit.
ORBIT_TAG = 0x0B17D1A1


def own_event(extra_info: int) -> bool:
    return extra_info == ORBIT_TAG
WM_MBUTTONDOWN, WM_MBUTTONUP, WM_XBUTTONDOWN, WM_XBUTTONUP = 0x0207, 0x0208, 0x020B, 0x020C
WM_MOUSEWHEEL, WM_MOUSEHWHEEL = 0x020A, 0x020E
WHEEL_DELTA = 120


def wheel_direction(msg: int, mouse_data: int) -> str | None:
    """'up' / 'down' / 'left' / 'right' for a wheel message (high word = signed delta)."""
    d = (mouse_data >> 16) & 0xFFFF
    d = d - 0x10000 if d & 0x8000 else d
    if not d:
        return None
    if msg == WM_MOUSEWHEEL:
        return "up" if d > 0 else "down"
    if msg == WM_MOUSEHWHEEL:
        return "right" if d > 0 else "left"
    return None


def wheel_amount(mouse_data: int) -> int:
    d = (mouse_data >> 16) & 0xFFFF
    return abs(d - 0x10000 if d & 0x8000 else d)


def mouse_input(msg: int, mouse_data: int) -> tuple[str, bool] | None:
    """(input id, down) for a low-level mouse message, or None if it's not a button we use."""
    if msg in (WM_MBUTTONDOWN, WM_MBUTTONUP):
        return "mouse:middle", msg == WM_MBUTTONDOWN
    if msg in (WM_XBUTTONDOWN, WM_XBUTTONUP):
        which = (mouse_data >> 16) & 0xFFFF
        name = {1: "mouse:back", 2: "mouse:forward"}.get(which)
        return (name, msg == WM_XBUTTONDOWN) if name else None
    return None


class KeyTracker:
    """Decides, per hook event, whether to swallow it, and keeps downs and ups paired:
    a key swallowed on its way down is swallowed on its way up too, whatever changed
    in between (modifiers released, Orbit turned off, settings saved)."""

    def __init__(self, wants: Callable[[str], bool], key: Callable[[str, bool], bool],
                 wants_gesture: Callable[[str], bool] | None = None, gesture: Callable[[str], bool] | None = None):
        self.wants = wants
        self.key = key
        self.wants_gesture = wants_gesture or (lambda inp: False)
        self.gesture = gesture or (lambda inp: False)
        self._wheel: dict[str, int] = {}               # partial notches (precision touchpads scroll in small steps)
        self.held: set[str] = set()
        self._held_vks: dict[int, str] = {}
        self._swallowed: dict[object, str] = {}

    def keyboard(self, vk: int, down: bool) -> bool:
        if vk in MOD_VKS:
            if down:
                self._held_vks[vk] = MOD_VKS[vk]
            else:
                self._held_vks.pop(vk, None)
            self.held = set(self._held_vks.values())
            return False
        name = VK_NAMES.get(vk)
        if name is None:
            return False
        return self._button(vk, key_input(name, self.held), down)

    def mouse(self, msg: int, mouse_data: int) -> bool:
        if msg in (WM_MOUSEWHEEL, WM_MOUSEHWHEEL):
            return self._scroll(msg, mouse_data)
        m = mouse_input(msg, mouse_data)
        if m is None:
            return False
        inp, down = m
        return self._button(inp, inp, down)

    def _scroll(self, msg: int, mouse_data: int) -> bool:
        d = wheel_direction(msg, mouse_data)
        inp = scroll_input(d, self.held) if d else None
        if inp is None or not self.wants_gesture(inp):
            return False                                    # plain scrolling, or nothing uses it
        acc = self._wheel.get(inp, 0) + wheel_amount(mouse_data)
        while acc >= WHEEL_DELTA:
            acc -= WHEEL_DELTA
            self.gesture(inp)
        self._wheel = {inp: acc}                           # a change of direction / keys starts over
        return True

    def _button(self, ident, inp: str, down: bool) -> bool:
        if down:
            if ident in self._swallowed:                 # held: the OS repeats the down
                self.key(self._swallowed[ident], True)
                return True
            if self.wants(inp):
                self._swallowed[ident] = inp
                self.key(inp, True)
                return True
            return False
        was = self._swallowed.pop(ident, None)
        if was is None:
            return False
        self.key(was, False)
        return True
