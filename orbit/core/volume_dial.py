"""Turn an output-volume level stream into dial clicks. Platform independent.

The CMF dial (and most earbud dials) has no channel of its own: each click
nudges the buds' volume one step and the OS reports the new level. A platform
backend feeds every level change here; this class decides how many clicks it
was, and puts the level back when the active tool doesn't want volume to move.

What the real-device traces taught us (Windows, Oct 2026; tools/dial_record.py):

  * The buds keep their own N-step grid (16: raw AVRCP 0, 8, 16 ... 64, 71, 79 ...
    of 127; one older session looked like 15) and the OS level is raw/127. Every
    report is exactly one grid step. The grid is detected from the levels seen:
    the smallest N that all recent reports sit on.
  * A level we set between grid points is rounded by the buds; the next click is
    +-1 from that. We only ever set grid points, so clicks stay whole steps.
  * The buds send at most one step every ~0.3 s and DROP the clicks in between
    (a 10-click spin arrives as 3 reports). Nothing here can recover them; the
    tools scale fast report streams instead (orbit.core.motion).
  * Every set of ours is followed ~1 ms later by a second, not-ours copy of the
    same level (Windows). That is an echo, never a click and never proof the buds
    took our level.
  * A click can be in flight while we set: it then arrives measured from the
    buds' old level. While a set is fresh, a report is measured from whichever of
    (our level, their old level) makes it a whole step.

Backend contract:
    get_level() -> float | None        current level 0..1
    set_level(level: float)            set it; the backend reports the resulting
                                       change back with ours=True
    thread_init()                      optional, called once on the worker thread
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Callable, Protocol

from orbit.core.events import InputEvent, Kind

log = logging.getLogger("orbit.dial")
trace = logging.getLogger("orbit.trace")

DEFAULT_GRID = 16           # CMF Buds Pro 2; re-detected from the levels the buds report
GRID_RANGE = range(8, 33)
GRID_FIT = 0.15             # max mean distance (in steps) from a grid point for "on grid"
GRID_SAMPLES = 8
CLICK_MIN = 0.35            # fraction of a step that counts as a click (2% keyboard nudges don't)
MAX_CLICKS = 2              # one step per report; 2 only if the OS skipped a callback
RECENTER_IDLE_S = 0.9       # quiet time before we restore the level
EDGE_STEPS = 2              # recenter at once when this close to either end
STALE_S = 0.8               # window after our own set in which the buds may lag behind
BURST_S = 0.15              # repeats of one report closer than this are the same report
EDGE_EPS = 0.004            # "at 0% / 100%"


class LevelBackend(Protocol):
    def get_level(self) -> float | None: ...
    def set_level(self, level: float) -> None: ...


class VolumeDial:
    def __init__(self, backend: LevelBackend, emit: Callable[[InputEvent], None], source: str = "volume-dial"):
        self.backend = backend
        self.emit = emit
        self.source = source
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._stopped = threading.Event()
        self._passthrough = True
        self._level: float | None = None       # last level seen
        self._from_dial = False                # was that a dial report (vs our set)?
        self.grid = DEFAULT_GRID
        self._seen: deque[float] = deque(maxlen=GRID_SAMPLES)   # recent dial-reported levels
        self._home: float | None = None
        self._last_move = 0.0
        self._last_dial = 0.0
        self._need_recenter = False
        self._saved: float | None = None       # real listening level while ducked
        self._apply: float | None = None       # level the worker should set
        self._last_set = (0.0, None, None)     # (time, buds' level before, our level)
        self._last_report = -1.0               # time of the last not-ours report

    # ---------------------------------------------------------------- lifecycle
    def start(self):
        self._level = self.backend.get_level()
        threading.Thread(target=self._worker, name=f"{self.source}-worker", daemon=True).start()

    def stop(self):
        self.set_duck(None)                    # never leave the user ducked
        self._stop.set()
        self._wake.set()
        self._stopped.wait(1.0)

    def rebase(self):
        """Device (re)connected: forget history, read the level fresh."""
        with self._lock:
            self._level = self.backend.get_level()
            self._from_dial = False
            self._last_set = (0.0, None, None)
            self._seen.clear()

    # ---------------------------------------------------------------- engine-facing
    def set_passthrough(self, on: bool):
        with self._lock:
            if on == self._passthrough:
                return
            self._passthrough = on
            if not on and self._level is not None:
                self._home = self._snap_home(self._level)
                self._need_recenter = True
        self._wake.set()

    def set_duck(self, factor: float | None):
        with self._lock:
            if factor:
                if self._saved is None:
                    if self._level is None:
                        return
                    self._saved = self._level
                n = self._grid()
                ducked = max(round(self._saved * factor * n), EDGE_STEPS) / n
                self._home = min(ducked, self._snap_home(self._saved))
                self._apply = self._home
            else:
                if self._saved is None:
                    return
                self._apply = self._saved
                self._home = self._snap_home(self._saved)
                self._saved = None
        self._wake.set()

    @property
    def step(self) -> float:
        return 1 / self.grid

    def level(self) -> float | None:
        return self._saved if self._saved is not None else self._level

    def nudge(self, steps: int):
        """Volume by `steps` of the buds' grid (a control in the Volume tool). Our own
        set, so its echo is never taken for a turn of the dial."""
        with self._lock:
            lvl = self._level
        if lvl is None:
            return
        self._set(min(1.0, max(0.0, round(lvl * self.grid + steps) / self.grid)), "control")

    def last_activity(self) -> float:
        """monotonic time of the last click or our own set."""
        return max(self._last_dial, self._last_set[0])

    # ---------------------------------------------------------------- backend-facing
    def on_level(self, level: float, ours: bool, now: float | None = None):
        """Every level change, from any thread."""
        now = time.monotonic() if now is None else now
        trace.debug("lvl  %5.1f %s", level * 100, "ours" if ours else "")
        with self._lock:
            if ours:
                self._level = level
                self._from_dial = False
                return
            prev = self._level
            if prev is None:
                self._level = level
                return
            step = self.step
            since, self._last_report = now - self._last_report, now

            t_set, before, target = self._last_set
            fresh = target is not None and now - t_set < STALE_S
            if fresh and abs(level - target) < CLICK_MIN * step:
                trace.debug("     echo of our level")                # never a click, keep the window
                self._level = level
                return
            d = level - prev
            if fresh:
                # Landing back on their old level is a click from ours (we recentered
                # one step, they clicked the same way), not a stale re-send: the buds
                # confirmed all 25 recenters in the calibration capture.
                # A click is measured from our level, or (still in flight when we set)
                # from theirs - whichever makes it a whole step.
                if before is not None and (abs(abs(level - before) / step - 1)
                                           < abs(abs(d) / step - 1) - 0.25):
                    trace.debug("     click before buds took our level: measured from %.1f", before * 100)
                    d = level - before
                    # Windows then re-applies our level: keep treating it as an echo
                    self._last_set = (t_set, None, target)
                else:
                    self._last_set = (t_set, None, None)        # buds moved on from ours

            self._level = level
            if abs(d) < CLICK_MIN * step:
                self._from_dial = True
                edge = 1 if level >= 1 - EDGE_EPS else -1 if level <= EDGE_EPS else 0
                if not (edge and d == 0 and since > BURST_S and not fresh):
                    return                                             # keyboard nudge / repeat
                # macOS reports a click that can't move past 0% / 100% as an unchanged
                # level (one burst per click); count it toward that end
                trace.debug("     click at the %s end", "top" if edge > 0 else "bottom")
                d = edge * step
            self._learn_grid(level)
            step = self.step

            # floor(+0.3), not round: one click from an off-grid level (1.6 steps) stays 1.
            # Capped so a glitch never becomes a burst.
            clicks = min(MAX_CLICKS, max(1, int(abs(d) / step + 0.3)))
            delta = clicks if d > 0 else -clicks
            self._from_dial = True

            self._last_move = self._last_dial = now
            if not self._passthrough:
                k = round(level * self._grid())
                if k <= EDGE_STEPS or k >= self._grid() - EDGE_STEPS:
                    self._last_move = 0.0                              # at an end: recenter now
                self._need_recenter = True
        trace.debug("     delta=%+d (step %.2f%%)", delta, self.step * 100)
        self.emit(InputEvent(Kind.ROTATE, delta, self.source))
        self._wake.set()

    # ---------------------------------------------------------------- internals
    def _grid(self) -> int:
        return max(self.grid, 2 * EDGE_STEPS + 3)

    def _learn_grid(self, level: float):
        """Smallest grid every recent dial report sits on (16 for the CMF buds)."""
        self._seen.append(level)
        if len(self._seen) < 3:
            return

        def fit(n):
            return sum(abs(v * n - round(v * n)) for v in self._seen) / len(self._seen)

        if fit(self.grid) <= GRID_FIT:
            return
        for n in GRID_RANGE:
            if fit(n) <= GRID_FIT:
                log.info("dial grid: %d steps (was %d)", n, self.grid)
                self.grid = n
                return

    def _snap_home(self, lvl: float) -> float:
        """Nearest point on the buds' grid, EDGE_STEPS+1 clicks away from both ends."""
        n = self._grid()
        k = min(max(round(lvl * n), EDGE_STEPS + 1), n - EDGE_STEPS - 1)
        return k / n

    def _set(self, level: float, why: str):
        with self._lock:
            before = self._level
            if before is not None and abs(before - level) < 1e-3:
                return
            self._last_set = (time.monotonic(), before, level)
        trace.debug("set  %5.1f (%s)", level * 100, why)
        try:
            self.backend.set_level(level)
        except Exception:
            log.exception("set level failed")

    def _worker(self):
        init = getattr(self.backend, "thread_init", None)
        if init:
            init()
        while True:
            with self._lock:
                target, self._apply = self._apply, None
            if target is not None:
                self._set(target, "duck/restore")
            if self._stop.is_set():
                break
            if self._need_recenter:
                wait = RECENTER_IDLE_S - (time.monotonic() - self._last_move)
                if wait <= 0:
                    with self._lock:
                        home, self._need_recenter = self._home, False
                        skip = self._passthrough or home is None
                    if not skip:
                        self._set(home, "recenter")
                    continue
                self._wake.wait(wait)
            else:
                self._wake.wait(1.0)
            self._wake.clear()
        self._stopped.set()
