@echo off
rem Builds dist\MouseRemap.exe (single file, no console window, version taken from _version.py)
rem and packs dist\MouseRemap-<version>-win64.zip plus its .sha256.
cd /d "%~dp0"
set SSL_CERT_FILE=
set SSL_CERT_DIR=
if not exist .venv\Scripts\python.exe (
  echo No .venv found. Run:  py -3.12 -m venv .venv ^&^& .venv\Scripts\python -m pip install -r requirements-dev.txt
  exit /b 1
)
.venv\Scripts\python.exe tools\make_version_info.py || exit /b 1
.venv\Scripts\pyinstaller.exe --noconsole --onefile --name MouseRemap --version-file version_info.txt mouse_remap.py || exit /b 1
.venv\Scripts\python.exe tools\package_release.py || exit /b 1
echo.
echo Built: %~dp0dist\MouseRemap.exe
