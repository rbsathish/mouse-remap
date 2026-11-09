@echo off
rem Runs both test files. Synthetic mouse presses are injected only for buttons that are mapped (and so swallowed),
rem and no real keyboard hook is installed, so nothing here reaches your open windows.
cd /d "%~dp0"
set SSL_CERT_FILE=
set SSL_CERT_DIR=
.venv\Scripts\python.exe tests\test_top_buttons.py || exit /b 1
.venv\Scripts\python.exe tests\test_remap.py || exit /b 1
echo.
echo All tests passed.
