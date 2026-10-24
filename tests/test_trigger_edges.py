"""Where triggers break in real life, one test each: ups that never come, modifiers let go
first or lost under the lock screen, the OS repeating a held key, settings saved mid-press,
presses right on the timing edges, keys bound only to a hold, fast knob clicks, AltGr,
trackpads (palms, fingers added or lifted one by one) and scroll (trackpad fractions,
momentum). Pure: no OS calls, any OS.
"""
import sys

import pytest

from orbit.core.controls import (BACK, FORWARD, GAP_S, HOLD_S, MAX_HOLD_S, OPEN, REPEAT_DELAY_S, REPEAT_EVERY_S, SELECT,
                                 Binding, Controls, Press, Router, Trigger)
from orbit.core.events import Kind
from orbit.core.touch import TouchGestures
from orbit.platform.mac import keytap
from orbit.platform.windows import keynames as wk


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def setup(*bindings):
    clock, posted = Clock(), []
    r = Router(posted.append, lambda m: None, clock)
    r.set_controls(Controls(tuple(Binding(a, t) for a, t in bindings)))
    return r, posted, clock


def run(r, clock, s):
    end = clock.t + s
    while clock.t < end:
        clock.t += 0.01
        r.hub.tick()


def moves(posted):
    return sum(e.delta for e in posted if e.kind == Kind.ROTATE)


def acts(posted):
    return [e.action for e in posted if e.action]


VOLUP, VOLDOWN, F13, F14, B = 0xAF, 0xAE, 0x7C, 0x7D, 0x42
CTRL, LWIN, ALT = 0xA2, 0x5B, 0xA4


def win_tracker(r, down_keys=None, masks=None):
    return wk.KeyTracker(r.wants, r.key, r.wants_gesture, r.gesture,
                         is_down=(lambda vk: vk in down_keys) if down_keys is not None else None,
                         mask=(lambda: masks.append(1)) if masks is not None else None)


# ================================================================ presses (core)

def test_lost_key_up_stops_repeating_after_the_limit():
    r, posted, clock = setup((FORWARD, Trigger("key:f13")))
    t = win_tracker(r)
    t.keyboard(F13, True)
    run(r, clock, MAX_HOLD_S + 0.5)
    after = moves(posted)
    run(r, clock, 5)
    assert moves(posted) == after and after > 10


def test_release_all_stops_a_held_repeat_at_once():
    r, posted, clock = setup((FORWARD, Trigger("key:f13")))
    t = win_tracker(r)
    t.keyboard(F13, True)
    run(r, clock, REPEAT_DELAY_S + 3 * REPEAT_EVERY_S)
    before = moves(posted)
    t.release_all()
    r.hub.release_all()
    run(r, clock, 3)
    assert moves(posted) == before
    assert t.keyboard(F13, False) is False              # the late up, if it comes, passes


def test_double_just_inside_and_just_outside_the_gap():
    r, posted, clock = setup((SELECT, Trigger("key:f13")), (OPEN, Trigger("key:f13", Press.DOUBLE)))
    t = win_tracker(r)
    for gap in (GAP_S - 0.02, GAP_S + 0.02):
        posted.clear()
        t.keyboard(F13, True); clock.t += 0.05; t.keyboard(F13, False)
        run(r, clock, gap)
        t.keyboard(F13, True); clock.t += 0.05; t.keyboard(F13, False)
        run(r, clock, 0.5)
        assert acts(posted) == ([OPEN] if gap < GAP_S else [SELECT, SELECT])


def test_a_count_nobody_uses_is_that_many_taps():
    r, posted, clock = setup((SELECT, Trigger("key:f13")), (OPEN, Trigger("key:f13", Press.TRIPLE)))
    t = win_tracker(r)
    for _ in range(2):
        t.keyboard(F13, True); clock.t += 0.05; t.keyboard(F13, False); clock.t += 0.1
    run(r, clock, 0.5)
    assert acts(posted) == [SELECT, SELECT]


def test_released_just_before_hold_is_a_tap_and_just_after_is_a_hold():
    r, posted, clock = setup((SELECT, Trigger("key:f13")), (OPEN, Trigger("key:f13", Press.HOLD)))
    t = win_tracker(r)
    t.keyboard(F13, True); run(r, clock, HOLD_S - 0.03); t.keyboard(F13, False)
    run(r, clock, 0.5)
    t.keyboard(F13, True); run(r, clock, HOLD_S + 0.03); t.keyboard(F13, False)
    run(r, clock, 0.5)
    assert acts(posted) == [SELECT, OPEN]


def test_fast_knob_clicks_are_every_one_a_move():
    # a Bluetooth keyboard knob: volume key taps ~40 ms apart
    r, posted, clock = setup((FORWARD, Trigger("key:volumeup")), (BACK, Trigger("key:volumedown")))
    t = win_tracker(r)
    for vk, n in ((VOLUP, 12), (VOLDOWN, 5)):
        for _ in range(n):
            t.keyboard(vk, True); clock.t += 0.015; t.keyboard(vk, False); clock.t += 0.025
    assert moves(posted) == 7


def test_os_key_repeat_counts_once():
    r, posted, clock = setup((SELECT, Trigger("key:f13")))
    t = win_tracker(r)
    for _ in range(6):
        assert t.keyboard(F13, True) is True
    t.keyboard(F13, False)
    assert acts(posted) == [SELECT]


def test_controls_saved_mid_press_still_swallow_the_up():
    r, posted, clock = setup((FORWARD, Trigger("key:f13")))
    t = win_tracker(r)
    assert t.keyboard(F13, True)
    r.set_controls(Controls((Binding(BACK, Trigger("key:f14")),)))
    assert t.keyboard(F13, False) is True              # apps never see a lone up
    run(r, clock, 2)
    assert moves(posted) == 1


# ================================================================ the key's own job (replay)

def test_key_bound_only_to_hold_is_re_sent_on_a_tap():
    r, posted, clock = setup((OPEN, Trigger("key:volumeup", Press.HOLD)))
    sent = []
    r.hub.replay = lambda inp, n: sent.append((inp, n))
    t = win_tracker(r)
    t.keyboard(VOLUP, True); clock.t += 0.08; t.keyboard(VOLUP, False)
    run(r, clock, 0.5)
    assert sent == [("key:volumeup", 1)] and posted == []
    t.keyboard(VOLUP, True); run(r, clock, HOLD_S + 0.1); t.keyboard(VOLUP, False)
    run(r, clock, 0.5)
    assert sent == [("key:volumeup", 1)] and acts(posted) == [OPEN]     # a hold is never re-sent


def test_key_bound_only_to_double_gives_back_a_single():
    r, posted, clock = setup((OPEN, Trigger("key:f13", Press.DOUBLE)))
    sent = []
    r.hub.replay = lambda inp, n: sent.append((inp, n))
    t = win_tracker(r)
    t.keyboard(F13, True); clock.t += 0.05; t.keyboard(F13, False)
    run(r, clock, GAP_S + 0.05)
    assert sent == [("key:f13", 1)]


def test_nothing_re_sent_when_a_tap_is_in_use():
    r, posted, clock = setup((SELECT, Trigger("key:f13")), (OPEN, Trigger("key:f13", Press.HOLD)))
    sent = []
    r.hub.replay = lambda inp, n: sent.append((inp, n))
    t = win_tracker(r)
    t.keyboard(F13, True); clock.t += 0.05; t.keyboard(F13, False)
    run(r, clock, 0.5)
    assert sent == [] and acts(posted) == [SELECT]


def test_replay_sends_through_output():
    from orbit.core.controls import replay_with

    class Out:
        def __init__(self):
            self.log = []

        def volume_step(self, n):
            self.log.append(("vol", n))

        def media(self, c):
            self.log.append(("media", c))

        def keys(self, k):
            self.log.append(("keys", k))
    out = Out()
    send = replay_with(out)
    import threading
    before = set(threading.enumerate())
    for inp, n in (("key:volumedown", 2), ("key:playpause", 1), ("key:ctrl+f13", 1), ("mouse:back", 1)):
        send(inp, n)
    for th in set(threading.enumerate()) - before:
        th.join(1)
    assert sorted(out.log) == sorted([("vol", -2), ("media", "play_pause"), ("keys", "f13")])


# ================================================================ Windows hook bookkeeping

def test_win_lost_win_key_up_is_dropped_by_the_sweep():
    # Win+L: the lock screen takes the Win up, so Orbit would read every later key as Win+key
    r, posted, clock = setup((FORWARD, Trigger("key:f13")))
    down = {LWIN}
    t = win_tracker(r, down)
    t.keyboard(LWIN, True)
    down.clear()                                    # Windows: Win is up (we never saw it)
    t.sweep()
    assert t.keyboard(F13, True) is True            # plain F13 again, not Win+F13
    assert moves(posted) == 1


def test_win_sweep_keeps_modifiers_that_are_really_down():
    r, posted, clock = setup((FORWARD, Trigger("key:ctrl+f13")))
    t = win_tracker(r, {CTRL})
    t.keyboard(CTRL, True)
    t.sweep()
    assert t.keyboard(F13, True) is True and moves(posted) == 1


def test_win_sweep_never_lets_go_of_a_swallowed_key():
    # Windows never sees a key Orbit swallowed as down, so the sweep must not "finish" it
    r, posted, clock = setup((OPEN, Trigger("key:f13", Press.HOLD)))
    t = win_tracker(r, set())
    t.keyboard(F13, True)
    for _ in range(4):
        run(r, clock, 0.25)
        t.sweep()
    assert acts(posted) == [OPEN]


def test_win_mask_key_when_swallowing_under_win_or_alt():
    r, posted, clock = setup((SELECT, Trigger("key:win+f13")), (FORWARD, Trigger("key:alt+f14")), (BACK, Trigger("key:f13")))
    masks = []
    t = win_tracker(r, masks=masks)
    t.keyboard(LWIN, True); t.keyboard(F13, True); t.keyboard(F13, False); t.keyboard(LWIN, False)
    t.keyboard(ALT, True); t.keyboard(F14, True); t.keyboard(F14, False); t.keyboard(ALT, False)
    t.keyboard(F13, True); t.keyboard(F13, False)            # no modifier: no mask
    t.keyboard(LWIN, True); t.keyboard(B, True); t.keyboard(B, False); t.keyboard(LWIN, False)  # not ours: no mask
    assert len(masks) == 2


def test_win_release_all_forgets_held_modifiers():
    r, posted, clock = setup((FORWARD, Trigger("key:f13")))
    t = win_tracker(r)
    t.keyboard(LWIN, True)
    t.release_all()
    assert t.keyboard(F13, True) is True


def test_win_altgr_fake_ctrl():
    assert wk.altgr_fake_ctrl(0xA2, 0x21D)
    assert not wk.altgr_fake_ctrl(0xA2, 0x1D)                # a real left Ctrl
    assert not wk.altgr_fake_ctrl(0xA3, 0x21D)


def test_win_only_tagged_events_are_ours():
    assert wk.own_event(wk.ORBIT_TAG)
    for extra in (0, 1, 0xFFFFFFFF):                          # Windows' HID keys, PowerToys' tag, others
        assert not wk.own_event(extra)


@pytest.mark.skipif(sys.platform != "win32", reason="imports Windows-only DLLs (user32) at module load")
def test_win_hook_quiet_watchdog_handles_tick_wrap():
    from orbit.platform.windows.input_keys import hooks_quiet
    assert hooks_quiet(10_000, 7_000)
    assert not hooks_quiet(10_000, 9_000)
    assert not hooks_quiet(9_000, 10_000)                     # hooks saw input after Windows' last: fine
    assert hooks_quiet(500, 0xFFFFFFFF - 2_000)               # GetTickCount wrapped (49.7 days)


def test_win_scroll_fractions_add_up_and_direction_change_starts_over():
    r, posted, clock = setup((FORWARD, Trigger("scroll:ctrl+down")), (BACK, Trigger("scroll:ctrl+up")))
    t = win_tracker(r)
    t.keyboard(CTRL, True)
    up = (40 << 16)                                           # a precision touchpad: 40 of 120 per message
    down = ((-40 & 0xFFFF) << 16)
    for _ in range(2):
        t.mouse(wk.WM_MOUSEWHEEL, up)
    assert moves(posted) == 0
    t.mouse(wk.WM_MOUSEWHEEL, down)                           # direction changed: the 80 is dropped
    for _ in range(2):
        t.mouse(wk.WM_MOUSEWHEEL, down)
    assert moves(posted) == 1
    t.keyboard(CTRL, False)
    assert t.mouse(wk.WM_MOUSEWHEEL, down) is False           # plain scroll is never ours


# ================================================================ macOS tap bookkeeping

def mac_tracker(r):
    return keytap.TapTracker(r.wants, r.key)


def test_mac_cmd_let_go_first_still_pairs_the_up():
    r, posted, clock = setup((FORWARD, Trigger("key:cmd+f13")))
    t = mac_tracker(r)
    assert t.key("f13", {"cmd"}, True, False)
    assert t.key("f13", set(), False, False)                 # up arrives without cmd
    run(r, clock, 3)
    assert moves(posted) == 1


def test_mac_media_key_states():
    assert keytap.system_key(8, (16 << 16) | (0xA << 8)) == ("playpause", True, False)
    assert keytap.system_key(8, (16 << 16) | (0xB << 8)) == ("playpause", False, False)
    assert keytap.system_key(8, (0 << 16) | (0xA << 8) | 1) == ("volumeup", True, True)
    assert keytap.system_key(8, (2 << 16) | (0xA << 8)) is None      # brightness: not ours
    assert keytap.system_key(7, (16 << 16) | (0xA << 8)) is None     # other subtype
    assert keytap.system_key(8, (16 << 16) | (0xC << 8)) is None     # unknown state


def test_mac_pinch_only_counts_when_it_ends():
    g = keytap.Gestures()
    assert g.magnify(0.1, keytap.PHASE_BEGAN) is None
    assert g.magnify(0.1, 0) is None
    assert g.magnify(0.0, keytap.PHASE_ENDED) == "touchpad:pinch-out"
    g.magnify(0.3, keytap.PHASE_BEGAN)
    assert g.magnify(0.0, keytap.PHASE_CANCELLED) is None             # cancelled: nothing
    g.magnify(0.05, keytap.PHASE_BEGAN)
    assert g.magnify(0.0, keytap.PHASE_ENDED) is None                 # too small


def test_mac_scroll_fractions_and_momentum():
    n = keytap.ScrollNotches()
    assert n.feed(0.4, 0, {"ctrl"}) == ("scroll:ctrl+up", 0)
    assert n.feed(0.7, 0, {"ctrl"}) == ("scroll:ctrl+up", 1)
    assert n.feed(5.0, 0, {"ctrl"}, momentum=True) == ("scroll:ctrl+up", 0)   # the flick's coasting: not more steps
    assert n.feed(1.0, 0, set()) == (None, 0)


# ================================================================ Windows trackpad

def touch():
    out = []
    return TouchGestures(out.append), out


def test_touch_three_finger_swipe_and_tap():
    g, out = touch()
    pts = {1: (0.4, 0.5), 2: (0.5, 0.5), 3: (0.6, 0.5)}
    g.frame(pts, 0.0)
    g.frame({k: (x + 0.2, y) for k, (x, y) in pts.items()}, 0.1)
    g.frame({}, 0.15)
    g.frame(pts, 1.0)
    g.frame({}, 1.1)
    assert out == ["touchpad:3-swipe-right", "touchpad:3-tap"]


def test_touch_fingers_lifted_one_by_one_still_one_swipe():
    g, out = touch()
    pts = {1: (0.4, 0.5), 2: (0.5, 0.5), 3: (0.6, 0.5)}
    g.frame(pts, 0.0)
    moved = {k: (x, y - 0.3) for k, (x, y) in pts.items()}
    g.frame(moved, 0.1)
    g.frame({1: moved[1], 2: moved[2]}, 0.12)
    g.frame({1: moved[1]}, 0.14)
    g.frame({}, 0.16)
    assert out == ["touchpad:3-swipe-up"]


def test_touch_fourth_finger_landing_makes_it_a_four_finger_gesture():
    g, out = touch()
    three = {1: (0.4, 0.5), 2: (0.5, 0.5), 3: (0.6, 0.5)}
    g.frame(three, 0.0)
    g.frame({**three, 4: (0.7, 0.5)}, 0.05)
    g.frame({}, 0.1)
    assert out == ["touchpad:4-tap"]


def test_touch_two_fingers_and_slow_resting_fingers_are_never_ours():
    g, out = touch()
    g.frame({1: (0.4, 0.5), 2: (0.6, 0.5)}, 0.0)
    g.frame({1: (0.4, 0.9), 2: (0.6, 0.9)}, 0.2)
    g.frame({}, 0.3)
    three = {1: (0.4, 0.5), 2: (0.5, 0.5), 3: (0.6, 0.5)}
    g.frame(three, 1.0)
    g.frame({}, 2.0)                                           # rested a second: not a tap
    assert out == []


def test_mac_release_all_after_secure_input():
    # Secure Input: the tap stops seeing keys, so the up of a held one never comes
    r, posted, clock = setup((FORWARD, Trigger("key:f13")))
    t = mac_tracker(r)
    t.key("f13", set(), True, False)
    t.release_all()
    r.hub.release_all()
    run(r, clock, 3)
    assert moves(posted) == 1
    assert t.key("f13", set(), False, False) is False         # a late up passes


@pytest.mark.skipif(sys.platform != "win32", reason="imports Windows-only DLLs (user32) at module load")
def test_touchpad_palm_is_not_a_finger():
    from orbit.platform.windows.touchpad import U_CONFIDENCE, U_TIP, _Device
    d = _Device.__new__(_Device)                     # only the finger rule, no HID
    d.confidence = False
    assert d.finger_down({U_TIP})                    # pad never said: every touch counts
    assert d.finger_down({U_TIP, U_CONFIDENCE})      # now it has said
    assert not d.finger_down({U_TIP})                # so a touch without it is a palm
    assert not d.finger_down({U_CONFIDENCE})         # lifted
