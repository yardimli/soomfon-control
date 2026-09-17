"""Windows desktop actions. Imported only when actual desktop control is requested."""
from __future__ import annotations

import logging
import ctypes
from ctypes import wintypes
import subprocess
import time
from dataclasses import dataclass

import psutil
import win32api
import win32con
import win32gui
import win32process

from .config import App

log = logging.getLogger(__name__)
_show_window_async = ctypes.WinDLL("user32", use_last_error=True).ShowWindowAsync
_show_window_async.argtypes = [wintypes.HWND, ctypes.c_int]
_show_window_async.restype = wintypes.BOOL
_set_execution_state = ctypes.WinDLL("kernel32", use_last_error=True).SetThreadExecutionState
_set_execution_state.argtypes = [wintypes.DWORD]
_set_execution_state.restype = wintypes.DWORD


@dataclass(frozen=True)
class Window:
    handle: int
    process: str
    title: str


def windows() -> list[Window]:
    result = []

    def visit(handle, _):
        if not win32gui.IsWindowVisible(handle):
            return
        if win32gui.GetClassName(handle) in {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}:
            return
        title = win32gui.GetWindowText(handle)
        if not title or win32gui.GetWindowLong(handle, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOOLWINDOW:
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(handle)
            process = psutil.Process(pid).name()
        except (psutil.Error, OSError):
            return
        result.append(Window(handle, process, title))

    win32gui.EnumWindows(visit, None)
    return result


def find_window(app: App) -> Window | None:
    # EnumWindows returns front-to-back ordering: prefer the most recently used match.
    return next((w for w in windows() if w.process.casefold() == app.process.casefold()
                 and app.title.casefold() in w.title.casefold()), None)


def tap(key: int):
    win32api.keybd_event(key, 0, 0, 0)
    win32api.keybd_event(key, 0, win32con.KEYEVENTF_KEYUP, 0)


def focus(window: Window):
    handle = window.handle
    if win32gui.IsIconic(handle):
        _show_window_async(handle, win32con.SW_RESTORE)
    if win32gui.GetForegroundWindow() == handle:
        return
    try:
        win32gui.SetForegroundWindow(handle)
    except win32gui.error:
        pass
    if win32gui.GetForegroundWindow() != handle:
        # An Alt press allows foreground activation under Windows' focus rules.
        # Do not synthesize Alt-up if the user is holding Alt themselves.
        alt_held = win32api.GetAsyncKeyState(win32con.VK_MENU) & 0x8000
        if not alt_held:
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        try:
            win32gui.SetForegroundWindow(handle)
        finally:
            if not alt_held:
                win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
    for _ in range(10):
        if win32gui.GetForegroundWindow() == handle:
            return
        time.sleep(0.05)
    raise RuntimeError(f"Windows refused to focus {window.process}: {window.title}")


class WindowsActions:
    def wake_display(self):
        # A one-shot idle reset: never hold the display awake between device inputs.
        if not _set_execution_state(0x00000001 | 0x00000002):  # SYSTEM_REQUIRED | DISPLAY_REQUIRED
            log.warning("Windows display wake request failed: %s", ctypes.get_last_error())
        # Register input without typing, clicking, or moving the pointer.
        win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 0, 0, 0, 0)
        # The power API alone does not stop a screensaver. Ask the standard
        # screensaver window to close asynchronously; never terminate its process.
        saver = win32gui.FindWindow("WindowsScreenSaverClass", None)
        if saver:
            win32gui.PostMessage(saver, win32con.WM_CLOSE, 0, 0)
            log.info("Requested Windows screensaver dismissal")

    def volume(self, delta: int):
        for _ in range(abs(delta)):
            tap(win32con.VK_VOLUME_UP if delta > 0 else win32con.VK_VOLUME_DOWN)

    def play_pause(self):
        tap(win32con.VK_MEDIA_PLAY_PAUSE)

    def previous_track(self):
        tap(win32con.VK_MEDIA_PREV_TRACK)

    def next_track(self):
        tap(win32con.VK_MEDIA_NEXT_TRACK)

    def activate(self, app: App):
        window = find_window(app)
        if window is not None:
            focus(window)
            return
        log.info("Launching %s", app.command[0])
        # An argument list and shell=False preserve paths with spaces and avoid shell parsing.
        try:
            child = subprocess.Popen(app.command, cwd=app.cwd, shell=False)
        except OSError as exc:
            if getattr(exc, "winerror", None) != 740:
                raise
            # Some tools (e.g. Fan Control) declare requireAdministrator.
            # Let Windows show its normal UAC consent prompt on a button-triggered launch.
            result = win32api.ShellExecute(None, "runas", app.command[0],
                                          subprocess.list2cmdline(app.command[1:]),
                                          app.cwd, win32con.SW_SHOWNORMAL)
            if result <= 32:
                raise OSError(f"Windows could not launch {app.command[0]} (code {result})")
            child = None
        deadline = time.monotonic() + app.timeout
        while time.monotonic() < deadline:
            window = find_window(app)
            if window is not None:
                focus(window)
                return
            # Reap short-lived launchers, but keep waiting for the real app's window.
            if child is not None:
                child.poll()
            time.sleep(0.15)
        raise TimeoutError(f"No window for {app.process!r} (title contains {app.title!r}) "
                           f"after {app.timeout}s. Check the process/title using --list-windows.")
