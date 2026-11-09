# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.1] - 2026-11-09

Documentation release. The app behaves exactly as in 1.0.0; the version number and the README bundled in the zip are
what changed.

### Changed
- Documentation: state the exact mouse the app was tested on, what was and was not tested, and a compatibility
  table for other mice.

## [1.0.0] - 2026-11-09

First release.

### Added
- Remap the five standard mouse buttons (left, right, middle, back, forward) to key combinations, media keys, or leave
  them as normal.
- Remap the three top buttons of the Amazon Basics Pro Series triple-mode mouse: **Search** (Shift+Win+F23),
  **Screenshot** (Print Screen) and **Desktop** (Win+D). The mouse's own keyboard channel is told apart from your real
  keyboard, so your keyboard's Win+D and Print Screen keep working.
- Settings window with presets and free-form combinations; saved to `%APPDATA%\MouseRemap\config.json`.
- System tray icon: open, turn remapping on or off, quit. Closing the window keeps the app running.
- Optional *Start with Windows* (per-user, starts hidden in the tray).
- Single instance: starting the exe again re-opens the window.
- Safety for left and right: a confirmation when changing them, and they always click normally while the settings
  window is in front.
- Version number shown in the window, the tray tooltip and the exe's file properties.
- Diagnostics in `tools/`: `check_buttons.bat` to see what your buttons send, and a live trial script.
- Automated tests (`test.bat`).
- MIT license.
