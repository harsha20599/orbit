"""Key / mouse capture bookkeeping (Windows hooks, macOS event tap): pure parts, any OS."""
from orbit.core.controls import Binding, Controls, Press, Presets, Router, Trigger
from orbit.platform.mac import keytap
from orbit.platform.windows import keynames as wk


class Clock:
    t = 100.0

    def __call__(self):
        return self.t


def router(controls):
    posted = []
    r = Router(posted.append, lambda m: None, Clock())
    r.set_controls(controls)
    return r, posted


# ================================================================ Windows

def tracker(controls):
    r, posted = router(controls)
    return wk.KeyTracker(r.wants, r.key), r, posted


def test_win_names():
    assert wk.VK_NAMES[0x7C] == "f13" and wk.VK_NAMES[0x87] == "f24"
    assert wk.VK_NAMES[0xAF] == "volumeup" and wk.VK_NAMES[0xB3] == "playpause"
    assert wk.VK_NAMES[ord("A")] == "a" and wk.VK_NAMES[ord("7")] == "7"


def test_win_bound_key_is_swallowed_down_and_up():
    t, r, posted = tracker(Presets.F_KEYS.controls)
    assert t.keyboard(0x7C, True) is True                  # F13
    assert t.keyboard(0x7C, False) is True
    assert [e.delta for e in posted] == [-1]               # F13 = previous


def test_win_unbound_keys_pass():
    t, r, posted = tracker(Presets.F_KEYS.controls)
    assert t.keyboard(ord("A"), True) is False
    assert t.keyboard(ord("A"), False) is False
    assert t.keyboard(0xFF, True) is False                 # unknown vk
    assert posted == []


def test_win_modifiers_never_swallowed_but_make_shortcuts():
    t, r, posted = tracker(Controls((Binding("open_wheel", Trigger("key:ctrl+space")),)))
    assert t.keyboard(0xA2, True) is False                 # left ctrl down: passes
    assert t.keyboard(0x20, True) is True                  # ctrl+space: ours
    assert t.keyboard(0x20, False) is True
    assert t.keyboard(0xA2, False) is False
    assert t.keyboard(0x20, True) is False                 # plain space types again
    assert [e.action for e in posted] == ["open_wheel"]


def test_win_up_is_swallowed_even_if_modifier_released_first():
    t, r, posted = tracker(Controls((Binding("select", Trigger("key:ctrl+f13")),)))
    t.keyboard(0x11, True); assert t.keyboard(0x7C, True) is True
    t.keyboard(0x11, False)                                 # ctrl up before F13 up
    assert t.keyboard(0x7C, False) is True                  # still ours: no stray F13 up for apps


def test_win_up_is_swallowed_even_if_orbit_turned_off_mid_press():
    t, r, posted = tracker(Presets.F_KEYS.controls)
    assert t.keyboard(0x7C, True) is True
    r.paused = True
    assert t.keyboard(0x7C, False) is True
    assert t.keyboard(0x7C, True) is False                  # off now: passes


def test_win_os_repeat_downs_stay_swallowed():
    t, r, posted = tracker(Presets.MEDIA_KEYS.controls)
    assert all(t.keyboard(0xAF, True) for _ in range(5))    # volume up held
    assert t.keyboard(0xAF, False) is True


def test_win_mouse_side_buttons():
    t, r, posted = tracker(Presets.MOUSE.controls)
    assert wk.mouse_input(wk.WM_XBUTTONDOWN, 1 << 16) == ("mouse:back", True)
    assert wk.mouse_input(wk.WM_XBUTTONUP, 2 << 16) == ("mouse:forward", False)
    assert wk.mouse_input(0x0201, 0) is None                # left button: never ours
    assert t.mouse(wk.WM_XBUTTONDOWN, 2 << 16) is True
    assert t.mouse(wk.WM_XBUTTONUP, 2 << 16) is True
    assert t.mouse(wk.WM_MBUTTONDOWN, 0) is False           # middle not bound
    assert [e.delta for e in posted] == [1]


def test_win_record_swallows_everything_but_modifiers():
    t, r, posted = tracker(Presets.F_KEYS.controls)
    seen = []
    r.capture, r.capture_keys = seen.append, True
    assert t.keyboard(ord("Q"), True) is True and t.keyboard(ord("Q"), False) is True
    assert t.keyboard(0x10, True) is False
    assert [(s.input, s.down) for s in seen] == [("key:q", True), ("key:q", False)]
    assert posted == []


# ================================================================ macOS

def test_mac_media_key_decoding():
    # NX_KEYTYPE_PLAY (16), key down (state 0xA), not a repeat
    data1 = (16 << 16) | (0xA << 8)
    assert keytap.system_key(8, data1) == ("playpause", True, False)
    assert keytap.system_key(8, (0 << 16) | (0xB << 8)) == ("volumeup", False, False)
    assert keytap.system_key(8, (1 << 16) | (0xA << 8) | 1) == ("volumedown", True, True)
    assert keytap.system_key(7, data1) is None              # not the media-key subtype
    assert keytap.system_key(8, (99 << 16) | (0xA << 8)) is None


def test_mac_keycodes_and_mods():
    assert keytap.KEY_NAMES[0x69] == "f13" and keytap.KEY_NAMES[0x31] == "space"
    assert keytap.mods_of(0x100000 | 0x020000) == {"cmd", "shift"}
    assert keytap.mods_of(0) == set()


def test_mac_mouse_buttons():
    assert keytap.mouse_name(3) == "mouse:back" and keytap.mouse_name(4) == "mouse:forward"
    assert keytap.mouse_name(2) == "mouse:middle" and keytap.mouse_name(0) is None


def test_mac_tracker_swallows_bound_keys_and_shortcuts():
    r, posted = router(Controls((Binding("open_wheel", Trigger("key:cmd+f13")),
                                 Binding("forward", Trigger("key:volumeup")))))
    t = keytap.TapTracker(r.wants, r.key)
    assert t.key("f13", {"cmd"}, True, False) is True
    assert t.key("f13", set(), False, False) is True        # up paired with its down
    assert t.key("f13", set(), True, False) is False        # without cmd: not ours
    assert t.key("volumeup", set(), True, False) is True
    assert t.key("volumeup", set(), True, True) is True     # repeat while held
    assert t.key("volumeup", set(), False, False) is True
    assert [e.action or e.delta for e in posted] == ["open_wheel", 1]


# ================================================================ scroll + modifier

def gtracker(controls):
    r, posted = router(controls)
    return wk.KeyTracker(r.wants, r.key, r.wants_gesture, r.gesture), r, posted


def wheel(delta):
    return (delta & 0xFFFF) << 16


def test_win_ctrl_scroll_is_a_control_plain_scroll_is_not():
    t, r, posted = gtracker(Presets.SCROLL.controls)
    assert t.mouse(wk.WM_MOUSEWHEEL, wheel(120)) is False          # no modifier: scrolls as usual
    t.keyboard(0xA2, True)
    assert t.mouse(wk.WM_MOUSEWHEEL, wheel(120)) is True           # ctrl + up: previous
    assert t.mouse(wk.WM_MOUSEWHEEL, wheel(-120)) is True          # ctrl + down: next
    t.keyboard(0xA2, False)
    assert [e.delta for e in posted] == [-1, 1]


def test_win_precision_scroll_adds_up_to_notches():
    t, r, posted = gtracker(Presets.SCROLL.controls)
    t.keyboard(0x11, True)
    for _ in range(5):
        assert t.mouse(wk.WM_MOUSEWHEEL, wheel(-40)) is True       # swallowed even between notches
    assert [e.delta for e in posted] == [1]                        # 200 of 120: one notch so far


def test_win_unbound_modifier_scroll_passes():
    t, r, posted = gtracker(Presets.SCROLL.controls)
    t.keyboard(0x12, True)                                         # alt + scroll: not in the preset
    assert t.mouse(wk.WM_MOUSEWHEEL, wheel(120)) is False
    assert wk.wheel_direction(wk.WM_MOUSEHWHEEL, wheel(-120)) == "left"


def test_win_record_captures_modifier_scroll():
    t, r, posted = gtracker(Controls())
    seen = []
    r.capture, r.capture_keys = seen.append, True
    t.keyboard(0x10, True)
    assert t.mouse(wk.WM_MOUSEWHEEL, wheel(120)) is True
    assert seen[0].input == "scroll:shift+up" and seen[0].counted


def test_scroll_labels():
    from orbit.core import controls as c
    assert c.input_label("scroll:ctrl+shift+down") == "Ctrl + Shift + scroll down"
    assert c.scroll_input("up", set()) is None
    assert c.input_label("touchpad:3-swipe-left") == "3-finger swipe left"
    assert c.input_label("touchpad:4-tap") == "4-finger tap"
    assert c.input_label("touchpad:pinch-in") == "Pinch in"


# ================================================================ macOS trackpad + scroll

def test_mac_pinch_and_rotate_fire_once_at_the_end():
    g = keytap.Gestures()
    assert g.magnify(-0.05, keytap.PHASE_BEGAN) is None
    assert g.magnify(-0.08, 0x4) is None
    assert g.magnify(-0.06, keytap.PHASE_ENDED) == "touchpad:pinch-in"
    assert g.magnify(0.3, keytap.PHASE_BEGAN | keytap.PHASE_ENDED) == "touchpad:pinch-out"
    assert g.magnify(0.05, keytap.PHASE_BEGAN) is None and g.magnify(0.04, keytap.PHASE_ENDED) is None   # too small
    assert g.rotate(12, keytap.PHASE_BEGAN) is None
    assert g.rotate(15, keytap.PHASE_ENDED) == "touchpad:rotate-left"
    assert g.rotate(-30, keytap.PHASE_BEGAN | keytap.PHASE_ENDED) == "touchpad:rotate-right"
    assert g.rotate(-40, keytap.PHASE_BEGAN | keytap.PHASE_CANCELLED) is None


def test_mac_swipes():
    assert keytap.swipe_input(1, 0) == "touchpad:swipe-left"
    assert keytap.swipe_input(-1, 0) == "touchpad:swipe-right"
    assert keytap.swipe_input(0, 1) == "touchpad:swipe-up"
    assert keytap.swipe_input(0, 0) is None


def test_mac_scroll_notches_need_a_modifier_and_add_up():
    s = keytap.ScrollNotches()
    assert s.feed(1.0, 0, set()) == (None, 0)
    assert s.feed(0.4, 0, {"cmd"}) == ("scroll:cmd+up", 0)
    assert s.feed(0.7, 0, {"cmd"}) == ("scroll:cmd+up", 1)
    assert s.feed(-2.0, 0, {"cmd"}) == ("scroll:cmd+down", 2)
    assert s.feed(0, 1.0, {"alt"}) == ("scroll:alt+left", 1)
