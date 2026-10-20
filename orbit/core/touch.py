"""Trackpad gestures from raw finger positions (Windows Precision Touchpads).

Three or four fingers: a swipe (left / right / up / down) or a tap. Two fingers are
scrolling, one is the pointer: never ours. Fed one frame at a time: the fingers
touching the pad now, positions normalised to 0..1 (y grows downwards, like the pad).

    3 or more fingers land     -> a gesture starts (the centroid is remembered)
    while all of them stay     -> the centroid is tracked
    every finger lifted        -> moved >= SWIPE of the pad: a swipe, the dominant axis
                                  short and still: a tap
                                  anything else: nothing (resting fingers, a slow drag)

Pure: no OS calls, time injected.
"""
from __future__ import annotations

from typing import Callable

SWIPE = 0.12          # of the pad's width / height
TAP_MOVE = 0.04
TAP_S = 0.35


def _centroid(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return sum(xs) / len(xs), sum(ys) / len(ys)


class TouchGestures:
    def __init__(self, emit: Callable[[str], None]):
        self.emit = emit
        self.reset()

    def reset(self):
        self._fingers = 0             # most fingers seen in this gesture
        self._start = None            # centroid when that many landed
        self._last = None
        self._t0 = 0.0
        self._moved = 0.0

    def frame(self, contacts: dict, t: float):
        n = len(contacts)
        if n == 0:
            if self._fingers >= 3:
                self._finish(t)
            self.reset()
            return
        c = _centroid(list(contacts.values()))
        if n >= 3 and n > self._fingers:          # (more) fingers landed: (re)start from here
            self._fingers, self._start, self._last, self._t0 = min(n, 4), c, c, t
            self._moved = 0.0
            return
        if self._fingers >= 3 and n == self._fingers:
            self._moved = max(self._moved, abs(c[0] - self._start[0]), abs(c[1] - self._start[1]))
            self._last = c

    def _finish(self, t: float):
        dx = self._last[0] - self._start[0]
        dy = self._last[1] - self._start[1]
        n = self._fingers
        if max(abs(dx), abs(dy)) >= SWIPE:
            d = ("right" if dx > 0 else "left") if abs(dx) >= abs(dy) else ("down" if dy > 0 else "up")
            self.emit(f"touchpad:{n}-swipe-{d}")
        elif t - self._t0 <= TAP_S and self._moved < TAP_MOVE:
            self.emit(f"touchpad:{n}-tap")
