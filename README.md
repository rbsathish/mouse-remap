# Mouse Button Remap

A small Windows tray app that lets you choose what the extra buttons on your mouse do: turn the side buttons into
**Copy / Paste**, the wheel click into **Undo**, or reassign the top **Search / Screenshot / Desktop** buttons to anything you like.

It works the same whether the mouse is connected by 2.4G receiver, Bluetooth or USB, because it changes what Windows
does with a button press, not how the mouse talks to the PC. No driver, no account, no internet.

> **Status:** version 1.0.0, tested on one mouse: the
> **Amazon Basics Pro Series 2.4G + Bluetooth + USB Triple Mode Wireless Ergonomic Mouse** (9 buttons, black),
> connected through its USB receiver or cable (Windows lists it as USB device `3151:5031`), on Windows 11.
> **Not tested:** Bluetooth mode, other mice, Windows 10. See [Compatibility](#compatibility).
>
> This is an independent project, not affiliated with or endorsed by Amazon.

## What you can remap

| Button | Remappable | Notes |
|---|---|---|
| Left, Right | yes | Guarded: they always click normally while the settings window is open, so you can never lock yourself out |
| Middle (wheel click) | yes | |
| Back, Forward (side buttons) | yes | The usual pair of thumb buttons |
| **Search** (top) | yes | Sent by this mouse as Shift + Win + F23 (the Copilot shortcut) |
| **Screenshot** (top) | yes | Sent as Print Screen |
| **Desktop** (top) | yes | Sent as Win + D |

Each button can be set to a key combination such as `ctrl+c`, `alt+left`, `win+shift+s`, a media key such as
`volume_up`, or **Normal** (leave the button alone). The list has presets (Copy, Paste, Undo, Close tab, Mute, ...), or you
can type your own.

**Cannot be remapped:** buttons handled inside the mouse itself, such as the DPI switch and the 2.4G/Bluetooth
mode button. Windows never sees those.

## Install

1. Download `MouseRemap-<version>-win64.zip` from the **Releases** page and unzip it somewhere permanent, for example
   `C:\Tools\MouseRemap`. (If you move the exe later, tick **Start with Windows** again so it points to the new place.)
2. Run `MouseRemap.exe`. A small window opens and an icon appears in the system tray.
3. Pick an action for each button, then click **Apply and save**. It takes effect immediately.
4. Tick **Start with Windows** (then **Apply and save**) if you want it running every time you sign in. It starts hidden
   in the tray.

Closing the window keeps the app running in the tray. Right-click the tray icon to turn remapping off or quit.
Starting `MouseRemap.exe` a second time simply brings the window back; it never runs two copies.

Settings are stored in `%APPDATA%\MouseRemap\config.json`.

### If Windows or your antivirus warns about it

The exe is not code-signed, so Windows SmartScreen may say "unknown publisher", and some antivirus tools are wary of any
program that watches mouse and keyboard input. The source is in this repository and you can build the exe yourself
(see [Build from source](#build-from-source)). The release zip has a `.sha256` file to check your download.

## Key combination syntax

Join keys with `+`, modifiers first: `ctrl+shift+t`, `alt+left`, `win+d`.

- **Modifiers:** `ctrl`, `alt`, `shift`, `win`
- **Keys:** letters `a`-`z`, digits `0`-`9`, `f1`-`f24`
- **Named keys:** `enter`, `esc`, `tab`, `space`, `backspace`, `delete`, `insert`, `home`, `end`, `pageup`, `pagedown`,
  `left`, `up`, `right`, `down`, `printscreen`
- **Media keys:** `volume_mute`, `volume_up`, `volume_down`, `media_play_pause`, `media_next`, `media_prev`, `media_stop`

Leave the box empty (or choose **Normal**) to keep a button's usual behaviour. A combination that can't be understood
is rejected with a message when you click **Apply and save**.

## Good to know

- **Left/right safety.** Changing a left or right button asks you to confirm. While the settings window is in front they
  click normally; if something goes wrong, run `MouseRemap.exe` again to bring the window back and set the button to
  Normal.
- **Programs run as administrator** don't receive remapped keys unless this app is also run as administrator, and
  nothing applies on the Windows sign-in screen.
- **The Screenshot (top) button is slightly delayed.** To tell the mouse's button apart from your keyboard's Print
  Screen key, the press is held until release. If you remap this button, your keyboard's Print Screen still works, but
  its action happens when you let go of the key rather than when you press it.
- **Your keyboard's shortcuts are left alone.** Win+D and Print Screen from your keyboard behave normally even when you
  remap the mouse's Desktop and Screenshot buttons. [How that works](docs/HOW_IT_WORKS.md).

## Privacy

- No network access, no telemetry, no log files. Nothing you type is recorded.
- Two global input hooks are installed so buttons can be intercepted. Windows calls a hook for every event, so the
  mouse hook sees each button press and the keyboard hook sees each key press. They look at which button or key it is,
  act only on the ones you mapped (for the keyboard hook: F23, Print Screen and Win+D, and only if a top button is
  mapped), and store nothing.
- The only things written to disk are `config.json` and, if you tick *Start with Windows*, one registry value under
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` named `MouseRemap`.

## Uninstall

Untick **Start with Windows** and click **Apply and save**, quit from the tray menu, then delete the folder you unzipped
and `%APPDATA%\MouseRemap`.

## Compatibility

This app was built and tested for one mouse (see the status note at the top). It is **not** a universal mouse driver.

| | Works on | Tested |
|---|---|---|
| Left, right, middle, back, forward | Should work on any mouse whose buttons Windows reports as standard buttons | Only on the mouse above |
| Top **Search / Screenshot / Desktop** buttons | Only mice built like this one: a keyboard hidden inside the mouse that sends exactly **Shift+Win+F23**, **Print Screen** and **Win+D** for those buttons. On any other mouse these three settings do nothing and nothing breaks | Only on the mouse above |
| Extra buttons beyond those (gaming mice with 7 to 12 buttons, DPI or profile buttons) | Not supported. They are usually handled by the maker's driver or inside the mouse | No |
| Connection | USB receiver / cable | Bluetooth mode not tested; it should behave the same because the app acts on what Windows receives |
| Windows | 64-bit Windows 10 and 11 | Windows 11 only. Not macOS or Linux |

**Mouse-maker software** (Logitech Options, Razer Synapse and similar) may already remap buttons itself. If both remap the
same button, they can conflict: turn one off.

To find out what your extra buttons send, run `tools\check_buttons.bat` from a source checkout. It listens for 30
seconds and prints what Windows received, without recording normal typing. If your mouse sends something this app
doesn't know about, that tells you why a button isn't recognised.

## Build from source

Requires Windows 10/11 and Python 3.12.

```bat
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt

test.bat       :: automated tests
run.bat        :: run from source, no console window
build.bat      :: builds dist\MouseRemap.exe and dist\MouseRemap-<version>-win64.zip (+ .sha256)
```

The version number lives in one place, `_version.py`, and is used by the window, the tray tooltip, the exe's file
properties (right-click > Properties > Details) and the zip name.

## Project layout

```
mouse_remap.py        the app: mouse hook, top-button hook, window, tray, settings
_version.py           the version number (single source of truth)
build.bat  test.bat  run.bat
requirements*.txt
tests/                automated tests (no real keyboard hook is installed by them)
tools/                diagnostics: check_buttons.bat, capture_keys.py, live_top_test.py, build helpers
docs/                 HOW_IT_WORKS.md, RELEASING.md, release notes
```

## Documentation

- [How it works](docs/HOW_IT_WORKS.md): the design, and what was measured about how this mouse talks to Windows
- [Releasing](docs/RELEASING.md): how to cut a new version
- [Changelog](CHANGELOG.md)

## License

[MIT](LICENSE): free to use, change and share, provided the copyright notice stays with it.
