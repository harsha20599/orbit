"""Windows Precision Touchpad fingers via Raw Input, for trackpad gestures.

Registers for the touchpad's HID reports (usage page 0x0D Digitizer, usage 0x05 Touch
Pad) with RIDEV_INPUTSINK, so they arrive whichever window is in front. Each report is
decoded with the device's own HID description (hid.dll): per finger collection the tip
switch, contact id and X / Y; on the top level the contact count. Precision touchpads
send either all fingers in one report ("parallel") or one report per finger with the
count only in the first ("hybrid"); both are handled.

Raw Input only listens: Windows still runs its own three / four-finger gestures. To use
those gestures for Orbit, set them to "Nothing" in Settings → Bluetooth & devices →
Touchpad. The decoding helpers are separate from the ctypes calls where possible.
"""
from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes

from orbit.core.touch import TouchGestures

log = logging.getLogger("orbit.touchpad")

user32 = ctypes.WinDLL("user32", use_last_error=True)
hid = ctypes.WinDLL("hid")

WM_INPUT = 0x00FF
RID_INPUT = 0x10000003
RIDI_PREPARSEDDATA = 0x20000005
RIM_TYPEHID = 2
RIDEV_INPUTSINK = 0x00000100
HIDP_STATUS_SUCCESS = 0x00110000
HidP_Input = 0
PAGE_GENERIC, PAGE_DIGITIZER = 0x01, 0x0D
U_X, U_Y = 0x30, 0x31
U_TIP, U_CONTACT_ID, U_CONTACT_COUNT, U_FINGER = 0x42, 0x51, 0x54, 0x22


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [("Usage", wintypes.USHORT), ("UsagePage", wintypes.USHORT),
                ("InputReportByteLength", wintypes.USHORT), ("OutputReportByteLength", wintypes.USHORT),
                ("FeatureReportByteLength", wintypes.USHORT), ("Reserved", wintypes.USHORT * 17),
                ("NumberLinkCollectionNodes", wintypes.USHORT), ("NumberInputButtonCaps", wintypes.USHORT),
                ("NumberInputValueCaps", wintypes.USHORT), ("NumberInputDataIndices", wintypes.USHORT),
                ("NumberOutputButtonCaps", wintypes.USHORT), ("NumberOutputValueCaps", wintypes.USHORT),
                ("NumberOutputDataIndices", wintypes.USHORT), ("NumberFeatureButtonCaps", wintypes.USHORT),
                ("NumberFeatureValueCaps", wintypes.USHORT), ("NumberFeatureDataIndices", wintypes.USHORT)]


class HIDP_VALUE_CAPS(ctypes.Structure):
    _fields_ = [("UsagePage", wintypes.USHORT), ("ReportID", ctypes.c_ubyte), ("IsAlias", ctypes.c_ubyte),
                ("BitField", wintypes.USHORT), ("LinkCollection", wintypes.USHORT),
                ("LinkUsage", wintypes.USHORT), ("LinkUsagePage", wintypes.USHORT),
                ("IsRange", ctypes.c_ubyte), ("IsStringRange", ctypes.c_ubyte),
                ("IsDesignatorRange", ctypes.c_ubyte), ("IsAbsolute", ctypes.c_ubyte),
                ("HasNull", ctypes.c_ubyte), ("Reserved", ctypes.c_ubyte),
                ("BitSize", wintypes.USHORT), ("ReportCount", wintypes.USHORT),
                ("Reserved2", wintypes.USHORT * 5), ("UnitsExp", wintypes.ULONG), ("Units", wintypes.ULONG),
                ("LogicalMin", wintypes.LONG), ("LogicalMax", wintypes.LONG),
                ("PhysicalMin", wintypes.LONG), ("PhysicalMax", wintypes.LONG),
                ("Usage", wintypes.USHORT), ("Reserved1", wintypes.USHORT),
                ("StringIndex", wintypes.USHORT), ("Reserved3", wintypes.USHORT),
                ("DesignatorIndex", wintypes.USHORT), ("Reserved4", wintypes.USHORT),
                ("DataIndex", wintypes.USHORT), ("Reserved5", wintypes.USHORT)]


assert ctypes.sizeof(HIDP_VALUE_CAPS) == 72, ctypes.sizeof(HIDP_VALUE_CAPS)

hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
hid.HidP_GetCaps.restype = ctypes.c_long
hid.HidP_GetValueCaps.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(wintypes.USHORT), ctypes.c_void_p]
hid.HidP_GetValueCaps.restype = ctypes.c_long
hid.HidP_GetUsageValue.argtypes = [ctypes.c_int, wintypes.USHORT, wintypes.USHORT, wintypes.USHORT,
                                   ctypes.POINTER(wintypes.ULONG), ctypes.c_void_p, ctypes.c_void_p, wintypes.ULONG]
hid.HidP_GetUsageValue.restype = ctypes.c_long
hid.HidP_GetUsages.argtypes = [ctypes.c_int, wintypes.USHORT, wintypes.USHORT, ctypes.c_void_p,
                               ctypes.POINTER(wintypes.ULONG), ctypes.c_void_p, ctypes.c_void_p, wintypes.ULONG]
hid.HidP_GetUsages.restype = ctypes.c_long
user32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, ctypes.c_void_p, ctypes.POINTER(wintypes.UINT),
                                   wintypes.UINT]
user32.GetRawInputData.restype = wintypes.UINT
user32.GetRawInputDeviceInfoW.argtypes = [wintypes.HANDLE, wintypes.UINT, ctypes.c_void_p, ctypes.POINTER(wintypes.UINT)]
user32.GetRawInputDeviceInfoW.restype = wintypes.UINT
user32.RegisterRawInputDevices.argtypes = [ctypes.c_void_p, wintypes.UINT, wintypes.UINT]


class _Device:
    """What one touchpad's reports look like."""

    def __init__(self, preparsed: ctypes.Array):
        self.pp = preparsed
        caps = HIDP_CAPS()
        if hid.HidP_GetCaps(self.pp, ctypes.byref(caps)) != HIDP_STATUS_SUCCESS:
            raise OSError("HidP_GetCaps")
        n = wintypes.USHORT(caps.NumberInputValueCaps)
        vcaps = (HIDP_VALUE_CAPS * max(1, n.value))()
        if hid.HidP_GetValueCaps(HidP_Input, vcaps, ctypes.byref(n), self.pp) != HIDP_STATUS_SUCCESS:
            raise OSError("HidP_GetValueCaps")
        self.fingers: list[int] = []                      # link collections holding a finger
        self.max: dict[tuple[int, int], int] = {}         # (link, usage) -> logical max
        self.has_count = False
        for v in vcaps[:n.value]:
            if v.IsRange:
                continue
            if v.UsagePage == PAGE_GENERIC and v.Usage in (U_X, U_Y):
                self.max[(v.LinkCollection, v.Usage)] = max(1, v.LogicalMax)
                if v.LinkCollection not in self.fingers:
                    self.fingers.append(v.LinkCollection)
            if v.UsagePage == PAGE_DIGITIZER and v.Usage == U_CONTACT_COUNT:
                self.has_count = True
        self.fingers.sort()
        self.contacts: dict[int, tuple[float, float]] = {}
        self.remaining = 0

    def _value(self, link: int, page: int, usage: int, report, size) -> int | None:
        v = wintypes.ULONG()
        r = hid.HidP_GetUsageValue(HidP_Input, page, link, usage, ctypes.byref(v), self.pp, report, size)
        return v.value if r == HIDP_STATUS_SUCCESS else None

    def _tip(self, link: int, report, size) -> bool:
        usages = (wintypes.USHORT * 16)()
        n = wintypes.ULONG(16)
        r = hid.HidP_GetUsages(HidP_Input, PAGE_DIGITIZER, link, usages, ctypes.byref(n), self.pp, report, size)
        return r == HIDP_STATUS_SUCCESS and U_TIP in usages[:n.value]

    def report(self, report, size) -> dict[int, tuple[float, float]]:
        count = self._value(0, PAGE_DIGITIZER, U_CONTACT_COUNT, report, size) if self.has_count else None
        if count:                                         # first (or only) report of a frame
            valid, self.remaining = count, max(0, count - len(self.fingers))
        else:                                             # hybrid: the frame's later reports
            valid = min(len(self.fingers), self.remaining) if self.remaining else len(self.fingers)
            self.remaining = max(0, self.remaining - valid)
        for link in self.fingers[:valid]:
            cid = self._value(link, PAGE_DIGITIZER, U_CONTACT_ID, report, size)
            if cid is None:
                continue
            if not self._tip(link, report, size):
                self.contacts.pop(cid, None)
                continue
            x = self._value(link, PAGE_GENERIC, U_X, report, size)
            y = self._value(link, PAGE_GENERIC, U_Y, report, size)
            if x is None or y is None:
                continue
            self.contacts[cid] = (x / self.max.get((link, U_X), 1), y / self.max.get((link, U_Y), 1))
        return self.contacts


class TouchpadReader:
    """Raw Input for touchpads on the hook thread's hidden window; gestures to `emit`."""

    def __init__(self, emit):
        self.gestures = TouchGestures(emit)
        self.devices: dict[int, _Device | None] = {}
        self.registered = False

    def register(self, hwnd) -> bool:
        rid = RAWINPUTDEVICE(PAGE_DIGITIZER, 0x05, RIDEV_INPUTSINK, hwnd)
        self.registered = bool(user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid)))
        if not self.registered:
            log.info("no touchpad input (err %d)", ctypes.get_last_error())
        return self.registered

    def _device(self, handle) -> _Device | None:
        key = int(handle or 0)
        if key not in self.devices:
            size = wintypes.UINT(0)
            user32.GetRawInputDeviceInfoW(handle, RIDI_PREPARSEDDATA, None, ctypes.byref(size))
            buf = (ctypes.c_char * max(1, size.value))()
            try:
                if user32.GetRawInputDeviceInfoW(handle, RIDI_PREPARSEDDATA, buf, ctypes.byref(size)) <= 0:
                    raise OSError("no preparsed data")
                self.devices[key] = _Device(buf)
                log.info("touchpad: %d finger slots", len(self.devices[key].fingers))
            except Exception as e:
                log.info("touchpad device skipped: %s", e)
                self.devices[key] = None
        return self.devices[key]

    def on_input(self, lparam):
        size = wintypes.UINT(0)
        hdr = ctypes.sizeof(RAWINPUTHEADER)
        user32.GetRawInputData(lparam, RID_INPUT, None, ctypes.byref(size), hdr)
        buf = (ctypes.c_char * size.value)()
        if user32.GetRawInputData(lparam, RID_INPUT, buf, ctypes.byref(size), hdr) != size.value:
            return
        h = RAWINPUTHEADER.from_buffer(buf)
        if h.dwType != RIM_TYPEHID:
            return
        dev = self._device(h.hDevice)
        if dev is None:
            return
        size_hid, count = ctypes.c_uint32.from_buffer(buf, hdr).value, ctypes.c_uint32.from_buffer(buf, hdr + 4).value
        base = hdr + 8
        for i in range(count):
            off = base + i * size_hid
            report = (ctypes.c_char * size_hid).from_buffer(buf, off)
            contacts = dev.report(report, size_hid)
            self.gestures.frame(dict(contacts), time.monotonic())
