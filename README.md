# SOOMFON Control

A small, JSON-configured **Windows 10/11** controller for the SOOMFON CN002 / Stream Controller SE. Uses [DeastinY/soomfon](https://github.com/DeastinY/soomfon) for the device protocol, pinned to a specific upstream commit.

- Turn the main knob to change system volume; press it to send media play/pause.
- Press an assigned button to restore and focus an existing program window, or launch the program and wait for its window before focusing it.
- Set PNG/JPEG/etc. button icons, with text fallbacks when no icon is supplied.
- Configure all nine buttons and choose which of the three knobs is the main knob.

## Setup (PowerShell)

Requires Python 3.10+ and the CN002 device supported by upstream (USB `1500:3001`). Close the manufacturer's controller software before running this controller so it does not compete for the device.

```powershell
cd F:\GitHub\soomfon-control
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python tools\install_hidapi.py
Copy-Item config.example.json config.json
.\.venv\Scripts\python -m soomfon_control --check
.\.venv\Scripts\python -m soomfon_control
```

The HIDAPI helper downloads the official libusb HIDAPI 0.15.0 Windows release, verifies a pinned SHA-256 checksum, and extracts only the matching x86/x64 DLL into `native/`. No system installation or administrator access is needed. Use the `hid` dependency supplied by upstream; the similarly named `hidapi` Python package has a different API and should not be installed in this virtual environment.

For a manual DLL installation or a non-editable package install, set an absolute path before running:

```powershell
$env:SOOMFON_HIDAPI_DLL = 'C:\path\to\hidapi.dll'
```

Keep the controller running. Ctrl+C stops it. Restart after editing JSON. `config.json` is ignored by Git so personal program paths stay local. You can keep multiple configurations and choose one with `--config profiles\work.json`.

During normal operation the console logs every button press/release and knob turn/press/release received from the driver, including unassigned controls. Each line includes a timestamp and the button or knob number; turns include the signed delta. Actions continue to run as usual.

## Configuration

The example starts with Notepad and File Explorer, plus four unassigned display buttons. Replace their actions with your programs. Example button entry inside `buttons`:

```json
"0": {
  "label": "Editor",
  "icon": "icons/editor.png",
  "app": {
    "command": ["%LOCALAPPDATA%/Programs/Microsoft VS Code/Code.exe", "F:/GitHub/soomfon-control"],
    "process": "Code.exe",
    "title": "soomfon-control",
    "timeout": 20
  }
}
```

Use your actual installation path. `icon` and `app` are optional; without an app the button has no action. The icon replaces the text label on the display. App icons are fitted inside 58×58 pixels without stretching, centered on the 60×60 display with a one-pixel background border on every side; transparent pixels use a dark background. Omit `icon` to use a short text label. Unconfigured displays are cleared at startup.

| Field | Meaning |
| --- | --- |
| `brightness` | Display brightness, integer 0–100 (default 70). |
| `main_knob` | Encoder index 0, 1, or 2 (default 0; confirm with `--monitor`). |
| `volume_steps` | Number of Windows volume-key taps per detent, 1–10 (default 1). These are native Windows increments, not an exact percentage. |
| `buttons` | Object keyed by string IDs `"0"`–`"8"`. |
| `label` | Fallback display text, best kept to 8 characters per line / 24 total. |
| `icon` | Optional image path, only for display buttons 0–5. |
| `app.command` | Required argument array, with the executable first. Paths containing spaces stay a single argument. No shell interpretation. Use an executable, not a shell command or `.cmd` shim. |
| `app.process` | Required actual window-owning process filename, e.g. `chrome.exe`. Matching is case-insensitive. |
| `app.title` | Optional case-insensitive window title substring. When provided, both process and title must match. |
| `app.cwd` | Optional existing working directory for the launched app. |
| `app.timeout` | Seconds to wait for a matching window after launch, greater than 0 and at most 120 (default 15). |

Relative icon paths, executable paths containing a slash, and working directories resolve from the JSON file's directory. Bare executable names resolve using Windows' normal executable search. Environment variables such as `%LOCALAPPDATA%` expand in command arguments and paths. JSON requires doubled backslashes (`C:\\Apps\\app.exe`); forward slashes work for file paths too.

Button IDs are upstream's zero-based IDs: LCD buttons **0–5**, plain buttons **6–8**, knob presses **9–11** corresponding to encoders **0–2**. The main knob press is reserved for play/pause. Other knobs are left unassigned. Verify physical positions on your hardware rather than assuming the numbering matches another revision:

```powershell
.\.venv\Scripts\python -m soomfon_control --monitor
```

This prints events without launching apps, changing volume, or replacing icons. Turn the large knob and put the printed encoder number in `main_knob`. Ctrl+C exits. On this CN002, live input confirmed that the large knob is encoder **1** and its press is key **10**; the supplied configuration uses `main_knob: 1`.

## Faces screensaver

The supplied configuration starts a screensaver after **10 seconds without controller input** (PC mouse/keyboard activity does not affect this timer). It shows photorealistic human faces from a collection of 64 expressions. Each button gets a random **30–90 second** timer with the default `frame_seconds: 60`. Whenever one face changes, a shared **10-second cooldown** starts and every other button's deadline is pushed another 10 seconds later (overdue timers restart from now). Only one face changes at a time, with at least 10 seconds between changes after the initial display. These extra delays can reduce the overall rate below six changes per minute. Each change fades the old face to black and then fades in the new face over about one second (12 small image uploads). Fade frames do not extend the cooldown. Waking the display cancels the transition and restores the icons. With the supplied face collection, each new face differs from the faces currently displayed on all six buttons.

```json
"screensaver": {
  "enabled": true,
  "idle_seconds": 10,
  "frame_seconds": 60,
  "images": "assets/faces"
}
```

The first button or knob press wakes the display and restores all app icons **without triggering that press's action**. Press again to launch/focus an app or play/pause. Turning a knob also wakes the display; the volume knob still changes volume on that turn. Unassigned controls also reset the timer. Screensaver start/stop messages and all input events appear in the console. Ctrl+C stops the animation and displays the cartoon “STOP / I'M / OFFLINE” panorama across the six buttons before closing. The device retains that picture while the controller is stopped; restarting restores the app icons. This applies to a normal Python shutdown, not an abrupt process kill or power loss.

Set `enabled` to `false` to disable the screensaver. `images` is a directory relative to the JSON file and must contain at least six valid PNG/JPEG/WebP files. Restart after changing the configuration. Display updates use their own worker so USB image uploads do not block input callbacks.

The artwork was generated with the built-in imagegen tool as one **8×8 sprite sheet**, then cropped into **64 separate 60×60 PNGs** using `tools/crop_faces.py`. The source is `assets/faces-sheet.png`; generation details and the prompt are in `assets/faces-artwork.md`. To re-crop a replacement sheet, run `.\.venv\Scripts\python tools\crop_faces.py`.

## Finding the right app window

Open the target program, then run:

```powershell
.\.venv\Scripts\python -m soomfon_control --list-windows
```

Use the printed process filename and optionally a stable part of the window title. If several windows match, the frontmost match wins. Matching an existing window does not rerun the command or change its open document. A running background/tray process without a matching visible window is treated as needing a launch; the program decides whether that launch reopens its existing instance. Programs that hand off to another process need the final window's process name.

Windows restricts foreground activation. The controller restores minimized windows, requests focus, and retries using an Alt-key activation fallback. It logs a failure if Windows still refuses (for example an elevated target or a different desktop). It does not send literal Alt+Tab, which could select the wrong application. Play/pause is a standard Windows media key, so the media app/session that Windows selects receives it.

Launches run on a worker so volume and play/pause remain responsive while a program starts. Repeated presses of the same action are ignored while it is pending. Errors are logged and the controller continues. Shutdown may wait for an in-progress launch timeout. Reconnect a disconnected device and restart the controller; automatic USB reconnection and automatic JSON reload are not implemented.

## Development / verification

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m soomfon_control --config config.example.json --check
```

Tests cover configuration errors, path handling, icon fitting, event routing, pending launch suppression, and focus-or-launch behavior with mocked desktop actions. They do not press media keys, launch programs, or require a connected device. Real hardware icon orientation, knob numbering, and desktop focus behavior should be checked on your device with your configured apps.

### Fade overhead

Only the changing button receives animation frames. Using all 64 supplied faces, a local benchmark measured roughly 49 KB of HID reports and 1.2 ms of CPU for blending, JPEG encoding and packet framing per transition. At six transitions per minute this is about 4.8 KiB/s average report traffic. These measurements exclude actual USB I/O, USB bus framing and OS scheduling; physical smoothness depends on the device. The display worker sends frames incrementally, so wake input can cancel a fade immediately instead of waiting for the whole animation.

Run `.\.venv\Scripts\python tools\benchmark_fade.py` to repeat the estimate without opening or writing to the device.

### Offline shutdown screen

The packaged `src/soomfon_control/assets/offline.png` is a single **180x120** cartoon panorama (about 33 KB), cut at runtime into six equal 60x60 tiles in button order 0–5 (three columns, two rows). It appears on normal controller shutdown, whether or not the screensaver was active. Artwork generation details are in `assets/offline-artwork.md`.
