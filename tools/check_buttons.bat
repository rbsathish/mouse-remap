@echo off
rem Shows what the mouse's extra buttons send to Windows. Watches for 30 seconds, changes nothing, and does not
rem record normal typing (only Windows-key combos, media keys, F13-F24, Print Screen and mouse buttons).
cd /d "%~dp0.."
set SSL_CERT_FILE=
set SSL_CERT_DIR=
set LOG=%TEMP%\mouse_remap_check.txt
echo.
echo Watching for 30 seconds. Press each extra mouse button a few times now.
echo Please do not type anything else until it finishes.
echo.
.venv\Scripts\python.exe tools\capture_keys.py 30 "%LOG%"
echo.
echo ---- What Windows saw (lines naming a device show which one sent it) ----
findstr /v /c:"register raw input" /c:"READY" /c:"DEVICE" /c:"DONE" "%LOG%"
echo ---- end ----
echo (Nothing listed above means Windows received nothing from those buttons.)
echo Full log, including a list of your input devices: %LOG%
pause
