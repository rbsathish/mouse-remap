# How it works

This document explains the design and records what was measured about the target mouse, because the top buttons
behave in ways that are not obvious and the design follows from those measurements.

## 1. The standard buttons: a low-level mouse hook

`MouseHook` installs a global low-level mouse hook (`WH_MOUSE_LL`) on its own thread with its own message loop.

- Windows calls the hook for every mouse button message. Left, right and middle arrive as ordinary button messages;
  Back and Forward arrive as "X button" messages whose high word says which one (1 = back, 2 = forward).
- If the button is mapped, the hook **swallows** the press (returns 1 instead of passing it on) and puts the key
  combination on a queue. A second thread sends the keys with `SendInput`, so the hook callback returns immediately.
  (Windows removes hooks that are too slow.)
- The matching **release** is also swallowed, tracked in a set, so an application never sees half a click even if the
  mapping is changed between press and release.
- Keys are pressed in order and released in reverse inside a single `SendInput` call.
- Keystrokes the app injects are flagged by Windows as injected, and the keyboard hook ignores those, so the app can
  never trigger itself.

**Left/right guard.** While the app's own window is the foreground window, left and right are never swallowed. That
means a bad mapping of both main buttons can always be fixed by opening the window.

## 2. The three top buttons: what the mouse actually is

The mouse reports itself to Windows as one device with several parts (USB IDs `3151:5031`):

| Part | What it is |
|---|---|
| Mouse interface | 5 buttons: left, right, middle, back, forward |
| Keyboard interface | 264 keys: the top buttons come out of here |
| Consumer-control interface | media keys (unused by this mouse's buttons) |
| Vendor-defined interface | the maker's configuration channel |

A capture of what Windows receives (using `tools/capture_keys.py`) showed the three top buttons are **not** mouse
clicks. They are keystrokes from the keyboard interface:

| Button | Keys sent |
|---|---|
| Search | Shift down, Win down, **F23** down (all within about 1 ms), released about 190 ms later: the Copilot shortcut |
| Screenshot | **Print Screen** |
| Desktop | Win down, **D** down within 1 to 6 ms, released about 120 ms later |

Print Screen and Win+D are exactly what a real keyboard sends. Remapping them blindly would hijack the keyboard's own
keys. So the app has to know **which device** a key came from.

### Which device sent it? Raw Input, with three surprises

Windows' Raw Input API names the source device of each keyboard event. Measured on this machine:

1. **The device record arrives after the hook.** The raw record for a key appears 0.5 to 7 ms after the low-level hook
   has seen it, and only once the hook has let the key through. A hook cannot wait inside its own callback for the
   record of the key it is judging; it would wait for something that can only appear after it returns.
2. **No device record exists for a key press that triggers a system hotkey.** F23 with Win+Shift (Copilot), Print
   Screen (screenshot tool) and Win+D (show desktop) are all system hotkeys. For those, Windows sends the **release**
   and plain modifier presses (Win, Shift) through Raw Input, but not the press itself. This also affects a normal
   keyboard, not only this mouse.
3. **The mouse's keys are a burst.** The mouse sends Win and the following key within about 1 to 6 ms; a person typing
   the same combination needs far longer.

### The design that follows

The app (`TopButtonHook` with `RawKeyTagger`) identifies the source using only signals that actually exist:

- A background thread owns a hidden window registered for keyboard Raw Input and remembers recent records:
  (time, scan code, press or release, *came from a device that is both a mouse and a keyboard*).
  A "mouse with its own keyboard" is found by comparing the USB vendor/product IDs of the mice and keyboards that
  Windows lists; the one ID that appears in both lists is the mouse.
- **Search (F23) and Desktop (D):** these come with the Win key just before them. The **Win press** has a raw record
  (it is a plain modifier), so the app checks that record: if Win came from the mouse's keyboard, the following key did
  too. If D arrives more than 30 ms after Win, it is a person on a keyboard and is passed through immediately without any
  lookup.
- **Screenshot (Print Screen):** there is nothing at press time to go on and no preceding modifier. The press is held
  back (swallowed). The **release** passes through, which is what makes its raw record appear. A worker thread then
  looks at the release's record: if it came from the mouse, your mapped action runs; otherwise Print Screen is
  **replayed** with `SendInput` so your keyboard's key still does its normal job (the action happens on release instead
  of on press). This is the one visible cost of the design.
- **Start-menu mask.** The Win key has already reached Windows when Search or Desktop is swallowed; releasing Win with
  nothing pressed in between would open the Start menu. The app taps an unassigned key (`VK 0xE8`) while Win is held,
  the same trick other remappers use, so the Start menu stays closed.
- **Waiting for release before sending.** Your mapped action is sent only after Win and Shift are up; otherwise
  `ctrl+c` would arrive as Win+Ctrl+C.
- **Fail open.** If a lookup finds nothing within 50 ms, the key is treated as coming from the keyboard and left
  alone (or replayed). The cost of being wrong is that the original button action happens, never a lost key.

## 3. Verification

- `tests/test_remap.py` (18 checks): combination parsing, swallowing of the five standard buttons with real injected
  presses, the left/right guard, and a real end-to-end copy and paste.
- `tests/test_top_buttons.py` (34 checks): the top-button logic driven event by event with a stand-in for the device
  lookup (no real keyboard hook installed), the device lookup itself, and a scan of this PC's devices.
- `tools/live_top_test.py`: installs the real hooks on the real mouse and only logs what it would send. Three live trials
  were run. The first two exposed the problems described in section 2; the third matched expectations (mouse Screenshot
  presses recognised as the mouse, keyboard Print Screen recognised as not the mouse and replayed, Search and Desktop
  recognised as the mouse).

Not covered by automated tests: Bluetooth connection mode, other mouse models, and long-term use as a Start-with-Windows
background app.

## 4. Other pieces

- **Settings:** `%APPDATA%\MouseRemap\config.json` (`enabled`, `autostart`, and the key combination for each button).
  Missing or unreadable values fall back to defaults.
- **Start with Windows:** one registry value, `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\MouseRemap`, running the
  exe with `--minimized`. It is per user and needs no administrator rights. It is not a Windows service, because a
  service runs in a separate session and cannot send keystrokes into your programs.
- **Single instance:** a named mutex. A second launch signals a named event that makes the running copy show its window.
- **DPI awareness** is switched on so the window is sharp on scaled displays.

## 5. Limits

- Applications running as administrator ignore keys injected by a normal-rights process, and the sign-in screen is a
  different desktop. Run the app as administrator if you need it to apply to elevated programs.
- Buttons handled by the mouse's firmware (DPI, mode switch) are invisible to Windows.
- The three top-button identities (F23, Print Screen, D) were measured on one mouse model.
