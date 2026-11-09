"""Tests for mouse_remap. Injects synthetic side-button presses through SendInput.

Only buttons that are MAPPED are ever injected, so every injected press is swallowed by the hook
and never reaches whatever window you have open.
"""
import ctypes
import os
import sys
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repo root

import mouse_remap as mr

INPUT_MOUSE, XDOWN, XUP, MDOWN, MUP = 0, 0x0080, 0x0100, 0x0020, 0x0040
LDOWN, LUP, RDOWN, RUP = 0x0002, 0x0004, 0x0008, 0x0010


def click(flag_down, flag_up, data=0):
    for flag in (flag_down, flag_up):
        ev = mr.INPUT(type=INPUT_MOUSE, u=mr._InputUnion(mi=mr.MOUSEINPUT(mouseData=data, dwFlags=flag)))
        mr.user32.SendInput(1, ctypes.byref(ev), ctypes.sizeof(mr.INPUT))
        time.sleep(0.03)


def pump(root, seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def check(name, ok):
    print(("PASS  " if ok else "FAIL  ") + name)
    return ok


results = []

# --- parsing
results.append(check("ctrl+c -> (LCtrl, C)", mr.parse_combo("ctrl+c") == (0xA2, 0x43)))
results.append(check("ctrl+shift+t order", mr.parse_combo("Ctrl + Shift + T") == (0xA2, 0xA0, 0x54)))
results.append(check("alt+left", mr.parse_combo("alt+left") == (0xA4, 0x25)))
results.append(check("f5 and media key", mr.parse_combo("f5") == (0x74,) and mr.parse_combo("media_next") == (0xB0,)))
results.append(check("empty means leave alone", mr.parse_combo("") == () and mr.parse_combo("   ") == ()))
for bad in ("ctrl+", "a+b", "ctrl+banana", "f99", "+"):
    try:
        mr.parse_combo(bad)
        results.append(check(f"rejects '{bad}'", False))
    except ValueError:
        results.append(check(f"rejects '{bad}'", True))

# --- hook interception (recording sender, nothing typed anywhere)
sent = []
hook = mr.MouseHook(sender=sent.append)
hook.mapping = {"back": mr.parse_combo("ctrl+c"), "forward": mr.parse_combo("ctrl+v"), "middle": mr.parse_combo("ctrl+x")}
hook.start()
click(XDOWN, XUP, 1)
click(XDOWN, XUP, 2)
click(MDOWN, MUP)
time.sleep(0.3)
results.append(check("back -> ctrl+c, forward -> ctrl+v, middle -> ctrl+x",
                     sent == [(0xA2, 0x43), (0xA2, 0x56), (0xA2, 0x58)]))
results.append(check("hook reports last button seen", hook.last_seen == "middle"))
hook.mapping.update(left=mr.parse_combo("ctrl+a"), right=mr.parse_combo("f5"))
sent.clear()
click(LDOWN, LUP)
click(RDOWN, RUP)
time.sleep(0.3)
results.append(check("left -> ctrl+a, right -> f5", sent == [(0xA2, 0x41), (0x74,)]))

# Lock-out guard: with our own window in front, a mapped left/right must pass through (not be swallowed).
hook.is_own_window = lambda: True
for msg, name in ((mr.WM_LBUTTONDOWN, "left"), (mr.WM_RBUTTONDOWN, "right")):
    info = mr.MSLLHOOKSTRUCT()
    sent.clear()
    swallowed = hook._callback(0, msg, ctypes.addressof(info))
    time.sleep(0.1)
    results.append(check(f"{name} click passes through while own window is active", swallowed != 1 and not sent))
hook.is_own_window = lambda: False
info = mr.MSLLHOOKSTRUCT()
results.append(check("...but is swallowed otherwise", hook._callback(0, mr.WM_LBUTTONDOWN, ctypes.addressof(info)) == 1))
hook._callback(0, mr.WM_LBUTTONUP, ctypes.addressof(info))   # release the swallowed press
hook.stop()

# --- end to end with real keystrokes, only if our own test window really has the keyboard focus
root = tk.Tk()
root.title("mouse_remap test")
root.attributes("-topmost", True)
entry = tk.Entry(root, width=30)
entry.pack(padx=20, pady=20)
root.update()
mr.user32.SetForegroundWindow(root.winfo_id())
entry.focus_force()
pump(root, 0.4)
mine = {root.winfo_id(), mr.user32.GetParent(root.winfo_id())}
if mr.user32.GetForegroundWindow() in mine:
    try:
        saved = root.clipboard_get()
    except tk.TclError:
        saved = ""
    real = mr.MouseHook()   # default sender: real SendInput
    real.mapping = {"back": mr.parse_combo("ctrl+c"), "forward": mr.parse_combo("ctrl+v")}
    real.start()
    entry.insert(0, "ABC")
    entry.select_range(0, "end")
    click(XDOWN, XUP, 1)            # Back  -> ctrl+c
    pump(root, 0.4)
    results.append(check("real Back press copied the selection", root.clipboard_get() == "ABC"))
    entry.delete(0, "end")
    click(XDOWN, XUP, 2)            # Forward -> ctrl+v
    pump(root, 0.4)
    results.append(check("real Forward press pasted it", entry.get() == "ABC"))
    real.stop()
    root.clipboard_clear()
    root.clipboard_append(saved)
    root.update()
else:
    print("SKIP  end-to-end typing (test window did not get focus; nothing was injected)")
root.destroy()

print(f"\n{sum(results)}/{len(results)} checks passed")
raise SystemExit(0 if all(results) else 1)
