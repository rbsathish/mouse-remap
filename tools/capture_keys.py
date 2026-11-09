"""Diagnostic: shows what the mouse's extra buttons (Search / Screenshot / Desktop) send to Windows.

Logs ONLY: Windows-key events and the keys pressed within 0.25 s after one, media / browser / launcher keys,
F13-F24, PrintScreen, mouse side/middle buttons and wheel tilt, and raw HID (consumer-control) reports.
Ordinary typing is not logged. Nothing is blocked or changed; it only watches.

usage: python tools\capture_keys.py [seconds] [logfile]   (default log: %TEMP%\mouse_remap_capture.txt)
"""
import ctypes
import os
import sys
import tempfile
import time
from ctypes import wintypes

DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else os.path.join(tempfile.gettempdir(), "mouse_remap_capture.txt")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
WM_INPUT = 0x00FF
RIM_TYPEKEYBOARD, RIM_TYPEHID = 1, 2
RID_INPUT, RIDI_DEVICENAME, RIDEV_INPUTSINK = 0x10000003, 0x20000007, 0x00000100
PM_REMOVE = 1


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
user32.RegisterRawInputDevices.restype = wintypes.BOOL
user32.GetRawInputData.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p,
                                   ctypes.POINTER(wintypes.UINT), wintypes.UINT]
user32.GetRawInputData.restype = wintypes.UINT
user32.GetRawInputDeviceInfoW.argtypes = [wintypes.HANDLE, wintypes.UINT, ctypes.c_void_p, ctypes.POINTER(wintypes.UINT)]
user32.GetRawInputDeviceInfoW.restype = wintypes.UINT
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

T0 = time.perf_counter()
LOG = open(LOG_PATH, "w", encoding="utf-8")
last_win = -10.0
device_names = {}


def log(line):
    LOG.write(f"{time.perf_counter() - T0:10.4f}  {line}\n")
    LOG.flush()


def interesting_key(vk):
    """Keys worth logging: Win keys, anything within 0.25 s of one, media/browser/launch keys, F13-F24, PrintScreen."""
    global last_win
    now = time.time()
    if vk in (0x5B, 0x5C):
        last_win = now
        return True
    return (now - last_win < 0.25 or 0xA6 <= vk <= 0xB7 or 0x7C <= vk <= 0x87 or vk in (0x2C, 0x5F, 0x5D, 0xE7))


def device_label(handle):
    if handle not in device_names:
        size = wintypes.UINT(0)
        user32.GetRawInputDeviceInfoW(handle, RIDI_DEVICENAME, None, ctypes.byref(size))
        buf = ctypes.create_unicode_buffer(max(size.value, 1))
        user32.GetRawInputDeviceInfoW(handle, RIDI_DEVICENAME, buf, ctypes.byref(size))
        name = buf.value
        # keep the identifying part: VID/PID/interface, drop the long GUID tail
        device_names[handle] = name.split("#{")[0].replace("\\\\?\\", "")
    return device_names[handle]


@HOOKPROC
def keyboard_proc(n_code, w_param, l_param):
    try:
        if n_code == 0:
            k = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if interesting_key(k.vkCode):
                kind = "up  " if w_param in (0x0101, 0x0105) else "down"
                log(f"HOOK key {kind} vk=0x{k.vkCode:02X} scan=0x{k.scanCode:02X} flags=0x{k.flags:02X}"
                    f"{' INJECTED' if k.flags & 0x10 else ''}{' EXT' if k.flags & 1 else ''}")
    except Exception as err:
        log(f"keyboard hook error: {err}")
    return user32.CallNextHookEx(None, n_code, w_param, l_param)


MOUSE_NAMES = {0x020B: "X down", 0x020C: "X up  ", 0x0207: "middle down", 0x0208: "middle up  ", 0x020E: "wheel TILT"}


@HOOKPROC
def mouse_proc(n_code, w_param, l_param):
    try:
        if n_code == 0 and w_param in MOUSE_NAMES:
            m = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            extra = f" which={(m.mouseData >> 16) & 0xFFFF}" if w_param in (0x020B, 0x020C) else \
                f" delta={ctypes.c_short((m.mouseData >> 16) & 0xFFFF).value}" if w_param == 0x020E else ""
            log(f"HOOK mouse {MOUSE_NAMES[w_param]}{extra}")
    except Exception as err:
        log(f"mouse hook error: {err}")
    return user32.CallNextHookEx(None, n_code, w_param, l_param)


@WNDPROC
def wnd_proc(hwnd, msg, w_param, l_param):
    if msg == WM_INPUT:
        try:
            size = wintypes.UINT(0)
            hdr = ctypes.sizeof(RAWINPUTHEADER)
            user32.GetRawInputData(l_param, RID_INPUT, None, ctypes.byref(size), hdr)
            buf = ctypes.create_string_buffer(size.value)
            if user32.GetRawInputData(l_param, RID_INPUT, buf, ctypes.byref(size), hdr) == size.value:
                header = RAWINPUTHEADER.from_buffer_copy(buf)
                data = buf.raw[hdr:size.value]
                if header.dwType == RIM_TYPEKEYBOARD:
                    make, flags, _res, vkey = int.from_bytes(data[0:2], "little"), int.from_bytes(data[2:4], "little"), 0, \
                        int.from_bytes(data[6:8], "little")
                    if interesting_key(vkey):
                        log(f"RAW  keyboard {'up  ' if flags & 1 else 'down'} vk=0x{vkey:02X} make=0x{make:02X} "
                            f"from {device_label(header.hDevice)}")
                elif header.dwType == RIM_TYPEHID:
                    count = int.from_bytes(data[4:8], "little")
                    size_hid = int.from_bytes(data[0:4], "little")
                    for i in range(count):
                        report = data[8 + i * size_hid: 8 + (i + 1) * size_hid]
                        log(f"RAW  HID report {report.hex(' ')} from {device_label(header.hDevice)}")
        except Exception as err:
            log(f"raw input error: {err}")
    return user32.DefWindowProcW(hwnd, msg, w_param, l_param)


class RAWINPUTDEVICELIST(ctypes.Structure):
    _fields_ = [("hDevice", wintypes.HANDLE), ("dwType", wintypes.DWORD)]


class RID_DEVICE_INFO(ctypes.Structure):
    # cbSize, dwType, then a union whose largest member (keyboard) is six DWORDs; read it as raw DWORDs.
    _fields_ = [("cbSize", wintypes.DWORD), ("dwType", wintypes.DWORD), ("data", wintypes.DWORD * 6)]


user32.GetRawInputDeviceList.argtypes = [ctypes.POINTER(RAWINPUTDEVICELIST), ctypes.POINTER(wintypes.UINT), wintypes.UINT]
user32.GetRawInputDeviceList.restype = wintypes.UINT


def list_devices():
    """What input devices Windows sees: type, VID/PID, and for HID the usage page; for mice the button count."""
    count = wintypes.UINT(0)
    user32.GetRawInputDeviceList(None, ctypes.byref(count), ctypes.sizeof(RAWINPUTDEVICELIST))
    devs = (RAWINPUTDEVICELIST * count.value)()
    user32.GetRawInputDeviceList(devs, ctypes.byref(count), ctypes.sizeof(RAWINPUTDEVICELIST))
    kinds = {0: "MOUSE", 1: "KEYBOARD", 2: "HID"}
    for d in devs:
        info = RID_DEVICE_INFO(cbSize=ctypes.sizeof(RID_DEVICE_INFO))
        size = wintypes.UINT(ctypes.sizeof(info))
        user32.GetRawInputDeviceInfoW(d.hDevice, 0x2000000B, ctypes.byref(info), ctypes.byref(size))
        w = list(info.data)
        if d.dwType == 0:
            detail = f"buttons={w[1]} sample_rate={w[2]} h_wheel={bool(w[3])}"
        elif d.dwType == 1:
            detail = f"function_keys={w[3]} total_keys={w[5]}"
        else:
            detail = f"vid=0x{w[0]:04X} pid=0x{w[1]:04X} usage_page=0x{w[3] & 0xFFFF:04X} usage=0x{w[3] >> 16:04X}"
        log(f"DEVICE {kinds.get(d.dwType, d.dwType):8} {detail}  {device_label(d.hDevice)}")


def main():
    hinst = kernel32.GetModuleHandleW(None)
    cls = WNDCLASSW(lpfnWndProc=wnd_proc, hInstance=hinst, lpszClassName="MouseRemapCapture")
    user32.RegisterClassW(ctypes.byref(cls))
    hwnd = user32.CreateWindowExW(0x80, "MouseRemapCapture", "capture", 0x80000000, 0, 0, 0, 0, None, None, hinst, None)
    # Registered one at a time so a single refusal doesn't lose the others.
    wanted = [(0x01, 0x06, "keyboard"), (0x0C, 0x01, "consumer control"),
              (0x01, 0x80, "system control"), (0xFFFF, 0x01, "this mouse's vendor channel")]
    raw_ok = True
    for page, usage, label in wanted:
        one = (RAWINPUTDEVICE * 1)(RAWINPUTDEVICE(page, usage, RIDEV_INPUTSINK, hwnd))
        ok = user32.RegisterRawInputDevices(one, 1, ctypes.sizeof(RAWINPUTDEVICE))
        log(f"register raw input {label} (page 0x{page:04X} usage 0x{usage:04X}): {'ok' if ok else 'REFUSED'}")
        raw_ok = raw_ok and bool(ok)
    kh = user32.SetWindowsHookExW(WH_KEYBOARD_LL, keyboard_proc, hinst, 0)
    mh = user32.SetWindowsHookExW(WH_MOUSE_LL, mouse_proc, hinst, 0)
    log(f"READY  raw_input={'ok' if raw_ok else 'FAILED'} keyboard_hook={'ok' if kh else 'FAILED'} "
        f"mouse_hook={'ok' if mh else 'FAILED'}  for {DURATION:.0f}s")
    list_devices()
    msg = wintypes.MSG()
    deadline = time.time() + DURATION
    while time.time() < deadline:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.005)
    for h in (kh, mh):
        if h:
            user32.UnhookWindowsHookEx(h)
    log("DONE")
    LOG.close()


if __name__ == "__main__":
    main()
