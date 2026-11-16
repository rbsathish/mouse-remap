"""Live check of the DPI-level reader against a real mouse: press the DPI button and watch the level change.

Usage:  .venv\\Scripts\\python.exe tools\\live_dpi_test.py [seconds]
Read-only: nothing is sent to the mouse.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repo root

import mouse_remap as mr

seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 30
print("DPI channel:", mr.find_dpi_channel() or "NOT FOUND")
mon = mr.DpiMonitor()
mon.start()
print(f"Press the DPI button for {seconds:.0f}s ...", flush=True)
shown = (None, None)
end = time.time() + seconds
while time.time() < end:
    state = (mon.connected, mon.level)
    if state != shown:
        shown = state
        print(f"  connected={mon.connected}  level={mon.level}", flush=True)
    time.sleep(0.05)
mon.stop()
