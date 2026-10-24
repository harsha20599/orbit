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
"""
from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes

from orbit.platform.windows.keynames import WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP, KeyTracker, own_event

log = logging.getLogger("orbit.keys")

WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
WM_QUIT = 0x0012

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


class WindowsKeyCapture:
    def __init__(self, router, accept_injected: bool = False):
        self.router = router
        self.accept_injected = accept_injected        # tools/key_capture_check.py only: also take Orbit's own events
        self.tracker = KeyTracker(router.wants, router.key, router.wants_gesture, router.gesture)
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

    def _run(self):
        self._tid = kernel32.GetCurrentThreadId()
        mod = kernel32.GetModuleHandleW(None)
        for kind, proc in ((WH_KEYBOARD_LL, self._kb), (WH_MOUSE_LL, self._ms)):
            h = user32.SetWindowsHookExW(kind, proc, mod, 0)
            if h:
                self._hooks.append(h)
            else:
                log.error("hook %d failed (err %d)", kind, ctypes.get_last_error())
        self._touchpad_window()
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        for h in self._hooks:
            user32.UnhookWindowsHookEx(h)
        self._hooks.clear()

    def _touchpad_window(self):
        """A message-only window on this thread, for the touchpad's Raw Input."""
        try:
            from orbit.platform.windows.touchpad import WM_INPUT, TouchpadReader
            self.touchpad = TouchpadReader(lambda g: self.router.gesture(g))

            def proc(hwnd, msg, wp, lp):
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
        except Exception:
            log.exception("touchpad gestures unavailable")
            self.touchpad = None

    def _on_key(self, code, wparam, lparam):
        if code == 0:
            kb = KBDLLHOOKSTRUCT.from_address(lparam)
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
            if self.accept_injected or not own_event(ms.dwExtraInfo):
                try:
                    if self.tracker.mouse(wparam, ms.mouseData):
                        return 1
                except Exception:
                    log.exception("mouse hook")
        return user32.CallNextHookEx(None, code, wparam, lparam)
