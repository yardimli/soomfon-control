import sys
from unittest.mock import Mock

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows backend")


@pytest.mark.parametrize("saver", [0, 123])
@pytest.mark.parametrize("power_result", [0, 0x80000000])
def test_wake_display_resets_idle_and_closes_only_screensaver(monkeypatch, saver, power_result):
    from soomfon_control import windows as backend
    power, mouse, post = Mock(return_value=power_result), Mock(), Mock()
    find = Mock(return_value=saver)
    monkeypatch.setattr(backend, "_set_execution_state", power)
    monkeypatch.setattr(backend.win32api, "mouse_event", mouse)
    monkeypatch.setattr(backend.win32gui, "FindWindow", find)
    monkeypatch.setattr(backend.win32gui, "PostMessage", post)
    backend.WindowsActions().wake_display()
    power.assert_called_once_with(3)  # No ES_CONTINUOUS: future idle sleep remains enabled.
    mouse.assert_called_once_with(backend.win32con.MOUSEEVENTF_MOVE, 0, 0, 0, 0)
    find.assert_called_once_with("WindowsScreenSaverClass", None)
    if saver:
        post.assert_called_once_with(saver, backend.win32con.WM_CLOSE, 0, 0)
    else:
        post.assert_not_called()


def test_track_actions_send_media_keys(monkeypatch):
    from soomfon_control import windows as backend
    key_event = Mock()
    monkeypatch.setattr(backend.win32api, "keybd_event", key_event)
    actions = backend.WindowsActions()
    actions.previous_track()
    actions.next_track()
    assert [call.args for call in key_event.call_args_list] == [
        (backend.win32con.VK_MEDIA_PREV_TRACK, 0, 0, 0),
        (backend.win32con.VK_MEDIA_PREV_TRACK, 0, backend.win32con.KEYEVENTF_KEYUP, 0),
        (backend.win32con.VK_MEDIA_NEXT_TRACK, 0, 0, 0),
        (backend.win32con.VK_MEDIA_NEXT_TRACK, 0, backend.win32con.KEYEVENTF_KEYUP, 0),
    ]


def test_existing_app_is_focused_without_launch(monkeypatch):
    from soomfon_control import windows as backend
    from soomfon_control.config import App
    window = backend.Window(123, "App.exe", "My document")
    monkeypatch.setattr(backend, "windows", lambda: [window])
    focus, launch = Mock(), Mock()
    monkeypatch.setattr(backend, "focus", focus)
    monkeypatch.setattr(backend.subprocess, "Popen", launch)
    backend.WindowsActions().activate(App(("App.exe",), "app.EXE", "DOCUMENT"))
    focus.assert_called_once_with(window)
    launch.assert_not_called()


def test_launch_waits_for_real_app_window(monkeypatch):
    from soomfon_control import windows as backend
    from soomfon_control.config import App
    window = backend.Window(123, "App.exe", "Ready")
    monkeypatch.setattr(backend, "find_window", Mock(side_effect=[None, None, window]))
    focus, launch = Mock(), Mock()
    monkeypatch.setattr(backend, "focus", focus)
    monkeypatch.setattr(backend.subprocess, "Popen", launch)
    monkeypatch.setattr(backend.time, "sleep", lambda _: None)
    app = App(("C:/Program Files/App.exe", "some file"), "App.exe")
    backend.WindowsActions().activate(app)
    launch.assert_called_once_with(app.command, cwd=None, shell=False)
    focus.assert_called_once_with(window)


def test_launch_timeout_is_reported(monkeypatch):
    from soomfon_control import windows as backend
    from soomfon_control.config import App
    monkeypatch.setattr(backend, "find_window", lambda _: None)
    monkeypatch.setattr(backend.subprocess, "Popen", Mock())
    monkeypatch.setattr(backend.time, "monotonic", Mock(side_effect=[0, 2]))
    with pytest.raises(TimeoutError, match="No window"):
        backend.WindowsActions().activate(App(("app.exe",), "app.exe", timeout=1))


def test_focus_restores_minimized_window(monkeypatch):
    from soomfon_control import windows as backend
    monkeypatch.setattr(backend.win32gui, "IsIconic", lambda _: True)
    restore = Mock()
    monkeypatch.setattr(backend, "_show_window_async", restore)
    monkeypatch.setattr(backend.win32gui, "GetForegroundWindow", lambda: 123)
    backend.focus(backend.Window(123, "app.exe", "App"))
    restore.assert_called_once_with(123, backend.win32con.SW_RESTORE)


def test_focus_fallback_releases_alt_even_on_failure(monkeypatch):
    from soomfon_control import windows as backend
    monkeypatch.setattr(backend.win32gui, "IsIconic", lambda _: False)
    monkeypatch.setattr(backend.win32gui, "GetForegroundWindow", lambda: 999)
    monkeypatch.setattr(backend.win32gui, "SetForegroundWindow", Mock(side_effect=backend.win32gui.error("denied")))
    monkeypatch.setattr(backend.win32api, "GetAsyncKeyState", lambda _: 0)
    key_event = Mock()
    monkeypatch.setattr(backend.win32api, "keybd_event", key_event)
    with pytest.raises(backend.win32gui.error):
        backend.focus(backend.Window(123, "app.exe", "App"))
    assert key_event.call_args_list[-1].args == (backend.win32con.VK_MENU, 0, backend.win32con.KEYEVENTF_KEYUP, 0)


def test_required_elevation_uses_windows_consent_flow(monkeypatch):
    from soomfon_control import windows as backend
    from soomfon_control.config import App
    error = OSError("elevation required")
    error.winerror = 740
    monkeypatch.setattr(backend.subprocess, "Popen", Mock(side_effect=error))
    execute = Mock(return_value=42)
    monkeypatch.setattr(backend.win32api, "ShellExecute", execute)
    window = backend.Window(1, "FanControl.exe", "Fan Control")
    monkeypatch.setattr(backend, "find_window", Mock(side_effect=[None, None, window]))
    monkeypatch.setattr(backend, "focus", Mock())
    monkeypatch.setattr(backend.time, "sleep", lambda _: None)
    app = App(("C:/Tools/FanControl.exe", "argument with spaces"), "FanControl.exe", cwd="C:/Tools")
    backend.WindowsActions().activate(app)
    execute.assert_called_once_with(None, "runas", app.command[0], '"argument with spaces"',
                                    app.cwd, backend.win32con.SW_SHOWNORMAL)
    backend.focus.assert_called_once_with(window)
