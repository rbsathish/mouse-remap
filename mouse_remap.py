"""Mouse Button Remap: turn extra mouse buttons (back / forward / middle) into key combos on Windows.

Works the same for 2.4G, Bluetooth or USB because it hooks the buttons Windows receives,
not the radio link. A small tkinter window edits the mapping; a tray icon keeps it running.
"""
import collections
import ctypes
import json
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
import winreg
from ctypes import wintypes
from tkinter import messagebox, ttk

import pystray
from PIL import Image, ImageDraw

from _version import __version__

APP_NAME = "MouseRemap"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

# ---------------------------------------------------------------- Win32 plumbing

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

WH_MOUSE_LL = 14
HC_ACTION = 0
WM_QUIT = 0x0012
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
SIMPLE_BUTTONS = {WM_LBUTTONDOWN: ("left", True), WM_LBUTTONUP: ("left", False),
                  WM_RBUTTONDOWN: ("right", True), WM_RBUTTONUP: ("right", False),
                  WM_MBUTTONDOWN: ("middle", True), WM_MBUTTONUP: ("middle", False)}
WM_XBUTTONDOWN, WM_XBUTTONUP = 0x020B, 0x020C
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x0001, 0x0002
ERROR_ALREADY_EXISTS = 183


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _InputUnion(ctypes.Union):
    # MOUSEINPUT is the largest member, so including it gives INPUT its correct size.
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _InputUnion)]


user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.SetEvent.argtypes = [wintypes.HANDLE]
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

# ---------------------------------------------------------------- key combos

MODIFIERS = {"ctrl": 0xA2, "control": 0xA2, "alt": 0xA4, "shift": 0xA0, "win": 0x5B, "windows": 0x5B}
NAMED_KEYS = {
    "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B, "tab": 0x09, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "printscreen": 0x2C, "volume_mute": 0xAD, "volume_down": 0xAE, "volume_up": 0xAF,
    "media_next": 0xB0, "media_prev": 0xB1, "media_stop": 0xB2, "media_play_pause": 0xB3,
}
EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2C, 0x2D, 0x2E, 0x5B}


def parse_combo(text):
    """'ctrl+shift+t' -> (0xA2, 0xA0, 0x54). Empty text -> () meaning 'leave the button alone'."""
    text = (text or "").strip().lower()
    if not text:
        return ()
    mods, key = [], None
    for part in (p.strip() for p in text.split("+")):
        if not part:
            raise ValueError(f"Empty part in '{text}'")
        if part in MODIFIERS:
            if MODIFIERS[part] not in mods:
                mods.append(MODIFIERS[part])
        elif key is not None:
            raise ValueError(f"'{text}' has more than one non-modifier key")
        elif part in NAMED_KEYS:
            key = NAMED_KEYS[part]
        elif len(part) == 1 and (part.isalpha() or part.isdigit()) and part.isascii():
            key = ord(part.upper())
        elif part[0] == "f" and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            key = 0x70 + int(part[1:]) - 1
        else:
            raise ValueError(f"Unknown key '{part}'")
    return tuple(mods + ([key] if key is not None else []))


def _key_event(vk, up):
    flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if vk in EXTENDED_VKS else 0)
    return INPUT(type=INPUT_KEYBOARD, u=_InputUnion(ki=KEYBDINPUT(wVk=vk, dwFlags=flags)))


def send_combo(vks):
    """Press every key in order, then release in reverse, in one SendInput call."""
    events = [_key_event(vk, False) for vk in vks] + [_key_event(vk, True) for vk in reversed(vks)]
    array = (INPUT * len(events))(*events)
    user32.SendInput(len(events), array, ctypes.sizeof(INPUT))


# ---------------------------------------------------------------- the mouse hook

BUTTONS = [("left", "Left button"), ("right", "Right button"), ("middle", "Middle (wheel click)"),
           ("back", "Back (side button)"), ("forward", "Forward (side button)")]


def own_window_active():
    """True while this app's own window has the focus (used so left/right clicks can never lock you out)."""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value == os.getpid()


class MouseHook:
    """Global low-level mouse hook. A mapped button is swallowed and its key combo is sent instead."""

    HOOK_ID = WH_MOUSE_LL

    def __init__(self, sender=send_combo):
        self.mapping = {}          # button name -> tuple of virtual keys; replaced whole, never edited
        self.enabled = True
        self.last_seen = ""
        self._sender = sender
        self.is_own_window = own_window_active
        self._swallowed = set()   # buttons whose press we swallowed, so their release is swallowed too
        self._queue = queue.Queue()
        self._proc = HOOKPROC(self._callback)   # keep a reference or it gets garbage collected
        self._hook = None
        self._thread_id = None
        self._ready = threading.Event()

    def start(self):
        threading.Thread(target=self._hook_thread, daemon=True).start()
        threading.Thread(target=self._send_thread, daemon=True).start()
        self._ready.wait(5)
        if not self._hook:
            raise OSError(f"Could not install the mouse hook (error {ctypes.get_last_error()})")

    def stop(self):
        self._queue.put(None)
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def _hook_thread(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        self._hook = user32.SetWindowsHookExW(self.HOOK_ID, self._proc, kernel32.GetModuleHandleW(None), 0)
        self._ready.set()
        if not self._hook:
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        user32.UnhookWindowsHookEx(self._hook)

    def _send_thread(self):
        # Keystrokes go out from here so the hook callback returns immediately (Windows drops slow hooks).
        while True:
            item = self._queue.get()
            if item is None:
                return
            try:
                self._deliver(item)
            except Exception:
                pass

    def _deliver(self, combo):
        self._sender(combo)

    def _callback(self, n_code, w_param, l_param):
        try:
            if n_code == HC_ACTION:
                name, is_down = None, True
                if w_param in (WM_XBUTTONDOWN, WM_XBUTTONUP):
                    info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    name = {1: "back", 2: "forward"}.get((info.mouseData >> 16) & 0xFFFF)
                    is_down = w_param == WM_XBUTTONDOWN
                elif w_param in SIMPLE_BUTTONS:
                    name, is_down = SIMPLE_BUTTONS[w_param]
                if name:
                    if is_down:
                        self.last_seen = name
                        combo = self.mapping.get(name)
                        # Left/right stay normal while our own window is in front, so a bad mapping is always fixable.
                        locked_out_guard = name in ("left", "right") and self.is_own_window()
                        if combo and self.enabled and not locked_out_guard:
                            self._swallowed.add(name)
                            self._queue.put(combo)
                            return 1
                    elif name in self._swallowed:
                        self._swallowed.discard(name)
                        return 1
        except Exception:
            pass   # never let an error escape into the hook chain
        return user32.CallNextHookEx(None, n_code, w_param, l_param)


# ---------------------------------------------------------------- the three top buttons
#
# Search / Screenshot / Desktop are not mouse clicks: the mouse has its own keyboard channel and sends
#   Search     -> Shift + Win + F23      Screenshot -> Print Screen      Desktop -> Win + D
# Print Screen and Win+D are also what a real keyboard sends, so a key is only taken when Raw Input says
# it came from a device that is both a mouse and a keyboard. Raw Input reports the source a few
# milliseconds AFTER the low-level hook sees the key, so the hook waits briefly for it.
#
# Measured on the real mouse: Windows sends NO raw record for a key PRESS that triggers a system hotkey
# (Copilot, Print Screen, Win+D); it does send the releases and plain modifiers such as Win. So:
#   Search / Desktop: the source is read from the raw record of the Win press just before (the mouse sends
#                     Win and the key within ~7 ms; a person on a keyboard is far slower, so a late D is
#                     passed through without waiting).
#   Screenshot:       the press is held back; the release passes through, and its raw record (which only
#                     appears after the hook returns) names the source, then either your action runs
#                     (mouse) or Print Screen is replayed (keyboard).

TOP_BUTTONS = [("search", "Search (top button)"), ("screenshot", "Screenshot (top button)"),
               ("desktop", "Desktop (top button)")]

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
WM_INPUT = 0x00FF
LLKHF_INJECTED = 0x10
RID_INPUT, RIDI_DEVICENAME, RIDEV_INPUTSINK = 0x10000003, 0x20000007, 0x00000100
RIM_TYPEMOUSE, RIM_TYPEKEYBOARD = 0, 1
VK_SHIFT, VK_LSHIFT, VK_RSHIFT, VK_LWIN, VK_RWIN = 0x10, 0xA0, 0xA1, 0x5B, 0x5C
VK_F23, VK_SNAPSHOT, VK_D = 0x86, 0x2C, 0x44
VK_MASK = 0xE8   # unassigned key: tapped while Win is held so releasing Win doesn't open the Start menu
SCREENSHOT_DECISION = "screenshot-decision"
RAW_WAIT_SECONDS = 0.05   # measured lag of the raw record behind the hook: 0.5-7 ms; Windows drops hooks at 300 ms

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]


class RAWINPUTDEVICELIST(ctypes.Structure):
    _fields_ = [("hDevice", wintypes.HANDLE), ("dwType", wintypes.DWORD)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


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
user32.GetRawInputDeviceList.argtypes = [ctypes.POINTER(RAWINPUTDEVICELIST), ctypes.POINTER(wintypes.UINT), wintypes.UINT]
user32.GetRawInputDeviceList.restype = wintypes.UINT
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]

_VID_PID = re.compile(r"VID[_&]([0-9A-F]{4,6})[&_]PID[_&]([0-9A-F]{4})", re.I)


def vid_pid(device_path):
    m = _VID_PID.search(device_path or "")
    return (m.group(1).upper(), m.group(2).upper()) if m else None


def raw_device_path(handle):
    size = wintypes.UINT(0)
    user32.GetRawInputDeviceInfoW(handle, RIDI_DEVICENAME, None, ctypes.byref(size))
    buf = ctypes.create_unicode_buffer(max(size.value, 1))
    user32.GetRawInputDeviceInfoW(handle, RIDI_DEVICENAME, buf, ctypes.byref(size))
    return buf.value


def mouse_keyboard_ids():
    """VID/PID pairs of devices Windows sees as BOTH a mouse and a keyboard (a mouse with its own key channel)."""
    count = wintypes.UINT(0)
    user32.GetRawInputDeviceList(None, ctypes.byref(count), ctypes.sizeof(RAWINPUTDEVICELIST))
    if not count.value:
        return set()
    devices = (RAWINPUTDEVICELIST * count.value)()
    user32.GetRawInputDeviceList(devices, ctypes.byref(count), ctypes.sizeof(RAWINPUTDEVICELIST))
    mice, keyboards = set(), set()
    for dev in devices:
        ident = vid_pid(raw_device_path(dev.hDevice))
        if ident and dev.dwType == RIM_TYPEMOUSE:
            mice.add(ident)
        elif ident and dev.dwType == RIM_TYPEKEYBOARD:
            keyboards.add(ident)
    return mice & keyboards


class RawKeyTagger:
    """Remembers, for each physical key event, whether it came from the mouse's own keyboard channel."""

    def __init__(self):
        self._records = collections.deque(maxlen=128)   # (monotonic time, make code, is_release, from_mouse)
        self._lock = threading.Lock()
        self._handle_is_mouse = {}
        self._thread_id = None
        self._ready = threading.Event()
        self.available = False
        self._proc = WNDPROC(self._wnd_proc)             # keep a reference or it gets garbage collected

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
        self._ready.wait(5)

    def stop(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def _run(self):
        hinst = kernel32.GetModuleHandleW(None)
        cls = WNDCLASSW(lpfnWndProc=self._proc, hInstance=hinst, lpszClassName="MouseRemapRawKeys")
        user32.RegisterClassW(ctypes.byref(cls))
        hwnd = user32.CreateWindowExW(0x80, "MouseRemapRawKeys", "raw", 0x80000000, 0, 0, 0, 0, None, None, hinst, None)
        device = (RAWINPUTDEVICE * 1)(RAWINPUTDEVICE(0x01, 0x06, RIDEV_INPUTSINK, hwnd))   # keyboards
        self._thread_id = kernel32.GetCurrentThreadId()
        self.available = bool(hwnd) and bool(user32.RegisterRawInputDevices(device, 1, ctypes.sizeof(RAWINPUTDEVICE)))
        self._ready.set()
        if not self.available:
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _is_mouse_channel(self, handle):
        if handle not in self._handle_is_mouse:
            self._handle_is_mouse[handle] = vid_pid(raw_device_path(handle)) in mouse_keyboard_ids()
        return self._handle_is_mouse[handle]

    def _wnd_proc(self, hwnd, msg, w_param, l_param):
        if msg == WM_INPUT:
            try:
                size = wintypes.UINT(0)
                header_size = ctypes.sizeof(RAWINPUTHEADER)
                user32.GetRawInputData(l_param, RID_INPUT, None, ctypes.byref(size), header_size)
                buf = ctypes.create_string_buffer(size.value)
                if size.value and user32.GetRawInputData(l_param, RID_INPUT, buf, ctypes.byref(size), header_size) == size.value:
                    header = RAWINPUTHEADER.from_buffer_copy(buf)
                    if header.dwType == RIM_TYPEKEYBOARD:
                        data = buf.raw[header_size:]
                        make = int.from_bytes(data[0:2], "little")
                        released = bool(int.from_bytes(data[2:4], "little") & 1)
                        record = (time.monotonic(), make, released, self._is_mouse_channel(header.hDevice))
                        with self._lock:
                            self._records.append(record)
            except Exception:
                pass
        return user32.DefWindowProcW(hwnd, msg, w_param, l_param)

    def came_from_mouse(self, make, released, since, timeout=RAW_WAIT_SECONDS):
        """Wait up to `timeout` for the raw record of this key event; False if it isn't from the mouse (or unknown)."""
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                records = list(self._records)
            for stamp, rec_make, rec_released, from_mouse in reversed(records):
                if stamp < since:
                    break
                if rec_make == make and rec_released == released:
                    return from_mouse
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.001)


class TopButtonHook(MouseHook):
    """Keyboard-level hook for the three top buttons; a key is taken only if it came from the mouse."""

    HOOK_ID = WH_KEYBOARD_LL

    COMBO_GAP_SECONDS = 0.03   # the mouse sends Win and its key within ~7 ms; a human is slower than this

    def __init__(self, tagger, sender=send_combo):
        super().__init__(sender)
        self.tagger = tagger
        self._win_down = False
        self._win_down_at = 0.0
        self._win_scan = VK_LWIN
        self._shift_down = False

    def _callback(self, n_code, w_param, l_param):
        try:
            if n_code == HC_ACTION:
                key = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if not key.flags & LLKHF_INJECTED:   # our own SendInput keystrokes are never touched
                    if self.handle_key(key.vkCode, key.scanCode, w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)):
                        return 1
        except Exception:
            pass   # never let an error escape into the hook chain
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def handle_key(self, vk, scan, is_down):
        """True if this key event must be swallowed."""
        now = time.monotonic()
        if vk in (VK_LWIN, VK_RWIN):
            if is_down and not self._win_down:   # first press, not auto-repeat
                self._win_down_at, self._win_scan = now, scan
            self._win_down = is_down
            return False
        if vk in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT):
            self._shift_down = is_down
            return False
        if vk == VK_F23:
            name = "search"
        elif vk == VK_SNAPSHOT:
            name = "screenshot"
        elif vk == VK_D and (self._win_down or vk in self._swallowed):
            name = "desktop"
        else:
            return False
        if name == "screenshot":
            return self._handle_screenshot(vk, scan, is_down, now)
        if not is_down:
            if vk in self._swallowed:
                self._swallowed.discard(vk)
                return True
            return False
        if vk in self._swallowed:
            return True   # auto-repeat of a press we already took
        combo = self.mapping.get(name)
        if not combo or not self.enabled or not self._win_down:
            return False
        if now - self._win_down_at > self.COMBO_GAP_SECONDS:
            return False   # a person pressing Win then the key: your keyboard, no need to wait
        # The key press itself has no raw record (system hotkey); the Win press just before it does.
        if not self.tagger.came_from_mouse(self._win_scan, False, self._win_down_at - 0.005):
            return False
        self._swallowed.add(vk)
        self.last_seen = f"{name} (top button)"
        self._sender((VK_MASK,))
        self._queue.put((combo, True))
        return True

    def _handle_screenshot(self, vk, scan, is_down, now):
        """Hold the press back; the release says whether it was the mouse's button or your keyboard's key."""
        if is_down:
            if vk in self._swallowed:
                return True   # auto-repeat of a press we are holding back
            if not self.mapping.get("screenshot") or not self.enabled:
                return False
            self._swallowed.add(vk)
            return True
        if vk not in self._swallowed:
            return False
        self._swallowed.discard(vk)
        # Windows only creates the raw record of a key AFTER the hook lets it through, so the release must pass
        # (a lone key-up is harmless) and the decision is made afterwards, off the hook thread.
        self._queue.put((SCREENSHOT_DECISION, scan, now - 0.01))
        return False

    def _deliver(self, item):
        if item[0] == SCREENSHOT_DECISION:
            _, scan, since = item
            combo = self.mapping.get("screenshot")
            if combo and self.tagger.came_from_mouse(scan, True, since):
                self.last_seen = "screenshot (top button)"
                self._sender(combo)
            else:
                self._sender((VK_SNAPSHOT,))   # your keyboard's Print Screen: replay it unchanged
            return
        combo, wait_for_release = item
        if wait_for_release:   # sending now would turn "ctrl+c" into Win+Ctrl+C while Win is still held
            deadline = time.monotonic() + 0.6
            while (self._win_down or self._shift_down) and time.monotonic() < deadline:
                time.sleep(0.005)
        self._sender(combo)


# ---------------------------------------------------------------- config + autostart

ALL_BUTTONS = BUTTONS + TOP_BUTTONS
DEFAULT_CONFIG = {"enabled": True, "autostart": False,
                  "buttons": {"left": "", "right": "", "middle": "", "back": "ctrl+c", "forward": "ctrl+v",
                              "search": "", "screenshot": "", "desktop": ""}}


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            saved = json.load(f)
        cfg["enabled"] = bool(saved.get("enabled", cfg["enabled"]))
        cfg["autostart"] = bool(saved.get("autostart", cfg["autostart"]))
        for key, _ in ALL_BUTTONS:
            if isinstance(saved.get("buttons", {}).get(key), str):
                cfg["buttons"][key] = saved["buttons"][key]
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def set_autostart(enabled):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if not enabled:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
            return
        if getattr(sys, "frozen", False):
            command = f'"{sys.executable}" --minimized'
        else:
            pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            command = f'"{pythonw}" "{os.path.abspath(__file__)}" --minimized'
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)


# ---------------------------------------------------------------- the window + tray

PRESETS = [
    ("Normal (don't change this button)", ""),
    ("Copy", "ctrl+c"), ("Paste", "ctrl+v"), ("Cut", "ctrl+x"),
    ("Undo", "ctrl+z"), ("Redo", "ctrl+y"), ("Select all", "ctrl+a"),
    ("Save", "ctrl+s"), ("Find", "ctrl+f"),
    ("Close tab", "ctrl+w"), ("Reopen closed tab", "ctrl+shift+t"),
    ("Next tab", "ctrl+tab"), ("Previous tab", "ctrl+shift+tab"),
    ("Browser back", "alt+left"), ("Browser forward", "alt+right"),
    ("Enter", "enter"), ("Escape", "esc"), ("Delete", "delete"),
    ("Show desktop", "win+d"), ("Screenshot (Snip)", "win+shift+s"), ("Print Screen", "printscreen"),
    ("Windows Search", "win+s"), ("Task view", "win+tab"), ("File Explorer", "win+e"),
    ("Run box", "win+r"), ("Lock PC", "win+l"),
    ("Mute", "volume_mute"), ("Volume up", "volume_up"), ("Volume down", "volume_down"),
    ("Play / pause", "media_play_pause"), ("Next track", "media_next"), ("Previous track", "media_prev"),
]
PRESET_BY_NAME = dict(PRESETS)
PRESET_NAME_BY_COMBO = {combo: name for name, combo in PRESETS}


def make_tray_image():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((18, 4, 46, 60), radius=14, fill=(40, 120, 220, 255), outline=(255, 255, 255, 255), width=3)
    d.line((32, 6, 32, 28), fill=(255, 255, 255, 255), width=3)
    d.line((18, 28, 46, 28), fill=(255, 255, 255, 255), width=3)
    return img


class App:
    def __init__(self, start_hidden):
        self.cfg = load_config()
        self.hook = MouseHook()
        self.tagger = RawKeyTagger()
        self.tagger.start()
        self.top_hook = TopButtonHook(self.tagger)
        self.hooks = (self.hook, self.top_hook)
        mapping = {k: parse_combo(v) for k, v in self.cfg["buttons"].items() if self._valid(v)}
        for h in self.hooks:
            h.enabled = self.cfg["enabled"]
            h.mapping = mapping
            h.start()

        self.ui_q = queue.Queue()
        self._shown = {}
        self.root = tk.Tk()
        self.root.title("Mouse Button Remap")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self._build_ui()

        self.tray = pystray.Icon(APP_NAME, make_tray_image(), f"Mouse Button Remap {__version__}", menu=pystray.Menu(
            pystray.MenuItem("Open", lambda *_: self.ui_q.put("show"), default=True),
            pystray.MenuItem("Remapping on", lambda *_: self.ui_q.put("toggle"), checked=lambda _: self.hook.enabled),
            pystray.MenuItem("Quit", lambda *_: self.ui_q.put("quit"))))
        self.tray.run_detached()
        if start_hidden:
            self.root.withdraw()
        self.root.after(100, self._poll)

    @staticmethod
    def _valid(text):
        try:
            parse_combo(text)
            return True
        except ValueError:
            return False

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}
        frame = ttk.Frame(self.root, padding=12)
        frame.grid()
        self.enabled_var = tk.BooleanVar(value=self.cfg["enabled"])
        ttk.Checkbutton(frame, text="Remapping on", variable=self.enabled_var,
                        command=self._on_enabled_toggled).grid(row=0, column=0, columnspan=2, sticky="w", **pad)
        names = [name for name, _ in PRESETS]
        self.combos = {}
        row = 1
        for key, label in ALL_BUTTONS:
            if key == "search":
                ids = mouse_keyboard_ids() if self.tagger.available else set()
                note = ("active for mouse " + ", ".join(f"{v}:{p}" for v, p in sorted(ids))) if ids else \
                    "not available: no mouse with its own key channel found"
                ttk.Label(frame, text=f"Top buttons: {note}", foreground="#555").grid(
                    row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 0))
                row += 1
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", **pad)
            box = ttk.Combobox(frame, values=names, width=34)
            combo = self.cfg["buttons"][key]
            box.set(PRESET_NAME_BY_COMBO.get(combo, combo))
            box.grid(row=row, column=1, sticky="w", **pad)
            self.combos[key] = box
            row += 1
        ttk.Label(frame, text="Pick from the list, or type your own, e.g. ctrl+shift+s or alt+left",
                  foreground="#555").grid(row=row, column=0, columnspan=2, sticky="w", padx=10)
        ttk.Label(frame, text="Left and right always click normally while this window is open,\n"
                              "so you can undo a bad mapping. Relaunching the exe reopens it.",
                  foreground="#555").grid(row=row + 1, column=0, columnspan=2, sticky="w", padx=10, pady=(4, 0))
        self.autostart_var = tk.BooleanVar(value=self.cfg["autostart"])
        ttk.Checkbutton(frame, text="Start with Windows", variable=self.autostart_var).grid(
            row=row + 2, column=0, columnspan=2, sticky="w", **pad)
        ttk.Button(frame, text="Apply and save", command=self.apply).grid(row=row + 3, column=0, sticky="w", **pad)
        self.status = ttk.Label(frame, text="")
        self.status.grid(row=row + 3, column=1, sticky="w", **pad)
        self.seen = ttk.Label(frame, text="Last button Windows saw: (press one)", foreground="#555")
        self.seen.grid(row=row + 4, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 0))
        ttk.Label(frame, text="Closing this window keeps it running in the tray.",
                  foreground="#555").grid(row=row + 5, column=0, columnspan=2, sticky="w", padx=10)
        ttk.Label(frame, text=f"Version {__version__}", foreground="#888").grid(
            row=row + 6, column=0, columnspan=2, sticky="w", padx=10, pady=(6, 0))

    def _combo_text(self, key):
        text = self.combos[key].get().strip()
        return PRESET_BY_NAME.get(text, text)

    def apply(self):
        mapping, texts = {}, {}
        for key, label in ALL_BUTTONS:
            text = self._combo_text(key)
            try:
                mapping[key] = parse_combo(text)
            except ValueError as err:
                messagebox.showerror("Can't use that", f"{label}: {err}", parent=self.root)
                return
            texts[key] = text
        risky = [label for key, label in BUTTONS if key in ("left", "right") and mapping[key]]
        if risky and not messagebox.askyesno(
                "Remap a main button?",
                f"You are changing: {', '.join(risky)}.\n\nThat button will stop clicking and send the key "
                "instead, everywhere except in this window. If something goes wrong, relaunch MouseRemap.exe "
                "to bring this window back and set it to Normal.\n\nContinue?", parent=self.root):
            return
        for h in self.hooks:
            h.mapping = mapping
            h.enabled = self.enabled_var.get()
        self.cfg.update(enabled=self.hook.enabled, autostart=self.autostart_var.get(), buttons=texts)
        try:
            save_config(self.cfg)
            set_autostart(self.cfg["autostart"])
        except OSError as err:
            messagebox.showerror("Could not save", str(err), parent=self.root)
            return
        self.status.config(text="Saved, active now")

    def _on_enabled_toggled(self):
        for h in self.hooks:
            h.enabled = self.enabled_var.get()
        self.cfg["enabled"] = self.hook.enabled

    def hide(self):
        self.root.withdraw()

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _poll(self):
        try:
            while True:
                action = self.ui_q.get_nowait()
                if action == "show":
                    self.show()
                elif action == "toggle":
                    self.enabled_var.set(not self.hook.enabled)
                    self._on_enabled_toggled()
                    try:
                        save_config(self.cfg)
                    except OSError:
                        pass
                elif action == "quit":
                    self.quit()
                    return
        except queue.Empty:
            pass
        for h in self.hooks:   # show whichever hook saw something new
            if h.last_seen and h.last_seen != self._shown.get(id(h)):
                self._shown[id(h)] = h.last_seen
                self.seen.config(text=f"Last button Windows saw: {h.last_seen}")
        self.root.after(100, self._poll)

    def quit(self):
        for h in self.hooks:
            h.stop()
        self.tagger.stop()
        self.tray.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    mutex = kernel32.CreateMutexW(None, False, "Local\\MouseRemapSingleInstance")
    show_event = kernel32.CreateEventW(None, False, False, "Local\\MouseRemapShowWindow")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.SetEvent(show_event)     # a second launch just asks the running copy to open its window
        return
    app = App(start_hidden="--minimized" in sys.argv)

    def wait_for_relaunch():
        while kernel32.WaitForSingleObject(show_event, 0xFFFFFFFF) == 0:
            app.ui_q.put("show")

    threading.Thread(target=wait_for_relaunch, daemon=True).start()
    app.run()
    kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    main()
