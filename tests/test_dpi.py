"""Tests for the DPI-level reader.

Only the report parsing and the monitor's behaviour when no mouse is found are tested here; nothing opens a real
device or sends anything to one. `tools/live_dpi_test.py` checks it against a real mouse.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repo root

import mouse_remap as mr

results = []


def check(name, ok):
    print(("PASS  " if ok else "FAIL  ") + name)
    results.append(ok)


# reports captured from the real mouse, one per DPI-button press (the 0F pairs are press/release flags)
check("level index 0 shows as level 1", mr.parse_dpi_levels(bytes.fromhex("050c0000")) == [1])
check("level index 3 shows as level 4", mr.parse_dpi_levels(bytes.fromhex("050c0300")) == [4])
check("flag reports are ignored", mr.parse_dpi_levels(bytes.fromhex("050f0100")) == [])
check("several reports in one read, in order",
      mr.parse_dpi_levels(bytes.fromhex("050c0100 050f0100")) == [2])
check("level followed by flags", mr.parse_dpi_levels(bytes.fromhex("050c0200 050f0000")) == [3])
check("two levels in one read", mr.parse_dpi_levels(bytes.fromhex("050c0100050c0200")) == [2, 3])
check("other report ids are ignored", mr.parse_dpi_levels(bytes.fromhex("010c0300")) == [])
check("empty data", mr.parse_dpi_levels(b"") == [])
check("truncated report is ignored", mr.parse_dpi_levels(bytes.fromhex("050c03")) == [])

# with no mouse around, the monitor stays quiet, retries, and stops promptly
calls = []
mon = mr.DpiMonitor(finder=lambda: calls.append(1))
mon.RETRY_SECONDS = 0.05
mon.start()
time.sleep(0.3)
check("not connected when the channel isn't found", mon.connected is False and mon.level is None)
check("keeps looking for the channel", len(calls) >= 3)
t0 = time.time()
mon.stop()
mon._thread.join(2)
check("stops promptly", not mon._thread.is_alive() and time.time() - t0 < 1)

# a failing lookup must not kill the thread
def broken():
    calls.append(2)
    raise OSError("device list unavailable")


mon = mr.DpiMonitor(finder=broken)
mon.RETRY_SECONDS = 0.05
mon.start()
time.sleep(0.3)
check("survives a failing lookup", mon._thread.is_alive())
mon.stop()
mon._thread.join(2)

# the real lookup runs without crashing on this machine (finds a path or None)
found = mr.find_dpi_channel()
check("real device lookup returns a path or None", found is None or isinstance(found, str))

print()
if all(results):
    print(f"{len(results)} checks passed")
else:
    print(f"{results.count(False)} of {len(results)} checks FAILED")
    sys.exit(1)
