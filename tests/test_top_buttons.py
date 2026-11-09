"""Tests for the Search / Screenshot / Desktop top-button logic.

No real keyboard hook is installed: key events are fed straight to TopButtonHook.handle_key with a stand-in
for the device lookup, so nothing here can interfere with your keyboard.
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repo root

import mouse_remap as mr

SHIFT, WIN, F23, PRTSC, D = 0xA0, 0x5B, 0x86, 0x2C, 0x44
SCAN = {F23: 0x6E, PRTSC: 0x37, D: 0x20}
results = []


def check(name, ok):
    print(("PASS  " if ok else "FAIL  ") + name)
    results.append(ok)


class FakeTagger:
    def __init__(self):
        self.mouse = True
        self.calls = 0

    def came_from_mouse(self, make, released, since, timeout=0.02):
        self.calls += 1
        return self.mouse


def make_hook(mapping):
    tagger, sent = FakeTagger(), []
    hook = mr.TopButtonHook(tagger, sender=sent.append)
    hook.mapping = {k: mr.parse_combo(v) for k, v in mapping.items()}
    threading.Thread(target=hook._send_thread, daemon=True).start()   # delivery thread only, no real hook
    return hook, tagger, sent


def press(hook, vk, down=True):
    return hook.handle_key(vk, SCAN.get(vk, 0), down)


CTRL_F, CTRL_C, CTRL_V = (0xA2, 0x46), (0xA2, 0x43), (0xA2, 0x56)

# --- Search = Shift+Win+F23 from the mouse
hook, tagger, sent = make_hook({"search": "ctrl+f"})
press(hook, SHIFT); press(hook, WIN)
check("Search: F23 from the mouse is swallowed", press(hook, F23) is True)
check("Search: Win is masked so Start doesn't open", sent == [(mr.VK_MASK,)])
check("Search: auto-repeat of F23 is swallowed without a second action", press(hook, F23) is True and len(sent) == 1)
time.sleep(0.1)
check("Search: custom action waits while Win+Shift are still held", len(sent) == 1)
press(hook, SHIFT, False); press(hook, WIN, False)
check("Search: F23 release is swallowed", press(hook, F23, False) is True)
time.sleep(0.2)
check("Search: custom action sent after Win+Shift released", sent == [(mr.VK_MASK,), CTRL_F])
hook.stop()

# --- Screenshot = Print Screen (press held back; the RELEASE says where it came from)
hook, tagger, sent = make_hook({"screenshot": "ctrl+c"})
check("Screenshot: the press is held back", press(hook, PRTSC) is True)
check("Screenshot: auto-repeat while held is swallowed", press(hook, PRTSC) is True)
time.sleep(0.1)
check("Screenshot: nothing sent until the release identifies the source", sent == [] and tagger.calls == 0)
check("Screenshot: the release passes through (raw record only exists after the hook returns)",
      press(hook, PRTSC, False) is False)
time.sleep(0.15)
check("Screenshot: from the mouse -> custom action, no mask, no replay", sent == [CTRL_C])
tagger.mouse = False
sent.clear()
press(hook, PRTSC)
check("Screenshot: keyboard release passes through too", press(hook, PRTSC, False) is False)
time.sleep(0.15)
check("Screenshot: from the keyboard -> Print Screen replayed unchanged", sent == [(mr.VK_SNAPSHOT,)])
hook.stop()

# --- Desktop = Win+D
hook, tagger, sent = make_hook({"desktop": "ctrl+v"})
press(hook, WIN)
check("Desktop: D (with Win held) from the mouse is swallowed", press(hook, D) is True)
check("Desktop: Win is masked", sent == [(mr.VK_MASK,)])
press(hook, WIN, False)   # the mouse releases Win BEFORE D, as seen in the real capture
check("Desktop: D release is still swallowed after Win is up", press(hook, D, False) is True)
time.sleep(0.2)
check("Desktop: custom action sent after Win released", sent == [(mr.VK_MASK,), CTRL_V])
tagger.mouse = False
sent.clear()
press(hook, WIN)
check("Desktop: a fast Win+D that the device lookup says is the keyboard passes through", press(hook, D) is False)
press(hook, WIN, False); press(hook, D, False)
time.sleep(0.1)
check("Desktop: ...and triggers nothing", sent == [])
tagger.mouse = True   # even if the lookup said 'mouse', a human-speed Win then D must not be taken
calls = tagger.calls
press(hook, WIN)
time.sleep(mr.TopButtonHook.COMBO_GAP_SECONDS + 0.03)
check("Desktop: Win then D more than 30 ms apart is a person typing: passes through, no wait",
      press(hook, D) is False and tagger.calls == calls and sent == [])
press(hook, WIN, False); press(hook, D, False)
hook.stop()

# --- things that must never be touched
hook, tagger, sent = make_hook({"search": "", "screenshot": "", "desktop": ""})
press(hook, WIN)
untouched = [press(hook, F23), press(hook, F23, False), press(hook, PRTSC), press(hook, PRTSC, False),
             press(hook, D), press(hook, D, False)]
check("Unmapped (Normal) buttons pass through and never ask the device lookup",
      untouched == [False] * 6 and tagger.calls == 0)
hook.stop()

hook, tagger, sent = make_hook({"screenshot": "ctrl+c"})
hook.enabled = False
check("Remapping switched off: Print Screen passes through", press(hook, PRTSC) is False and tagger.calls == 0)
hook.enabled = True
hook.mapping = {}
check("Mapping removed mid-press still replays Print Screen",
      press(hook, PRTSC) is False)   # no mapping at press time -> untouched
hook.mapping = {"screenshot": mr.parse_combo("ctrl+c")}
press(hook, PRTSC)
hook.mapping = {}   # settings applied between press and release
press(hook, PRTSC, False)
time.sleep(0.15)
check("Print Screen is replayed if the mapping vanished before the release", sent == [(mr.VK_SNAPSHOT,)])
hook.mapping = {"screenshot": mr.parse_combo("ctrl+c")}
hook.enabled = True
press(hook, WIN, False)
check("D without Win is never a Desktop press", press(hook, D) is False and tagger.calls == 0)
check("Ordinary letter keys are ignored", press(hook, 0x41) is False and press(hook, 0x41, False) is False)
hook.stop()

# --- the device lookup itself (records fed in by hand)
tagger = mr.RawKeyTagger()
now = time.monotonic()
tagger._records.append((now, 0x37, False, True))
tagger._records.append((now, 0x20, False, False))
check("Lookup: record from the mouse channel -> True", tagger.came_from_mouse(0x37, False, now - 0.01) is True)
check("Lookup: record from the keyboard -> False", tagger.came_from_mouse(0x20, False, now - 0.01) is False)
check("Lookup: no record at all -> False after the short wait", tagger.came_from_mouse(0x6E, False, now - 0.01) is False)
check("Lookup: a stale record from an earlier press is ignored", tagger.came_from_mouse(0x37, False, now + 1) is False)

late = mr.RawKeyTagger()
since = time.monotonic() - 0.01


def deliver_late():   # spin-wait: threading.Timer is too coarse on Windows (about 15 ms steps)
    end = time.perf_counter() + 0.007
    while time.perf_counter() < end:
        pass
    late._records.append((time.monotonic(), 0x6E, False, True))


threading.Thread(target=deliver_late, daemon=True).start()
check("Lookup: waits for a raw record that arrives 7 ms late", late.came_from_mouse(0x6E, False, since) is True)

# --- this PC's real devices
ids = mr.mouse_keyboard_ids()
print("INFO  mice that also have a keyboard channel here:", sorted(ids))
check("Device scan finds the 3151:5031 mouse", ("3151", "5031") in ids)
check("...and does not mistake the plain keyboard (1A2C) or the other mouse (30FA)",
      ("1A2C", "0E24") not in ids and ("30FA", "0300") not in ids)

real = mr.RawKeyTagger()
real.start()
check("Raw Input window registered", real.available)
real.stop()

print(f"\n{sum(results)}/{len(results)} checks passed")
raise SystemExit(0 if all(results) else 1)
