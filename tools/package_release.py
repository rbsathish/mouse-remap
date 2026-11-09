"""Packs dist\\MouseRemap.exe into dist\\MouseRemap-<version>-win64.zip and writes its SHA-256 next to it."""
import hashlib
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from _version import __version__  # noqa: E402

exe = os.path.join(ROOT, "dist", "MouseRemap.exe")
if not os.path.exists(exe):
    raise SystemExit("dist\\MouseRemap.exe not found: run build.bat first")

archive = os.path.join(ROOT, "dist", f"MouseRemap-{__version__}-win64.zip")
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(exe, "MouseRemap.exe")
    for name in ("README.md", "CHANGELOG.md", "LICENSE"):
        z.write(os.path.join(ROOT, name), name)

digest = hashlib.sha256(open(archive, "rb").read()).hexdigest()
with open(archive + ".sha256", "w", encoding="ascii") as f:
    f.write(f"{digest}  {os.path.basename(archive)}\n")
print(f"{archive}\nsha256 {digest}")
