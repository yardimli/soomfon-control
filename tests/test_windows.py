import sys
from unittest.mock import Mock

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows backend")


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
