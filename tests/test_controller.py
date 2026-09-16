import threading
from unittest.mock import Mock

from soomfon_control.config import App, Button, Config
from soomfon_control.controller import Controller, button_image


def test_knob_and_press_routing():
    actions = Mock()
    controller = Controller(Config(70, 2, 3, {}), actions)
    try:
        controller.on_encoder(0, 1)
        controller.on_encoder(2, -1)
        controller.on_key(11, False)
        controller.on_key(9, True)
        controller.on_key(11, True)
        actions.volume.assert_called_once_with(-3)
        actions.play_pause.assert_called_once_with()
    finally:
        controller.close()


def test_slow_launch_is_coalesced_and_does_not_block_volume():
    entered, release = threading.Event(), threading.Event()
    actions = Mock()
    def launch(app):
        entered.set()
        assert release.wait(3)
    actions.activate.side_effect = launch
    app = App(("example.exe",), "example.exe")
    controller = Controller(Config(70, 0, 1, {0: Button("App", app=app)}), actions)
    try:
        controller.on_key(0, False)
        actions.activate.assert_not_called()
        controller.on_key(0, True)
        assert entered.wait(2)
        controller.on_key(0, True)
        controller.on_encoder(0, 1)
        actions.volume.assert_called_once_with(1)
    finally:
        release.set()
        controller.close()
    actions.activate.assert_called_once_with(app)


def test_failed_media_action_does_not_escape_callback():
    actions = Mock()
    actions.play_pause.side_effect = OSError("unavailable")
    controller = Controller(Config(70, 0, 1, {}), actions)
    try:
        controller.on_key(9, True)
        controller.on_encoder(0, 1)
        actions.volume.assert_called_once()
    finally:
        controller.close()


def test_transparent_icon_is_letterboxed(tmp_path):
    from PIL import Image
    path = tmp_path / "icon.png"
    Image.new("RGBA", (100, 50), (255, 0, 0, 255)).save(path)
    result = button_image(Button("Test", path))
    assert result.size == (60, 60)
    assert result.getpixel((30, 30)) == (255, 0, 0)
    assert result.getpixel((30, 0)) == (23, 35, 55)

