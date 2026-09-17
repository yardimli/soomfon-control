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
| `brightness_knob` | Encoder for device brightness; supplied configuration uses 0 (left small knob). Omit or use null to disable. Must differ from `main_knob`. |
| `brightness_step` | Percentage points per brightness detent, 1–100 (default 5). Brightness is clamped to 0–100 and logged. Changes last for the current run; restart uses `brightness` from JSON. |
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

Button IDs are upstream's zero-based IDs: LCD buttons **0–5**, plain buttons **6–8**, knob presses **9–11** corresponding to encoders **0–2**. The main knob press is reserved for play/pause. The left small knob (encoder 0) adjusts device brightness, clockwise brighter and counterclockwise dimmer. Press the left small knob for previous track and the right small knob (encoder 2) for next track. These send standard Windows media keys. Rotation of the right small knob is unassigned. Verify physical positions on your hardware rather than assuming the numbering matches another revision:

```powershell
.\.venv\Scripts\python -m soomfon_control --monitor
```

This prints events without launching apps, changing volume, or replacing icons. Turn the large knob and put the printed encoder number in `main_knob`. Ctrl+C exits. On this CN002, live input confirmed that the large knob is encoder **1** and its press is key **10**; the supplied configuration uses `main_knob: 1`.

## App pages

The personal `config.json` uses the three plain buttons as page selectors. Each row below lists the initial six display buttons in order 0–5:

| Selector button | Page | Display buttons |
| --- | --- | --- |
| 6 | Daily apps | PhpStorm, Chrome, ChatGPT, WhatsApp, Total Commander, GitHub Desktop |
| 7 | Web and tools | FileZilla, Chrome Remote Desktop, Firefox, Microsoft Edge, Photoshop 2026, PuTTY |
| 8 | System and development | HeidiSQL, S3 Browser, Calculator, Godot Engine, Fan Control, Task Manager |

Startup selects page 1 (button 6) in the configured order. The pages form one shared list of 18 slots. Pressing an app moves it to slot 0 on page 1, shifts all preceding entries back by one across page boundaries, and returns the display to page 1. Icons and actions move together. Page selectors, releases, knob actions, and wake-only presses do not change the ordering. Recency is kept for the current run; restarting restores the JSON order, and the JSON file is never rewritten. Selecting a page replaces both the icons and their app actions. A page-selector press also wakes the screensaver directly into that page; the next screensaver wake restores the most recently selected page. Knob controls and shutdown artwork remain global.

For multiple pages, replace the top-level `buttons` object with `pages`. Each page key is its selector button (`"6"`, `"7"`, or `"8"`), and each page has a `name` and a `buttons` object using display IDs `"0"`–`"5"`. Button entries use the same `label`, `icon`, and `app` fields described above. Paths remain relative to the configuration file. A legacy single-page `buttons` configuration, such as `config.example.json`, still works; do not use both formats in one file.

```json
"pages": {
  "6": {"name": "Daily apps", "buttons": {}},
  "7": {"name": "Web and tools", "buttons": {}},
  "8": {"name": "System and development", "buttons": {}}
}
```

Populate the empty objects with your app entries. To export installed icons for one page, run `tools/export_app_icons.ps1 -Page 7` (optionally select individual display keys with `-Buttons 0,2,3`). Chrome Remote Desktop uses its shortcut's separate `.ico` file because its launcher contains no icon. Its window match includes the title `Chrome Remote Desktop` to distinguish it from normal Chrome windows.

Godot 4.6.1 and Fan Control currently point to their existing folders in `C:/Users/kunfu/Downloads`; update the paths if you move them. Fan Control declares that it requires administrator access: when launching it, Windows shows its normal UAC consent prompt. Already-open windows are still focused first.

## Cards screensaver (selected by default)

Set `screensaver.mode` to `"cards"` or `"faces"`, then restart the controller. Both modes use the configured 60-second idle timeout and support waking, page selection, brightness control, and the offline shutdown picture.

Cards occupy the six display buttons in this order:

| Button | Content |
| --- | --- |
| 0 | Local clock, 24-hour HH:MM, HOME label |
| 1 | Türkiye clock, 24-hour HH:MM, country label |
| 2 | Norway clock, 24-hour HH:MM, country label |
| 3 | Full day of week above local date as MM-DD, aligned and sized like the clocks |
| 4 | Today's weather: conditions, low–high °C, rain probability |
| 5 | Tomorrow's weather: conditions, low–high °C, rain probability |

Clock/date text is white against dark gradients that shift subtly on each minute update. Updates follow wall-clock minute boundaries; unchanged cards are not repeatedly uploaded. Türkiye uses `Europe/Istanbul` and Norway uses `Europe/Oslo`, including daylight-saving changes. `local_timezone: "local"` uses the Windows system timezone; set an IANA timezone such as `"Asia/Taipei"` to override it. The `tzdata` dependency supplies timezone rules on Windows.

```json
"screensaver": {
  "enabled": true,
  "mode": "cards",
  "idle_seconds": 60,
  "images": "assets/faces",
  "frame_seconds": 60,
  "local_timezone": "local",
  "weather": {
    "city": "Xindian",
    "country": "Taiwan",
    "region": "New Taipei City"
  }
}
```

The face image path and frame interval are retained for switching back to `"faces"`; cards mode does not load those images or use the face-change cooldown/fade.

Weather is provided by [Open-Meteo](https://open-meteo.com/) using its [forecast API](https://open-meteo.com/en/docs) and [geocoding API](https://open-meteo.com/en/docs/geocoding-api). Forecast data is fetched at startup and every **three hours** on a background thread, independent of display activity. Three forecast days are cached in memory so today/tomorrow labels can advance at midnight between refreshes. Weather dates follow the selected location's timezone. A weather update refreshes its two cards immediately, without waiting for the next clock minute.

If a fetch fails, existing data stays visible with `STALE`; without usable data the weather cards show `No data`. The controller logs the failure and retries after five minutes while clocks and controls continue working. No API key is needed for the public endpoint. Weather data attribution: Open-Meteo, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

For another city, replace `weather` with e.g. `{"city": "Oslo", "country": "NO"}`. Country accepts an English name or two-letter country code. `region` is optional and can disambiguate a province/city. Alternatively set `{"latitude": 24.96005, "longitude": 121.53892}`; coordinates take priority and bypass geocoding. Both coordinates must be supplied. The default city resolves to Xindian District, New Taipei City, Taiwan. Configuration validation does not require internet access.

## Faces screensaver

The supplied configuration starts a screensaver after **60 seconds without controller input** (PC mouse/keyboard activity does not affect this timer). It shows photorealistic human faces from a collection of 64 expressions. Each button gets a random **30–90 second** timer with the default `frame_seconds: 60`. Whenever one face changes, a shared **10-second cooldown** starts and every other button's deadline is pushed another 10 seconds later (overdue timers restart from now). Only one face changes at a time, with at least 10 seconds between changes after the initial display. These extra delays can reduce the overall rate below six changes per minute. Each change fades the old face to black and then fades in the new face over about one second (12 small image uploads). Fade frames do not extend the cooldown. Waking the display cancels the transition and restores the icons. With the supplied face collection, each new face differs from the faces currently displayed on all six buttons.

```json
"screensaver": {
  "enabled": true,
  "idle_seconds": 60,
  "frame_seconds": 60,
  "images": "assets/faces"
}
```

The first button or knob press wakes the display and restores all app icons **without triggering that press's action**. Press again to launch/focus an app, play/pause, or skip to the previous/next track. Turning a knob also wakes the display; the volume knob still changes volume on that turn. Unassigned controls also reset the timer. Screensaver start/stop messages and all input events appear in the console. Ctrl+C stops the animation and displays the cartoon “STOP / I'M / OFFLINE” panorama across the six buttons before closing. The device retains that picture while the controller is stopped; restarting restores the app icons. This applies to a normal Python shutdown, not an abrupt process kill or power loss.

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

Weather cards use the packaged 240×120 `weather-sprites.png` sheet, cropped into eight 60×60 backgrounds for clear, partly cloudy, cloudy, fog, rain/drizzle/showers, snow, thunderstorms, and icy rain. Unknown conditions retain the plain gradient. All six cards use separated hues with bounded drift, including different tints when today and tomorrow share a weather pattern. See `assets/weather-artwork.md` for generation details.

### Waking the computer display

Every device button/knob press and nonzero knob turn requests that Windows turn the monitor on, resets Windows idle activity, and asks a standard Windows screensaver to close. This runs before the device's own screensaver consumes a wake press, so that press can wake both displays. Releases and screensaver animation updates do not wake Windows. Existing app/media actions and the device's first-press-to-wake behavior remain in effect.

The wake request is one-shot; the controller does not keep the computer awake while idle. It uses [SetThreadExecutionState](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate), a mouse input event, and an asynchronous close request to the standard screensaver window. When Windows reports an active screensaver, the mouse event nudges the pointer toward the virtual desktop center by 12 relative units so custom savers such as Wallpaper Engine can detect actual motion. During normal use it has zero movement. Pointer acceleration can affect the distance. Custom screensavers and secure desktops may handle injected input differently; the console logs when this nudge is requested. Windows sign-in is still required if the session is locked. This works while the controller is running with the monitor in power saving; full sleep/hibernation suspends Python and requires hardware/Windows USB wake support. Physical monitor power switches cannot be controlled this way.

When Windows reports a running screensaver, dismissal also enumerates both the controller desktop and the `Screen-saver` desktop, posting `WM_CLOSE` only to standard screensaver windows or windows belonging to `.scr` processes (including Wallpaper Engine's `wpxscreensaver64.scr`). This request does not depend on the console being foreground. Normal Wallpaper Engine wallpaper processes are excluded. Console warnings distinguish inaccessible desktops, rejected close requests, and cases where no accessible saver window was found. A logged close request means it was posted, not that the saver has confirmed exiting.

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
