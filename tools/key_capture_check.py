"""Windows: check the key / mouse hooks for real (not a unit test; needs a desktop).

Installs a recording hook first (low-level hooks run newest first, so it sees only what
gets past Orbit's hook, and it swallows everything so no app receives the test keys),
then Orbit's capture with `b`, Ctrl+Space and the mouse forward button bound, then
sends a, b, c, Ctrl+Space, Space and a forward click.

Expected: past Orbit = a, c, space (+ the ctrl presses themselves); Orbit's router got
exactly b, Ctrl+Space and the forward button; nothing else.

    python tools/key_capture_check.py
"""
import ctypes
import sys
import threading
import time
from ctypes import wintypes

sys.path.insert(0, ".")
from orbit.core.controls import Binding, Controls, Router, Trigger  # noqa: E402
from orbit.platform.windows import input_keys as ik  # noqa: E402
from orbit.platform.windows.keynames import VK_NAMES, mouse_input  # noqa: E402

user32, kernel32 = ik.user32, ik.kernel32
passed: list[str] = []


def recorder():
    def kb(code, w, l):
        if code == 0:
            k = ik.KBDLLHOOKSTRUCT.from_address(l)
            if w in (0x100, 0x104):
                passed.append(VK_NAMES.get(k.vkCode, hex(k.vkCode)))
            return 1                                   # swallow: no app ever sees the test
        return user32.CallNextHookEx(None, code, w, l)

    def ms(code, w, l):
        if code == 0:
            m = ik.MSLLHOOKSTRUCT.from_address(l)
            mi = mouse_input(w, m.mouseData)
            if mi:
                if mi[1]:
                    passed.append(mi[0])
                return 1
        return user32.CallNextHookEx(None, code, w, l)
    procs = (ik.HOOKPROC(kb), ik.HOOKPROC(ms))
    mod = kernel32.GetModuleHandleW(None)
    hooks = [user32.SetWindowsHookExW(13, procs[0], mod, 0), user32.SetWindowsHookExW(14, procs[1], mod, 0)]
    rec_ready.set()
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        pass
    for h in hooks:
        user32.UnhookWindowsHookEx(h)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def send(*inputs):
    arr = (INPUT * len(inputs))(*inputs)
    n = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
    if n != len(inputs):
        print("SendInput sent", n, "of", len(inputs), "err", ctypes.get_last_error())
    time.sleep(0.03)


def key(vk, up=False):
    i = INPUT(type=1)
    i.ki = KEYBDINPUT(vk, 0, 0x2 if up else 0, 0, 0)
    return i


def xbutton(which, down):
    i = INPUT(type=0)
    i.mi = MOUSEINPUT(0, 0, which, 0x0080 if down else 0x0100, 0, 0)
    return i


rec_ready = threading.Event()
rec = threading.Thread(target=recorder, daemon=True)
rec.start()
rec_ready.wait(2)

posted = []
r = Router(posted.append, lambda m: None)
r.set_controls(Controls((Binding("forward", Trigger("key:b")), Binding("open_wheel", Trigger("key:ctrl+space")),
                         Binding("back", Trigger("mouse:forward")))))
cap = ik.WindowsKeyCapture(r, accept_injected=True)
cap.start()
time.sleep(0.2)

t0 = time.perf_counter()
A, B, C, SPACE, CTRL = 0x41, 0x42, 0x43, 0x20, 0xA2
for vk in (A, B, C):
    send(key(vk), key(vk, True))
send(key(CTRL), key(SPACE), key(SPACE, True), key(CTRL, True))
send(key(SPACE), key(SPACE, True))
send(xbutton(2, True), xbutton(2, False))
time.sleep(0.3)
ms = (time.perf_counter() - t0) * 1000

cap.stop()
user32.PostThreadMessageW(rec.native_id, 0x12, 0, 0)
got = [(e.kind.value, e.delta, e.action) for e in posted]
want_past = ["a", "c", hex(CTRL), "space"]
past = [p if p != "ctrl" else hex(CTRL) for p in passed]
ok = past == want_past and got == [("rotate", 1, None), ("action", 0, "open_wheel"), ("rotate", -1, None)]
print(f"past Orbit: {past}\nrouter:     {got}\n{ms:.0f} ms")
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
