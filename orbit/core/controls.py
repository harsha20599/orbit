"""Controls: which trigger does which function. Port of the Android app's core/Controls.kt.

One setup for everything:

    Single press / Select  <- e.g. "Earbuds: press", "F13 · tap"
    Open menu              <- e.g. "Earbuds: double press", "Mouse forward button · hold"
    Previous / Next        <- e.g. "Dial back / forward", "Volume − / + key · tap"

A trigger is an input (a key or shortcut, a media key, a mouse side button, an
earbud gesture, a dial turn) plus how it's pressed. Triggers from different sources
mix freely, and a function can have several.

Input ids:
    key:<combo>                 "key:f13", "key:ctrl+shift+space", "key:volumeup", "key:playpause"
    mouse:back|forward|middle   mouse buttons
    media:play|next|prev|hold   the earbuds' gestures, as the OS hands them to Orbit
    vol:up|down                 the CMF dial (it turns the buds' volume)

Snappy: a key whose only use is a plain tap fires on key down (and repeats while
held when it moves). Double / triple taps wait GAP_S for the next tap but never after
the highest count in use; holds fire the moment they pass.

Pure logic, no OS or Qt: the clock is injected, so it is all unit-testable.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Callable, Iterable

from orbit.core.events import InputEvent, Kind

CONTROLLER = "controller:"       # InputEvent.source prefix for events from controls


class Press(str, Enum):
    TAP = "tap"
    DOUBLE = "double"
    TRIPLE = "triple"
    HOLD = "hold"

    @property
    def label(self) -> str:
        return {"tap": "Tap", "double": "Double tap", "triple": "Triple tap", "hold": "Hold"}[self.value]


def counted(inp: str) -> bool:
    """The device counts presses itself (earbud gestures, dial turns): always a tap."""
    return inp.startswith("vol:") or (inp.startswith("media:") and inp != "media:hook")


_KEY_NAMES = {
    "volumeup": "Volume +", "volumedown": "Volume −", "mute": "Mute", "playpause": "Play / pause key",
    "nexttrack": "Next track key", "prevtrack": "Previous track key", "stop": "Stop key",
    "enter": "Enter", "space": "Space", "tab": "Tab", "esc": "Esc", "backspace": "Backspace",
    "delete": "Delete", "insert": "Insert", "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "pageup": "Page up", "pagedown": "Page down", "home": "Home", "end": "End",
    "printscreen": "Print Screen", "capslock": "Caps Lock", "menu": "Menu",
    "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win", "cmd": "Cmd",
}
MODS = ("ctrl", "cmd", "win", "alt", "shift")          # reading order, as shortcuts.py writes combos


def key_name(name: str) -> str:
    if name in _KEY_NAMES:
        return _KEY_NAMES[name]
    if len(name) == 1:
        return name.upper()
    if name.startswith("f") and name[1:].isdigit():
        return name.upper()
    return name.capitalize()


def input_label(inp: str) -> str:
    if inp.startswith("key:"):
        parts = inp[4:].split("+")
        return "+".join(key_name(p) for p in parts)
    return {
        "mouse:back": "Mouse back button", "mouse:forward": "Mouse forward button",
        "mouse:middle": "Middle mouse button",
        "media:play": "Earbuds: press", "media:next": "Earbuds: double press",
        "media:prev": "Earbuds: triple press", "media:hold": "Earbuds: press and hold",
        "media:hook": "Cable button",
        "vol:up": "Dial forward", "vol:down": "Dial back",
    }.get(inp, inp)


def key_input(name: str, mods: Iterable[str] = ()) -> str:
    """'f13' + {'ctrl'} -> 'key:ctrl+f13' (modifiers in the usual order)."""
    held = set(mods)
    return "key:" + "+".join([m for m in MODS if m in held] + [name])


@dataclass(frozen=True)
class Trigger:
    input: str
    press: Press = Press.TAP

    def __post_init__(self):                 # "hold" from Qt / JSON -> Press.HOLD (raises on nonsense)
        if not isinstance(self.press, Press):
            object.__setattr__(self, "press", Press(self.press))

    @property
    def counted(self) -> bool:
        return counted(self.input)

    def normalized(self) -> "Trigger":
        return replace(self, press=Press.TAP) if self.counted else self

    def label(self) -> str:
        base = input_label(self.input)
        return base if self.counted else f"{base} · {self.press.label.lower()}"


@dataclass(frozen=True)
class Binding:
    action: str
    trigger: Trigger


SELECT = "select"
OPEN = "open_wheel"
BACK = "back"
FORWARD = "forward"
ASSISTANT = "assistant"
LAST_TOOL = "last_tool"
CUSTOM = "custom:"               # custom:<action spec>, e.g. custom:keys:ctrl+shift+m, custom:launch:notepad
CORE = (SELECT, OPEN, BACK, FORWARD)
EXTRA = (ASSISTANT, CUSTOM, LAST_TOOL)


def action_label(a: str) -> str:
    if a.startswith(CUSTOM):
        spec = a[len(CUSTOM):]
        kind, _, arg = spec.partition(":")
        if kind == "keys":
            return f"Press {input_label('key:' + arg)}"
        if kind == "launch":
            return f"Open {arg}"
        return "Custom command"
    return {SELECT: "Single press / Select", OPEN: "Open menu", BACK: "Previous", FORWARD: "Next",
            ASSISTANT: "Open assistant", LAST_TOOL: "Previous tool"}.get(a, a)


def action_hint(a: str) -> str:
    return {
        SELECT: "Picks the highlighted tool. In a tool: its press (play / pause…).",
        OPEN: "Shows the wheel of tools. Again closes it.",
        BACK: "Previous item. In a tool: back, quieter, previous slide…",
        FORWARD: "Next item. In a tool: forward, louder, next slide…",
        ASSISTANT: "Claude (Quick Entry and voice typing on Windows).",
        CUSTOM: "Press a key combo or open an app.",
        LAST_TOOL: "Back to the tool you used before.",
    }.get(a, "")


@dataclass(frozen=True)
class Controls:
    bindings: tuple[Binding, ...] = ()
    preset: str | None = None

    def triggers(self, action: str) -> list[Trigger]:
        return [b.trigger for b in self.bindings if b.action == action]

    def action_for(self, t: Trigger) -> str | None:
        return next((b.action for b in self.bindings if b.trigger == t), None)

    @property
    def actions(self) -> list[str]:
        extra = [b.action for b in self.bindings if b.action not in CORE]
        return list(dict.fromkeys(list(CORE) + extra))

    def add(self, action: str, t: Trigger) -> tuple["Controls", str | None]:
        """Add t to action; a trigger does one thing, so whoever had it loses it.
        Returns the new controls and the action that lost it."""
        n = t.normalized()
        lost = next((b.action for b in self.bindings if b.trigger == n and b.action != action), None)
        kept = tuple(b for b in self.bindings if b.trigger != n)
        return Controls(kept + (Binding(action, n),), None), lost

    def remove(self, action: str, t: Trigger) -> "Controls":
        return Controls(tuple(b for b in self.bindings if not (b.action == action and b.trigger == t)), None)

    def clear(self, action: str) -> "Controls":
        return Controls(tuple(b for b in self.bindings if b.action != action), None)

    def uses(self, inp: str) -> bool:
        """Exact input, or a prefix ending in ':' ("media:")."""
        if inp.endswith(":"):
            return any(b.trigger.input.startswith(inp) for b in self.bindings)
        return any(b.trigger.input == inp for b in self.bindings)

    # ---- settings.json
    def to_json(self) -> dict:
        return {"preset": self.preset or "",
                "bindings": [{"action": b.action, "input": b.trigger.input, "press": b.trigger.press.value}
                             for b in self.bindings]}

    @staticmethod
    def from_json(d: dict | None) -> "Controls":
        if not isinstance(d, dict) or not isinstance(d.get("bindings"), list):
            return Presets.default()
        out = []
        for j in d["bindings"]:
            try:
                if not isinstance(j.get("action"), str) or not isinstance(j.get("input"), str) or not j["input"]:
                    continue
                out.append(Binding(j["action"], Trigger(j["input"], Press(j.get("press", "tap"))).normalized()))
            except (ValueError, AttributeError, TypeError):
                continue
        return Controls(tuple(out), d.get("preset") or None)


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    about: str
    controls: Controls
    platforms: tuple[str, ...] = ("win32", "darwin")


def _p(pid, name, about, *bs, platforms=("win32", "darwin")):
    return Preset(pid, name, about, Controls(tuple(Binding(a, Trigger(i, p)) for a, i, p in bs), pid), platforms)


T, D, TR, H = Press.TAP, Press.DOUBLE, Press.TRIPLE, Press.HOLD


class Presets:
    CMF = _p("cmf", "CMF Buds Pro 2", "Turn the case dial to move; press to select, double press to open.",
             (SELECT, "media:play", T), (OPEN, "media:next", T), (BACK, "vol:down", T), (FORWARD, "vol:up", T))
    EARBUDS = _p("earbuds", "Other earbuds and headphones", "Press once to select, twice to move, three times to open.",
                 (SELECT, "media:play", T), (FORWARD, "media:next", T), (OPEN, "media:prev", T))
    MEDIA_KEYS = _p("media_keys", "Keyboard volume knob / media keys",
                    "Volume keys or knob move; play / pause selects; next track opens.",
                    (BACK, "key:volumedown", T), (FORWARD, "key:volumeup", T),
                    (SELECT, "key:playpause", T), (OPEN, "key:nexttrack", T))
    MOUSE = _p("mouse", "Mouse side buttons", "Back / forward move; hold back to select, hold forward to open.",
               (BACK, "mouse:back", T), (FORWARD, "mouse:forward", T),
               (SELECT, "mouse:back", H), (OPEN, "mouse:forward", H))
    F_KEYS = _p("f_keys", "Spare keys (F13–F16)", "For macro pads and remotes that send F13–F16.",
                (BACK, "key:f13", T), (FORWARD, "key:f14", T), (SELECT, "key:f15", T), (OPEN, "key:f16", T))

    ALL = (CMF, EARBUDS, MEDIA_KEYS, MOUSE, F_KEYS)

    @classmethod
    def by_id(cls, pid: str | None) -> Preset | None:
        return next((p for p in cls.ALL if p.id == pid), None)

    @classmethod
    def default(cls) -> Controls:
        return cls.CMF.controls

    @classmethod
    def combine(cls, *ps: Preset) -> Controls:
        c = Controls()
        for p in ps:
            for b in p.controls.bindings:
                c, _ = c.add(b.action, b.trigger)
        return replace(c, preset=ps[0].id if len(ps) == 1 else None)


# ---------------------------------------------------------------- presses

GAP_S = 0.300
HOLD_S = 0.500
REPEAT_DELAY_S = 0.380
REPEAT_EVERY_S = 0.110
_EPS = 1e-6                     # float clocks: a deadline reached is reached


class PressRecognizer:
    """One input's downs / ups -> the presses in use."""

    def __init__(self, presses: set[Press], repeat: bool, emit: Callable[[Press], None]):
        self.presses = set(presses)
        self.repeat = repeat
        self.emit = emit
        self.reset()

    def reset(self):
        self._down_at: float | None = None
        self._fired_on_down = False
        self._hold_fired = False
        self._next_repeat = 0.0
        self._taps = 0
        self._last_up = 0.0

    @property
    def _instant(self) -> bool:
        return all(p == Press.TAP for p in self.presses)

    @property
    def _max_taps(self) -> int:
        return 3 if Press.TRIPLE in self.presses else 2 if Press.DOUBLE in self.presses else 1

    def down(self, now: float):
        if self._down_at is not None:            # the OS's own key repeat
            return
        self._down_at, self._hold_fired = now, False
        self._fired_on_down = self._instant
        if self._instant:
            if Press.TAP in self.presses:
                self.emit(Press.TAP)
            self._next_repeat = now + REPEAT_DELAY_S

    def up(self, now: float):
        if self._down_at is None:
            return
        self._down_at = None
        if self._fired_on_down or self._hold_fired:
            return
        self._taps += 1
        self._last_up = now
        if self._taps >= self._max_taps:
            self._flush()

    def tick(self, now: float):
        d = self._down_at
        if d is not None:
            if self._fired_on_down:
                if self.repeat:
                    while now + _EPS >= self._next_repeat:
                        self.emit(Press.TAP)
                        self._next_repeat += REPEAT_EVERY_S
            elif Press.HOLD in self.presses and not self._hold_fired and now - d + _EPS >= HOLD_S:
                self._hold_fired, self._taps = True, 0
                self.emit(Press.HOLD)
        elif self._taps and now - self._last_up + _EPS >= GAP_S:
            self._flush()

    def next_wake(self) -> float | None:
        d = self._down_at
        if d is not None and self._fired_on_down:
            return self._next_repeat if self.repeat else None
        if d is not None and Press.HOLD in self.presses and not self._hold_fired:
            return d + HOLD_S
        if d is None and self._taps:
            return self._last_up + GAP_S
        return None

    def _flush(self):
        p = {1: Press.TAP, 2: Press.DOUBLE}.get(self._taps, Press.TRIPLE)
        self._taps = 0
        if p in self.presses:
            self.emit(p)


def action_event(action: str, n: int, source: str, t: float) -> InputEvent:
    """The InputEvent a function becomes (moves are turns, so every tool understands them)."""
    if action == FORWARD:
        return InputEvent(Kind.ROTATE, n, source, t)
    if action == BACK:
        return InputEvent(Kind.ROTATE, -n, source, t)
    if action == SELECT:
        return InputEvent(Kind.CLICK, 0, source, t, action=SELECT)
    return InputEvent(Kind.ACTION, 0, source, t, action=action)


class ControlsHub:
    """The live controls: inputs in, InputEvents out. Thread-safe (keyboard hooks call
    it from their own threads; the Qt main thread ticks it)."""

    def __init__(self, emit: Callable[[InputEvent], None], clock: Callable[[], float] = time.monotonic):
        self.emit = emit
        self.clock = clock
        self._lock = threading.RLock()
        self.controls = Controls()
        self._slots: dict[str, PressRecognizer] = {}

    def set(self, c: Controls):
        with self._lock:
            self.controls = c
            self._slots = {}
            for inp in dict.fromkeys(b.trigger.input for b in c.bindings if not b.trigger.counted):
                mine = [b for b in c.bindings if b.trigger.input == inp]
                presses = {b.trigger.press for b in mine}
                moves = presses == {Press.TAP} and mine[0].action in (FORWARD, BACK)

                def fire(p, inp=inp):
                    a = self.controls.action_for(Trigger(inp, p))
                    if a:
                        self._emit(a, 1, None)
                self._slots[inp] = PressRecognizer(presses, moves, fire)

    def has(self, inp: str) -> bool:
        """A control uses this key / button (the platform should swallow it)."""
        return inp in self._slots

    def key(self, inp: str, down: bool) -> bool:
        with self._lock:
            r = self._slots.get(inp)
            if r is None:
                return False
            (r.down if down else r.up)(self.clock())
            return True

    def pulse(self, inp: str, n: int = 1, source: str | None = None) -> bool:
        """n of an input the device counts itself (earbud gesture, dial turn)."""
        with self._lock:
            a = next((b.action for b in self.controls.bindings if b.trigger.input == inp), None)
        if a is None:
            return False
        self._emit(a, n, source)
        return True

    def _emit(self, action: str, n: int, source: str | None):
        self.emit(action_event(action, n, source or CONTROLLER + "controls", self.clock()))

    def tick(self):
        with self._lock:
            now = self.clock()
            for r in list(self._slots.values()):
                r.tick(now)

    def next_wake(self) -> float | None:
        with self._lock:
            ws = [w for w in (r.next_wake() for r in self._slots.values()) if w is not None]
            return min(ws) if ws else None

    def volume_is_dial(self) -> bool:
        return self.controls.uses("vol:")


# ---------------------------------------------------------------- router

# what the buds' sources send, as inputs
_BUD_KINDS = {Kind.CLICK: "media:play", Kind.DOUBLE: "media:next", Kind.TRIPLE: "media:prev", Kind.HOLD: "media:hold"}
_NATIVE = {"media:play": "play_pause", "media:next": "next", "media:prev": "previous"}


@dataclass
class Captured:
    input: str
    down: bool
    counted: bool = False


class Router:
    """Between every input and the engine.

    - the buds' sources (volume dial, media session, hold sniffer) -> their inputs
    - keyboard / mouse hooks -> key(); returns whether to swallow the key
    - while a Settings page is capturing, every input goes to it instead (nothing acts)
    - off (paused): buds events go straight to the engine (it plays them natively),
      keys are never swallowed
    """

    def __init__(self, post: Callable[[InputEvent], None], media: Callable[[str], None],
                 clock: Callable[[], float] = time.monotonic):
        self.post = post
        self.media = media
        self.hub = ControlsHub(post, clock)
        self.paused = False
        self.capture: Callable[[Captured], None] | None = None
        self.capture_keys = False          # Record: swallow every key, not just bound ones

    def set_controls(self, c: Controls):
        self.hub.set(c)

    def from_source(self, ev: InputEvent) -> None:
        """An event from one of the buds' sources (any thread)."""
        if self.paused:
            self.post(ev)
            return
        if ev.kind == Kind.ROTATE:
            inp, n = ("vol:up" if ev.delta > 0 else "vol:down"), abs(ev.delta)
        elif ev.kind in _BUD_KINDS:
            inp, n = _BUD_KINDS[ev.kind], 1
        else:
            self.post(ev)                   # PRESS / RELEASE / anything else: as before
            return
        cap = self.capture
        if cap:
            cap(Captured(inp, True, counted=True))
            return
        if self.hub.pulse(inp, n, ev.source if ev.kind == Kind.ROTATE else None):
            return
        if inp in _NATIVE:                  # not used by any control: does what it would without Orbit
            self.media(_NATIVE[inp])

    def key(self, inp: str, down: bool) -> bool:
        """A key / mouse button from a hook (hook thread). True = swallow it."""
        if self.paused:
            return False
        cap = self.capture
        if cap:
            if self.capture_keys or self.hub.has(inp):
                cap(Captured(inp, down))
                return True
            return False
        return self.hub.key(inp, down)

    def wants(self, inp: str) -> bool:
        return not self.paused and (bool(self.capture and self.capture_keys) or self.hub.has(inp))
