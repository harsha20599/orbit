"""Gesture engine: one state machine, no OS or UI code.

States
  TOOL   dial drives the active tool (default state)
  WHEEL  wheel menu is open; rotate moves the highlight, click commits

Gesture model (adapts to what the sources can deliver):
  hold                -> open wheel        (or `gestures.open_wheel_fallback` if no source has HOLD)
  in wheel: rotate    -> move highlight
            click     -> commit highlighted item
            hold      -> close without change
            double/triple -> close without change
            idle      -> close without change after wheel.dismiss_after_ms
  with PRESS_RELEASE (future firmware decoding):
            press + turn -> wheel opens instantly, release commits (quick-select)
"""
from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Protocol

from orbit.core import actions, tools
from orbit.core.events import Capability, InputEvent, Kind
from orbit.core.motion import SpinTracker
from orbit.core.tools import Hud, Tool
from orbit.platform.base import InputSource, Output, RotationSource

log = logging.getLogger("orbit.engine")


class UI(Protocol):
    def wheel_open(self, items: list[dict], index: int) -> None: ...
    def wheel_move(self, index: int, direction: int) -> None: ...
    def wheel_commit(self, index: int) -> None: ...
    def wheel_cancel(self) -> None: ...
    def hud(self, h: Hud) -> None: ...


class State(Enum):
    TOOL = "tool"
    WHEEL = "wheel"


class Engine:
    def __init__(self, cfg: dict, out: Output, ui: UI, sources: list[InputSource]):
        self.cfg = cfg
        self.out = out
        self.ui = ui
        self.sources = sources
        self.rotation_sources = [s for s in sources if isinstance(s, RotationSource)]
        caps = set().union(*(s.capabilities for s in sources if s.available)) if sources else set()
        self.caps = caps

        self.tools: dict[str, Tool] = {tid: tools.build(tid, tc) for tid, tc in cfg["tools"].items()}
        self.wheel_ids: list[str] = [i for i in cfg["wheel"]["items"] if i in self.tools]
        g_cfg = cfg["gestures"]
        self.gestures = {g: actions.parse(a) for g, a in g_cfg.items()
                         if g not in ("open_wheel", "open_wheel_fallback")}
        # Gestures that open the wheel always win over tool-level bindings.
        opens = g_cfg.get("open_wheel", ["hold"])
        self.open_with = {opens} if isinstance(opens, str) else set(opens)
        has_hold = Capability.HOLD in caps or Capability.PRESS_RELEASE in caps
        if not has_hold and "hold" in self.open_with:
            self.open_with.discard("hold")
            if not self.open_with:
                self.open_with = {g_cfg.get("open_wheel_fallback", "triple")}
            log.warning("press-and-hold unavailable; wheel opens with %s", sorted(self.open_with))
        if not self.open_with:                  # every gesture reassigned: keep a way in
            self.open_with = {g_cfg.get("open_wheel_fallback", "triple")}
            self.gestures.pop(next(iter(self.open_with)), None)
            log.warning("no gesture opens the wheel; using %s", sorted(self.open_with))

        self.dismiss_after = cfg["wheel"].get("dismiss_after_ms", 6000) / 1000
        self.duck = float(cfg["wheel"].get("duck_volume", 0.5))   # 0 or 1 = off
        self.timeout_selects = cfg["wheel"].get("on_timeout", "select") == "select"
        # The buds drop the clicks between reports when turned fast (10 clicks -> 3 reports),
        # so a report at their max rate moves the highlight `accel` items instead of one.
        # Off by default: two deliberate clicks ~0.45 s apart look the same as a spin with
        # dropped clicks, and skipping an item when you meant one is worse than one more turn.
        self.wheel_accel = max(1, int(cfg["wheel"].get("accel", 1)))
        self._wheel_spin = SpinTracker()
        self.state = State.TOOL
        self.tool: Tool = self.tools[cfg.get("default_tool", self.wheel_ids[0])]
        self.prev_tool: Tool | None = None
        self.index = 0
        self._wheel_last = 0.0
        self._pressed_at: float | None = None
        self._quick = False
        # Does the dial (the buds' volume) drive Orbit? Controls without a dial turn
        # (other earbuds, keys only) leave the volume as volume.
        self.volume_dial = True
        self.assistant = actions.parse(cfg.get("assistant") or g_cfg.get("hold", "none"))
        self._sync_passthrough()

    def set_volume_dial(self, on: bool) -> None:
        if on != self.volume_dial:
            self.volume_dial = on
            self._sync_passthrough()

    # ------------------------------------------------------------------ public
    # ------------------------------------------------------------------ on / off
    paused = False

    def set_paused(self, on: bool) -> None:
        """Off: Orbit steps aside. The dial changes volume, presses go to the music
        player as they would without Orbit; the wheel closes and the tool lets go."""
        if on == self.paused:
            return
        if on:
            if self.state == State.WHEEL:
                self._cancel()
            self.tool.leave(self)
        self.paused = on
        if not on:
            self.tool.enter(self)
        self._sync_passthrough()
        log.info("Orbit %s", "off" if on else "on")

    _NATIVE = {Kind.CLICK: "play_pause", Kind.DOUBLE: "next", Kind.TRIPLE: "previous"}

    def handle(self, ev: InputEvent) -> None:
        log.debug("%s  [%s/%s]", ev, "off" if self.paused else self.state.value, self.tool.id)
        if self.paused:
            if ev.kind in self._NATIVE:
                self.out.media(self._NATIVE[ev.kind])
            return
        if ev.kind == Kind.PRESS:
            self._pressed_at = ev.t
            return
        if ev.kind == Kind.RELEASE:
            self._pressed_at = None
            if self._quick:
                self._quick = False
                self._commit()
            return

        if ev.kind == Kind.ACTION:
            self._perform(ev.action or "")
            return
        if self.state == State.WHEEL:
            self._wheel_event(ev)
        else:
            self._tool_event(ev)

    def _perform(self, a: str) -> None:
        """A function a control asked for (moves arrive as turns, select as a click)."""
        from orbit.core import controls as c
        if a == c.OPEN:
            self._cancel() if self.state == State.WHEEL else self.open_wheel()
            return
        if self.state == State.WHEEL:
            self._cancel()
            return
        if a == c.LAST_TOOL:
            self.last_tool()
        elif a == c.ASSISTANT:
            self.assistant(self)
        elif a.startswith(c.CUSTOM):
            act = actions.parse(a[len(c.CUSTOM):])
            act(self)
            self.ui.hud(Hud("keyboard", c.action_label(a), ""))
        else:
            log.warning("unknown control action '%s'", a)

    def tick(self) -> None:
        now = time.monotonic()
        self.tool.tick(self, now)
        if self.state == State.WHEEL and not self._quick and now - self._wheel_last > self.dismiss_after:
            # A press arrives ~0.4 s late (firmware waits for double/triple), so letting the
            # highlight stand is the fast path. One-shot actions never fire on timeout.
            if self.timeout_selects and self.tools[self.wheel_ids[self.index]].sticky:
                self._commit()
            else:
                self._cancel()

    def open_wheel(self) -> None:
        if self.state == State.WHEEL or not self.wheel_ids:
            return
        self.tool.leave(self)
        self.state = State.WHEEL
        self.index = self.wheel_ids.index(self.tool.id) if self.tool.id in self.wheel_ids else 0
        self._wheel_last = time.monotonic()
        self._wheel_spin = SpinTracker()
        self._sync_passthrough()
        self.ui.wheel_open([self.tools[i].to_item() for i in self.wheel_ids], self.index)

    def set_tool(self, tid: str) -> None:
        if tid not in self.tools:
            log.error("unknown tool '%s'", tid)
            return
        self.tool.leave(self)
        self._switch_to(self.tools[tid])
        self.tool.enter(self)
        self._sync_passthrough()
        self.ui.hud(self.tool.hud(self))

    def last_tool(self) -> None:
        if self.prev_tool:
            self.set_tool(self.prev_tool.id)

    def _switch_to(self, t: Tool) -> None:
        if t is not self.tool:
            self.prev_tool = self.tool
            self.tool = t

    def rotation_level(self) -> float | None:
        for s in self.rotation_sources:
            lvl = s.level()
            if lvl is not None:
                return lvl
        return None

    def shutdown(self) -> None:
        self.tool.leave(self)

    # ------------------------------------------------------------------ states
    def _tool_event(self, ev: InputEvent) -> None:
        if ev.kind == Kind.ROTATE:
            if self._pressed_at is not None and Capability.PRESS_RELEASE in self.caps:
                self._quick = True       # press + turn -> quick-select wheel
                self.open_wheel()
                self._wheel_event(ev)
                return
            from orbit.core.controls import CONTROLLER
            if self.tool.rotation_passthrough and ev.source.startswith(CONTROLLER):
                self._step_volume(ev.delta)         # the buds change the volume themselves; keys don't
            h = self.tool.rotate(self, ev.delta)
            if h:
                self.ui.hud(h)
            return

        name = ev.kind.value
        if ev.action is None and name in self.open_with:
            self.open_wheel()
            return
        handled = self.tool.gesture(self, name)
        if handled is False:
            a = self.gestures.get(name, actions.NOOP)
            a(self)
            if a is not actions.NOOP and self.state == State.TOOL:
                self.ui.hud(Hud(self.tool.icon, self.tool.label, str(a)))
        elif isinstance(handled, Hud):
            self.ui.hud(handled)

    def _wheel_event(self, ev: InputEvent) -> None:
        self._wheel_last = time.monotonic()
        if ev.kind == Kind.ROTATE:
            n = len(self.wheel_ids)
            self.index = (self.index + self._wheel_steps(ev.delta)) % n
            self.ui.wheel_move(self.index, 1 if ev.delta > 0 else -1)
        elif ev.kind == Kind.CLICK:
            self._commit()
        elif ev.kind in (Kind.HOLD, Kind.DOUBLE, Kind.TRIPLE):
            self._cancel()

    def _wheel_steps(self, delta: int) -> int:
        """Careful clicks move one item; reports at the buds' max rate (<~0.47 s apart,
        same direction) move `accel`. Turn-backs stay exact. No catch-up for the first
        report of a flick: in a menu, overshooting is worse than one more click."""
        spin = self._wheel_spin
        spin.update(delta)
        if self.wheel_accel == 1 or spin.intensity < 0.75:
            return delta
        return delta * self.wheel_accel

    def _commit(self) -> None:
        item = self.tools[self.wheel_ids[self.index]]
        self.ui.wheel_commit(self.index)
        self.state = State.TOOL
        if item.sticky:
            self._switch_to(item)
            item.enter(self)
            self._sync_passthrough()
            self.ui.hud(item.hud(self))
        else:
            self._sync_passthrough()
            self.tool.enter(self)
            self.ui.hud(item.fire(self))

    def _cancel(self) -> None:
        self.state = State.TOOL
        self._quick = False
        self.ui.wheel_cancel()
        self.tool.enter(self)
        self._sync_passthrough()

    def _step_volume(self, n: int) -> None:
        """Volume up / down by n steps for a control in the Volume tool: through the buds'
        own level when connected (marked as ours, so it is never read back as a turn),
        else the system volume keys."""
        for s in self.rotation_sources:
            nudge = getattr(s, "nudge", None)
            if nudge and s.level() is not None:
                nudge(n)
                return
        self.out.volume_step(n)

    def _sync_passthrough(self) -> None:
        """Rotation side effects follow state: the wheel consumes rotation and ducks the
        level (so each detent's native blip is soft); tool mode restores the real level
        first, then passes rotation through or consumes it per tool."""
        wheel = self.state == State.WHEEL and not self.paused and self.volume_dial
        on = self.paused or not self.volume_dial or (not wheel and self.tool.rotation_passthrough)
        for s in self.rotation_sources:
            if wheel:
                s.set_passthrough(False)
                s.set_duck(self.duck if 0 < self.duck < 1 else None)
            else:
                s.set_duck(None)
                s.set_passthrough(on)
