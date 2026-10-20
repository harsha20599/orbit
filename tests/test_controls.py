"""Controls (orbit/core/controls.py): presses, setups, hub, router, engine. No OS, no Qt.

Mirrors the Android tests (android/app/src/test/.../ControlsTest.kt) and adds the
desktop-only parts: the router between the buds' sources / key hooks and the engine.
"""
import pytest

from orbit.core import controls as c
from orbit.core.controls import (Binding, Captured, Controls, ControlsHub, Press, PressRecognizer, Presets,
                                 Router, Trigger)
from orbit.core.engine import State
from orbit.core.events import InputEvent, Kind

from tests.test_engine import make


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t

    def adv(self, s):
        self.t += s


# ================================================================ presses

def rec(*presses, repeat=False):
    got = []
    return PressRecognizer(set(presses), repeat, got.append), got


def press(r, clock, hold=0.06, gap=0.0, step=0.01):
    r.down(clock.t)
    end = clock.t + hold
    while clock.t < end - 1e-9:
        clock.adv(step)
        r.tick(clock.t)
    r.up(clock.t)
    end = clock.t + gap
    while clock.t < end - 1e-9:
        clock.adv(step)
        r.tick(clock.t)


def test_tap_only_fires_on_key_down():
    r, got = rec(Press.TAP)
    r.down(1.0)
    assert got == [Press.TAP]
    r.up(1.05)
    assert got == [Press.TAP]


def test_moves_repeat_while_held_and_stop_on_release():
    r, got = rec(Press.TAP, repeat=True)
    r.down(1.0)
    r.tick(1.0 + c.REPEAT_DELAY_S + 2 * c.REPEAT_EVERY_S)
    assert len(got) == 4
    r.up(2.0)
    r.tick(5.0)
    assert len(got) == 4


def test_tap_without_repeat_never_repeats():
    r, got = rec(Press.TAP, repeat=False)
    r.down(1.0)
    r.tick(3.0)
    assert got == [Press.TAP]


def test_tap_and_hold_need_no_gap_wait():
    k = Clock()
    r, got = rec(Press.TAP, Press.HOLD)
    press(r, k, hold=0.08)
    assert got == [Press.TAP]
    got.clear()
    r.down(k.t)
    k.adv(c.HOLD_S)
    r.tick(k.t)
    assert got == [Press.HOLD]               # at the threshold, before the release
    r.up(k.t + 0.5)
    assert got == [Press.HOLD]


def test_double_and_triple():
    k = Clock()
    r, got = rec(Press.TAP, Press.DOUBLE, Press.TRIPLE)
    press(r, k, gap=0.4)
    assert got == [Press.TAP]
    got.clear()
    press(r, k, gap=0.1); press(r, k, gap=0.4)
    assert got == [Press.DOUBLE]
    got.clear()
    press(r, k, gap=0.1); press(r, k, gap=0.1); press(r, k)
    assert got == [Press.TRIPLE]             # no wait after the third


def test_double_only_ignores_singles_and_fires_on_second_release():
    k = Clock()
    r, got = rec(Press.DOUBLE)
    press(r, k, gap=0.4)
    assert got == []
    press(r, k, gap=0.1); press(r, k)
    assert got == [Press.DOUBLE]


def test_slow_taps_are_two_singles():
    k = Clock()
    r, got = rec(Press.TAP, Press.DOUBLE)
    press(r, k, gap=0.5); press(r, k, gap=0.5)
    assert got == [Press.TAP, Press.TAP]


def test_os_key_repeat_is_ignored():
    r, got = rec(Press.TAP)
    r.down(1.0); r.down(1.03); r.down(1.06)
    assert got == [Press.TAP]


def test_stray_up_without_down_is_harmless():
    r, got = rec(Press.TAP, Press.DOUBLE)
    r.up(1.0)
    r.tick(5.0)
    assert got == []


def test_next_wake_tracks_deadlines():
    r, _ = rec(Press.HOLD)
    assert r.next_wake() is None
    r.down(1.0)
    assert r.next_wake() == pytest.approx(1.0 + c.HOLD_S)
    r2, _ = rec(Press.TAP, Press.DOUBLE)
    r2.down(1.0); r2.up(1.05)
    assert r2.next_wake() == pytest.approx(1.05 + c.GAP_S)


# ================================================================ triggers, labels

def test_labels():
    assert Trigger("key:volumeup", Press.DOUBLE).label() == "Volume + · double tap"
    assert Trigger("key:ctrl+shift+space").label() == "Ctrl+Shift+Space · tap"
    assert Trigger("key:f13", Press.HOLD).label() == "F13 · hold"
    assert Trigger("mouse:forward").label() == "Mouse forward button · tap"
    assert Trigger("media:next").label() == "Earbuds: double press"
    assert Trigger("vol:up").label() == "Dial forward"


def test_key_input_orders_modifiers():
    assert c.key_input("f13", {"shift", "ctrl"}) == "key:ctrl+shift+f13"
    assert c.key_input("a") == "key:a"
    assert c.key_input("space", ["alt", "cmd"]) == "key:cmd+alt+space"


def test_counted_inputs_are_always_taps():
    co, _ = Controls().add(c.OPEN, Trigger("media:next", Press.HOLD))
    assert co.triggers(c.OPEN) == [Trigger("media:next", Press.TAP)]


def test_action_labels():
    assert c.action_label(c.SELECT) == "Single press / Select"
    assert c.action_label(c.BACK) == "Previous" and c.action_label(c.FORWARD) == "Next"
    assert c.action_label("custom:keys:ctrl+shift+m") == "Press Ctrl+Shift+M"
    assert c.action_label("custom:launch:notepad") == "Open notepad"


# ================================================================ controls

def test_every_preset_opens_moves_and_selects():
    for p in Presets.ALL:
        for a in (c.OPEN, c.SELECT, c.FORWARD):
            assert p.controls.triggers(a), (p.name, a)


def test_presets_only_set_the_four_functions():
    for p in Presets.ALL:
        assert all(b.action in c.CORE for b in p.controls.bindings), p.name


def test_default_is_the_cmf_dial():
    d = Presets.default()
    assert d.preset == "cmf"
    assert d.triggers(c.FORWARD) == [Trigger("vol:up")]
    assert d.triggers(c.OPEN) == [Trigger("media:next")]


def test_adding_moves_a_trigger_and_says_from_where():
    co = Presets.MEDIA_KEYS.controls
    co2, lost = co.add(c.SELECT, Trigger("key:volumeup"))
    assert lost == c.FORWARD
    assert co2.triggers(c.FORWARD) == []
    assert Trigger("key:volumeup") in co2.triggers(c.SELECT)
    assert co2.preset is None


def test_a_function_can_have_several_triggers():
    co = Presets.CMF.controls
    co, _ = co.add(c.FORWARD, Trigger("key:f14"))
    assert len(co.triggers(c.FORWARD)) == 2
    co = co.remove(c.FORWARD, Trigger("vol:up"))
    assert co.triggers(c.FORWARD) == [Trigger("key:f14")]
    assert co.clear(c.FORWARD).triggers(c.FORWARD) == []


def test_actions_list_core_then_extras():
    co, _ = Presets.CMF.controls.add(c.LAST_TOOL, Trigger("media:prev"))
    assert co.actions == [c.SELECT, c.OPEN, c.BACK, c.FORWARD, c.LAST_TOOL]


def test_uses_exact_or_prefix():
    co = Presets.CMF.controls
    assert co.uses("vol:") and co.uses("media:play") and not co.uses("media:pla") and not co.uses("key:")


def test_combine_keeps_every_trigger():
    co = Presets.combine(Presets.CMF, Presets.MEDIA_KEYS)
    assert len(co.triggers(c.FORWARD)) == 2 and co.preset is None
    assert Presets.combine(Presets.MOUSE).preset == "mouse"


def test_json_round_trip():
    co, _ = Presets.MOUSE.controls.add("custom:keys:ctrl+shift+m", Trigger("key:f15", Press.DOUBLE))
    back = Controls.from_json(co.to_json())
    assert back.bindings == co.bindings


@pytest.mark.parametrize("bad", [None, [], "x", {"bindings": "nope"}, {}])
def test_unreadable_json_falls_back_to_the_default(bad):
    assert Controls.from_json(bad) == Presets.default()


def test_bad_rows_are_skipped_not_fatal():
    d = {"bindings": [{"action": "select", "input": "key:f13", "press": "tap"},
                      {"action": "select", "input": "key:f14", "press": "wiggle"},
                      {"action": 3, "input": "key:f15"}, {"input": "key:f16"}, "junk",
                      {"action": "open_wheel", "input": "", "press": "tap"}]}
    assert Controls.from_json(d).triggers(c.SELECT) == [Trigger("key:f13")]


# ================================================================ hub

def hub():
    k = Clock()
    events = []
    return ControlsHub(events.append, k), events, k


def test_hub_swallows_only_its_inputs():
    h, events, k = hub()
    h.set(Presets.MEDIA_KEYS.controls)
    assert h.has("key:volumeup") and not h.has("key:a")
    assert h.key("key:volumeup", True) and h.key("key:volumeup", False)
    assert not h.key("key:a", True)
    assert [e.delta for e in events] == [1]


def test_shortcuts_match_exactly():
    h, events, k = hub()
    h.set(Controls((Binding(c.OPEN, Trigger("key:ctrl+space")),)))
    assert h.has("key:ctrl+space") and not h.has("key:space")


def test_hub_emits_the_right_events():
    h, events, k = hub()
    h.set(Presets.F_KEYS.controls)
    for inp in ("key:f13", "key:f14", "key:f15", "key:f16"):
        h.key(inp, True); h.key(inp, False)
    assert [(e.kind, e.delta, e.action) for e in events] == [
        (Kind.ROTATE, -1, None), (Kind.ROTATE, 1, None), (Kind.CLICK, 0, c.SELECT), (Kind.ACTION, 0, c.OPEN)]
    assert all(e.source.startswith(c.CONTROLLER) for e in events)


def test_hub_hold_through_tick():
    h, events, k = hub()
    h.set(Presets.MOUSE.controls)          # back: tap = previous, hold = select
    h.key("mouse:back", True)
    k.adv(c.HOLD_S); h.tick()
    h.key("mouse:back", False)
    assert [e.action for e in events] == [c.SELECT]


def test_pulses_use_their_tap_binding_with_count():
    h, events, k = hub()
    h.set(Presets.CMF.controls)
    assert h.pulse("vol:up", 3, "avrcp-volume")
    assert events[-1].kind == Kind.ROTATE and events[-1].delta == 3 and events[-1].source == "avrcp-volume"
    assert h.pulse("media:next") and events[-1].action == c.OPEN
    assert not h.pulse("media:hold")
    assert h.volume_is_dial()


def test_next_wake_none_when_idle():
    h, _, _ = hub()
    h.set(Presets.MOUSE.controls)
    assert h.next_wake() is None
    h.key("mouse:forward", True)
    assert h.next_wake() is not None


def test_reconfiguring_mid_press_is_safe():
    h, events, k = hub()
    h.set(Presets.MOUSE.controls)
    h.key("mouse:back", True)
    h.set(Presets.F_KEYS.controls)
    h.key("mouse:back", False)
    k.adv(1); h.tick()
    assert events == []


# ================================================================ router

def router():
    k = Clock()
    posted, media = [], []
    r = Router(posted.append, media.append, k)
    return r, posted, media, k


def bud(kind, delta=0, source="smtc"):
    return InputEvent(kind, delta, source)


def test_router_turns_bud_events_into_functions():
    r, posted, media, _ = router()
    r.set_controls(Presets.CMF.controls)
    r.from_source(bud(Kind.DOUBLE))
    r.from_source(bud(Kind.ROTATE, 2, "avrcp-volume"))
    r.from_source(bud(Kind.CLICK))
    assert [(e.kind, e.delta, e.action) for e in posted] == [
        (Kind.ACTION, 0, c.OPEN), (Kind.ROTATE, 2, None), (Kind.CLICK, 0, c.SELECT)]
    assert posted[1].source == "avrcp-volume"          # still the dial: the engine leaves volume native in Volume
    assert media == []


def test_unused_bud_presses_still_control_music():
    r, posted, media, _ = router()
    r.set_controls(Presets.F_KEYS.controls)               # nothing from the buds in use
    r.from_source(bud(Kind.CLICK)); r.from_source(bud(Kind.DOUBLE)); r.from_source(bud(Kind.TRIPLE))
    r.from_source(bud(Kind.ROTATE, 1, "avrcp-volume")); r.from_source(bud(Kind.HOLD, source="bt-etw"))
    assert media == ["play_pause", "next", "previous"]
    assert posted == []


def test_off_passes_everything_through():
    r, posted, media, _ = router()
    r.set_controls(Presets.CMF.controls)
    r.paused = True
    e = bud(Kind.CLICK)
    r.from_source(e)
    assert posted == [e]
    assert r.key("key:volumeup", True) is False and not r.wants("key:volumeup")


def test_press_release_events_pass_unchanged():
    r, posted, _, _ = router()
    e = bud(Kind.PRESS)
    r.from_source(e)
    assert posted == [e]


def test_capture_takes_everything_and_nothing_acts():
    r, posted, media, _ = router()
    r.set_controls(Presets.MEDIA_KEYS.controls)
    seen = []
    r.capture = seen.append
    r.from_source(bud(Kind.CLICK))
    assert r.key("key:volumeup", True) is True           # bound: swallowed, shown
    assert r.key("key:a", True) is False                 # not bound, not recording: typing works
    r.capture_keys = True
    assert r.key("key:a", True) is True and r.wants("key:a")
    assert [s.input for s in seen] == ["media:play", "key:volumeup", "key:a"]
    assert posted == [] and media == []
    r.capture = None
    r.capture_keys = False
    assert not r.wants("key:a")


def test_router_key_drives_the_hub():
    r, posted, _, _ = router()
    r.set_controls(Presets.MEDIA_KEYS.controls)
    assert r.wants("key:playpause")
    assert r.key("key:playpause", True)
    assert posted[-1].action == c.SELECT


# ================================================================ engine

def test_engine_open_toggles_and_other_actions_close_the_wheel():
    e, out, ui, rot = make()
    e.handle(InputEvent(Kind.ACTION, 0, "controller:x", action=c.OPEN))
    assert e.state == State.WHEEL
    e.handle(InputEvent(Kind.ACTION, 0, "controller:x", action=c.OPEN))
    assert e.state == State.TOOL
    e.open_wheel()
    e.handle(InputEvent(Kind.ACTION, 0, "controller:x", action=c.LAST_TOOL))
    assert e.state == State.TOOL


def test_engine_select_commits_in_the_wheel():
    e, out, ui, rot = make()
    e.handle(InputEvent(Kind.ACTION, 0, "controller:x", action=c.OPEN))
    e.handle(InputEvent(Kind.ROTATE, 2, "controller:x"))
    e.handle(InputEvent(Kind.CLICK, 0, "controller:x", action=c.SELECT))
    assert e.state == State.TOOL and e.tool.id == "scroll"


def test_engine_select_in_a_tool_ignores_old_open_wheel_gesture():
    e, out, ui, rot = make()
    e.open_with = {"click"}                                  # an old settings.json said click opens the wheel
    e.handle(InputEvent(Kind.CLICK, 0, "controller:x", action=c.SELECT))
    assert e.state == State.TOOL
    assert ("media", "play_pause") in out.log                # the usual press: play / pause


def test_engine_custom_command_runs_the_action():
    e, out, ui, rot = make()
    e.handle(InputEvent(Kind.ACTION, 0, "controller:x", action="custom:keys:ctrl+shift+m"))
    assert ("keys", "ctrl+shift+m") in out.log


def test_engine_last_tool_and_assistant():
    e, out, ui, rot = make()
    e.set_tool("scroll")
    e.handle(InputEvent(Kind.ACTION, 0, "controller:x", action=c.LAST_TOOL))
    assert e.tool.id == "volume"
    before = len(out.log)
    e.handle(InputEvent(Kind.ACTION, 0, "controller:x", action=c.ASSISTANT))
    assert len(out.log) > before                             # the hold chain ran (Claude on Windows)


def test_engine_unknown_action_is_harmless():
    e, out, ui, rot = make()
    e.handle(InputEvent(Kind.ACTION, 0, "controller:x", action="nope"))
    e.handle(InputEvent(Kind.ACTION, 0, "controller:x", action=None))
    assert e.state == State.TOOL


def test_controller_turns_in_volume_step_the_volume_but_the_dial_does_not():
    e, out, ui, rot = make()
    steps = []
    rot.nudge = steps.append
    e.handle(InputEvent(Kind.ROTATE, 1, "avrcp-volume"))     # the buds already moved the volume
    e.handle(InputEvent(Kind.ROTATE, -2, "controller:controls"))
    assert steps == [-2]


def test_controller_volume_falls_back_to_keys_without_buds():
    e, out, ui, rot = make()
    rot.level = lambda: None
    rot.nudge = lambda n: pytest.fail("no buds: must not nudge")
    e.handle(InputEvent(Kind.ROTATE, 2, "controller:controls"))
    assert out.log.count(("keys", "volumeup")) == 2


def test_volume_stays_volume_when_no_control_uses_the_dial():
    e, out, ui, rot = make()
    e.set_volume_dial(False)
    e.set_tool("scroll")
    assert rot.passthrough is True                           # scroll would consume the dial; not now
    e.open_wheel()
    assert rot.passthrough is True                           # nor duck it
    e.set_volume_dial(True)
    assert rot.passthrough is False


def test_end_to_end_mouse_buttons_drive_the_wheel():
    e, out, ui, rot = make()
    k = Clock()
    r = Router(e.handle, out.media, k)
    r.set_controls(Presets.MOUSE.controls)
    r.key("mouse:forward", True); k.adv(c.HOLD_S); r.hub.tick(); r.key("mouse:forward", False)
    assert e.state == State.WHEEL
    for _ in range(2):
        r.key("mouse:forward", True); k.adv(0.05); r.key("mouse:forward", False)
    r.key("mouse:back", True); k.adv(c.HOLD_S); r.hub.tick(); r.key("mouse:back", False)
    assert e.state == State.TOOL and e.tool.id == "scroll"
