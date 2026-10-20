"""Trackpad gestures from finger positions (orbit/core/touch.py)."""
from orbit.core.touch import TouchGestures


def run(frames):
    got = []
    g = TouchGestures(got.append)
    t = 0.0
    for f in frames:
        g.frame(f, t)
        t += 0.016
    return got


def fingers(n, x, y):
    return {i: (x + 0.05 * i, y) for i in range(n)}


def swipe(n, dx, dy, steps=12):
    return [fingers(n, 0.4 + dx * k / steps, 0.5 + dy * k / steps) for k in range(steps + 1)] + [{}]


def test_three_finger_swipes():
    assert run(swipe(3, 0.3, 0)) == ["touchpad:3-swipe-right"]
    assert run(swipe(3, -0.3, 0.05)) == ["touchpad:3-swipe-left"]
    assert run(swipe(3, 0, -0.25)) == ["touchpad:3-swipe-up"]
    assert run(swipe(3, 0.02, 0.25)) == ["touchpad:3-swipe-down"]


def test_four_finger_swipe_and_tap():
    assert run(swipe(4, 0.3, 0)) == ["touchpad:4-swipe-right"]
    assert run([fingers(4, 0.4, 0.5)] * 5 + [{}]) == ["touchpad:4-tap"]


def test_three_finger_tap():
    assert run([fingers(3, 0.4, 0.5)] * 6 + [{}]) == ["touchpad:3-tap"]


def test_fingers_landing_one_by_one_still_count():
    frames = [fingers(1, 0.4, 0.5), fingers(2, 0.4, 0.5)] + swipe(3, 0.3, 0)
    assert run(frames) == ["touchpad:3-swipe-right"]


def test_two_fingers_scroll_and_one_finger_point_are_never_ours():
    assert run(swipe(2, 0.4, 0)) == []
    assert run(swipe(1, 0.4, 0)) == []


def test_long_still_press_is_not_a_tap():
    assert run([fingers(3, 0.4, 0.5)] * 40 + [{}]) == []           # 0.64 s resting


def test_small_wobble_is_neither():
    assert run(swipe(3, 0.07, 0)) == []


def test_lifting_fingers_mid_swipe_keeps_the_gesture():
    frames = swipe(3, 0.3, 0)[:-1] + [fingers(2, 0.7, 0.5), fingers(1, 0.7, 0.5), {}]
    assert run(frames) == ["touchpad:3-swipe-right"]
