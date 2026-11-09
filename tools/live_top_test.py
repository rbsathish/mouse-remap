"""Live trial of the top-button hook on the real mouse. Installs the real hook but only LOGS what it would send.

usage: python tools\live_top_test.py [seconds] [logfile]   (default log: %TEMP%\mouse_remap_live_test.txt)
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repo root

import mouse_remap as mr

DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 50.0
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else os.path.join(tempfile.gettempdir(), "mouse_remap_live_test.txt")
T0 = time.perf_counter()
log_file = open(LOG_PATH, "w", encoding="utf-8")


def log(line):
    log_file.write(f"{time.perf_counter() - T0:8.3f}  {line}\n")
    log_file.flush()


class LoggingTagger(mr.RawKeyTagger):
    def came_from_mouse(self, make, released, since, timeout=mr.RAW_WAIT_SECONDS):
        start = time.perf_counter()
        result = super().came_from_mouse(make, released, since, timeout)
        log(f"lookup make=0x{make:02X} {'up' if released else 'down'} -> {'MOUSE' if result else 'not mouse'} "
            f"(waited {1000 * (time.perf_counter() - start):.1f} ms)")
        return result


tagger = LoggingTagger()
tagger.start()
def sender(combo):
    # The Start-menu mask and a replayed keyboard Print Screen are sent for real so your keyboard behaves normally;
    # your three mapped actions (ctrl+alt+1/2/3) are only logged.
    if combo == (mr.VK_MASK,):
        log("send for real: Start-menu mask")
        mr.send_combo(combo)
    elif combo == (mr.VK_SNAPSHOT,):
        log("send for real: replay keyboard Print Screen")
        mr.send_combo(combo)
    else:
        log(f"WOULD SEND {combo}  <- your mapped action for a mouse button")


hook = mr.TopButtonHook(tagger, sender=sender)
hook.mapping = {"search": mr.parse_combo("ctrl+alt+1"), "screenshot": mr.parse_combo("ctrl+alt+2"),
                "desktop": mr.parse_combo("ctrl+alt+3")}
hook.start()
log(f"READY raw_input={'ok' if tagger.available else 'FAILED'} for {DURATION:.0f}s")
time.sleep(DURATION)
hook.stop()
tagger.stop()
log("DONE")
log_file.close()
