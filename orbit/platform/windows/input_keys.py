"""Windows: keys, media keys and mouse buttons as Orbit controls.

Low-level keyboard and mouse hooks (WH_KEYBOARD_LL / WH_MOUSE_LL) on their own thread.
A key or button that a control uses is swallowed (its usual action never happens) and
handed to the controls router; everything else passes straight through. Events Orbit
itself injects (SendInput: its keyboard shortcuts, scrolling) carry the INJECTED flag
and are never looked at, so Orbit can't trigger itself.

Low-level hooks see every key from every keyboard, so a key is a control whichever
keyboard it comes from. Windows drops a hook whose callback is slow, so the callback
only does a dictionary lookup and posts to the router.
"""
from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes

from orbit.platform.windows.keynames import WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP, KeyTracker

log = logging.getLogger("orbit.keys")

WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
LLKHF_INJECTED, LLMHF_INJECTED = 0x10, 0x01
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
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class WindowsKeyCapture:
    def __init__(self, router, accept_injected: bool = False):
        self.router = router
        self.accept_injected = accept_injected        # tools/key_capture_check.py only: SendInput is injected
        self.tracker = KeyTracker(router.wants, router.key)
        self._thread: threading.Thread | None = None
        self._tid = 0
        self._ready = threading.Event()
        self._hooks: list = []
        # keep the callbacks alive for as long as the hooks are
        self._kb = HOOKPROC(self._on_key)
        self._ms = HOOKPROC(self._on_mouse)

    def describe(self):
        return f"keyboard + mouse hooks ({len(self._hooks)} up)"

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
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        for h in self._hooks:
            user32.UnhookWindowsHookEx(h)
        self._hooks.clear()

    def _on_key(self, code, wparam, lparam):
        if code == 0:
            kb = KBDLLHOOKSTRUCT.from_address(lparam)
            if (self.accept_injected or not kb.flags & LLKHF_INJECTED) and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN, WM_KEYUP, WM_SYSKEYUP):
                try:
                    if self.tracker.keyboard(kb.vkCode, wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)):
                        return 1
                except Exception:
                    log.exception("key hook")
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _on_mouse(self, code, wparam, lparam):
        if code == 0:
            ms = MSLLHOOKSTRUCT.from_address(lparam)
            if self.accept_injected or not ms.flags & LLMHF_INJECTED:
                try:
                    if self.tracker.mouse(wparam, ms.mouseData):
                        return 1
                except Exception:
                    log.exception("mouse hook")
        return user32.CallNextHookEx(None, code, wparam, lparam)
