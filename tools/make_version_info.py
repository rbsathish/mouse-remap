"""Writes version_info.txt, the Windows file-properties resource PyInstaller embeds in MouseRemap.exe.

Right-click the exe > Properties > Details then shows the product name and version from _version.py.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from _version import __version__  # noqa: E402

if not re.fullmatch(r"\d+\.\d+\.\d+", __version__):
    raise SystemExit(f"_version.py must hold MAJOR.MINOR.PATCH, got {__version__!r}")

major, minor, patch = (int(part) for part in __version__.split("."))
four = f"{major}, {minor}, {patch}, 0"

TEXT = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({four}), prodvers=({four}), mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('FileDescription', 'Mouse Button Remap'),
      StringStruct('FileVersion', '{__version__}.0'),
      StringStruct('InternalName', 'MouseRemap'),
      StringStruct('OriginalFilename', 'MouseRemap.exe'),
      StringStruct('ProductName', 'Mouse Button Remap'),
      StringStruct('ProductVersion', '{__version__}'),
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ]
)
"""

out = os.path.join(ROOT, "version_info.txt")
with open(out, "w", encoding="utf-8") as f:
    f.write(TEXT)
print(f"wrote {out} for version {__version__}")
