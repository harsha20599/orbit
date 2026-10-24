"""Windows: keys, media keys and mouse buttons as Orbit controls.

Low-level keyboard and mouse hooks (WH_KEYBOARD_LL / WH_MOUSE_LL) on their own thread.
A key or button that a control uses is swallowed (its usual action never happens) and
handed to the controls router; everything else passes straight through. Events Orbit
itself sends (SendInput: its keyboard shortcuts, scrolling) carry ORBIT_TAG in
dwExtraInfo and are never looked at, so Orbit can't trigger itself. Other injected
events are looked at: Windows injects the keys of HID media controls (a Bluetooth
keyboard's volume knob), and those are controls like any key.

Low-level hooks see every key from every keyboard, so a key is a control whichever
keyboard it comes from. Windows drops a hook whose callback is slow, so the callback
only does a dictionary lookup and posts to the router.

Keeping it working (what AutoHotkey and PowerToys learned the hard way):
  - Windows removes a slow hook without telling anyone. A watchdog compares the last
    input Windows saw (GetLastInputInfo) with the last one the hooks saw, and puts the
    hooks back when they have gone quiet while input kept coming. The hook thread runs
    at time-critical priority so it is rarely slow in the first place.
  - The lock screen, UAC prompts and sleep eat key-ups. Every SWEEP_MS the modifiers
    Orbit thinks are held are checked against Windows' own key state; on lock / unlock
    and resume everything is let go and the hooks are put back.
  - Swallowing a key while Win or Alt is held would make Windows treat the Win / Alt
    release as a press on its own (Start menu, menu bar): a tagged dummy key goes out.
"""
from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes

from orbit.platform.windows.keynames import (MASK_VK, ORBIT_TAG, WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP,
                                             KeyTracker, altgr_fake_ctrl, own_event)

log = logging.getLogger("orbit.keys")

WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
WM_QUIT = 0x0012
WM_TIMER, WM_WTSSESSION_CHANGE, WM_POWERBROADCAST = 0x0113, 0x02B1, 0x0218
WM_APP_MASK = 0x8001
WTS_SESSION_LOCK, WTS_SESSION_UNLOCK = 0x7, 0x8
PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC = 0x7, 0x12
SWEEP_MS = 250
QUIET_MS = 2000             # hooks saw nothing this long while Windows got input: they're gone

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
HWND_MESSAGE = wintypes.HWND(-3)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                   wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
user32.SetTimer.restype = ctypes.c_size_t
kernel32.GetTickCount.restype = wintypes.DWORD
kernel32.GetCurrentThread.restype = wintypes.HANDLE
kernel32.SetThreadPriority.argtypes = [wintypes.HANDLE, ctypes.c_int]


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class _KI(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KI), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def _is_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def _send_mask():
    keys = (_INPUT * 2)()
    for i, flags in enumerate((0, 2)):
        keys[i].type = 1
        keys[i].ki = _KI(MASK_VK, 0, flags, 0, ORBIT_TAG)
    user32.SendInput(2, keys, ctypes.sizeof(_INPUT))


def _last_input_tick() -> int:
    li = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
    user32.GetLastInputInfo(ctypes.byref(li))
    return li.dwTime


def hooks_quiet(last_input: int, seen: int) -> bool:
    """Windows got input QUIET_MS after the hooks last saw any (tick counts wrap)."""
    gap = (last_input - seen) & 0xFFFFFFFF
    return QUIET_MS < gap < 0x80000000


class WindowsKeyCapture:
    def __init__(self, router, accept_injected: bool = False):
        self.router = router
        self.accept_injected = accept_injected        # tools/key_capture_check.py only: also take Orbit's own events
        self.tracker = KeyTracker(router.wants, router.key, router.wants_gesture, router.gesture,
                                  is_down=_is_down, mask=self._post_mask)
        self._seen = 0                 # tick when a hook last saw any input
        self._reinstalled = 0
        self.reinstalls = 0
        self.touchpad = None
        self._thread: threading.Thread | None = None
        self._tid = 0
        self._ready = threading.Event()
        self._hooks: list = []
        # keep the callbacks alive for as long as the hooks are
        self._kb = HOOKPROC(self._on_key)
        self._ms = HOOKPROC(self._on_mouse)

    def describe(self):
        pad = "touchpad gestures on" if self.touchpad is not None and self.touchpad.registered else "no touchpad"
        return f"keyboard + mouse hooks ({len(self._hooks)} up), {pad}"

    def start(self):
        self._thread = threading.Thread(target=self._run, name="key-hooks", daemon=True)
        self._thread.start()
        self._ready.wait(2.0)

    def stop(self):
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)

    def _install(self):
        for h in self._hooks:
            user32.UnhookWindowsHookEx(h)
        self._hooks.clear()
        mod = kernel32.GetModuleHandleW(None)
        for kind, proc in ((WH_KEYBOARD_LL, self._kb), (WH_MOUSE_LL, self._ms)):
            h = user32.SetWindowsHookExW(kind, proc, mod, 0)
            if h:
                self._hooks.append(h)
            else:
                log.error("hook %d failed (err %d)", kind, ctypes.get_last_error())
        self._seen = kernel32.GetTickCount()

    def _reinstall(self, why: str):
        self.reinstalls += 1
        self._reinstalled = kernel32.GetTickCount()
        self.release_all()
        self._install()
        log.info("key capture: hooks put back (%s)", why)

    def release_all(self):
        self.tracker.release_all()
        self.router.hub.release_all()

    def _post_mask(self):
        user32.PostThreadMessageW(self._tid, WM_APP_MASK, 0, 0)

    def _run(self):
        self._tid = kernel32.GetCurrentThreadId()
        kernel32.SetThreadPriority(kernel32.GetCurrentThread(), 15)       # THREAD_PRIORITY_TIME_CRITICAL
        self._install()
        self._touchpad_window()
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_APP_MASK and not msg.hWnd:
                _send_mask()
                continue
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        for h in self._hooks:
            user32.UnhookWindowsHookEx(h)
        self._hooks.clear()

    def _check(self):
        """Every SWEEP_MS on the hook thread: drop stale modifiers; put the hooks back if
        Windows dropped them."""
        try:
            self.tracker.sweep()
            now = kernel32.GetTickCount()
            if (self._hooks and hooks_quiet(_last_input_tick(), self._seen)
                    and (now - self._reinstalled) & 0xFFFFFFFF > 10_000):
                self._reinstall("Windows had dropped them")
        except Exception:
            log.exception("key capture check")

    def _on_session(self, msg, wp):
        if msg == WM_WTSSESSION_CHANGE and wp in (WTS_SESSION_LOCK, WTS_SESSION_UNLOCK):
            self.release_all()
            if wp == WTS_SESSION_UNLOCK:
                self._reinstall("unlocked")
        elif msg == WM_POWERBROADCAST and wp in (PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC):
            self._reinstall("resumed")

    def _touchpad_window(self):
        """A message-only window on this thread, for the touchpad's Raw Input."""
        try:
            from orbit.platform.windows.touchpad import WM_INPUT, TouchpadReader
            self.touchpad = TouchpadReader(lambda g: self.router.gesture(g))

            def proc(hwnd, msg, wp, lp):
                if msg == WM_TIMER:
                    self._check()
                    return 0
                if msg in (WM_WTSSESSION_CHANGE, WM_POWERBROADCAST):
                    self._on_session(msg, wp)
                if msg == WM_INPUT:
                    try:
                        self.touchpad.on_input(lp)
                    except Exception:
                        log.exception("touchpad input")
                return user32.DefWindowProcW(hwnd, msg, wp, lp)
            self._wndproc = WNDPROC(proc)
            wc = WNDCLASSW()
            wc.lpfnWndProc = self._wndproc
            wc.lpszClassName = "OrbitInputSink"
            wc.hInstance = kernel32.GetModuleHandleW(None)
            user32.RegisterClassW(ctypes.byref(wc))
            hwnd = user32.CreateWindowExW(0, "OrbitInputSink", "Orbit", 0, 0, 0, 0, 0, HWND_MESSAGE, None,
                                          wc.hInstance, None)
            if hwnd:
                self.touchpad.register(hwnd)
                user32.SetTimer(hwnd, 1, SWEEP_MS, None)
                try:
                    ctypes.WinDLL("wtsapi32").WTSRegisterSessionNotification(hwnd, 0)   # this session only
                except Exception:
                    log.exception("session notifications")
        except Exception:
            log.exception("touchpad gestures unavailable")
            self.touchpad = None

    def _on_key(self, code, wparam, lparam):
        if code == 0:
            kb = KBDLLHOOKSTRUCT.from_address(lparam)
            self._seen = kb.time
            if altgr_fake_ctrl(kb.vkCode, kb.scanCode):
                return user32.CallNextHookEx(None, code, wparam, lparam)      # AltGr's fake Ctrl: not a Ctrl press
            if (self.accept_injected or not own_event(kb.dwExtraInfo)) and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN, WM_KEYUP, WM_SYSKEYUP):
                try:
                    if self.tracker.keyboard(kb.vkCode, wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)):
                        return 1
                except Exception:
                    log.exception("key hook")
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _on_mouse(self, code, wparam, lparam):
        if code == 0:
            ms = MSLLHOOKSTRUCT.from_address(lparam)
            self._seen = ms.time
            if self.accept_injected or not own_event(ms.dwExtraInfo):
                try:
                    if self.tracker.mouse(wparam, ms.mouseData):
                        return 1
                except Exception:
                    log.exception("mouse hook")
        return user32.CallNextHookEx(None, code, wparam, lparam)
