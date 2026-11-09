@echo off
rem Runs the tool from source with no console window.
cd /d "%~dp0"
start "" .venv\Scripts\pythonw.exe mouse_remap.py
