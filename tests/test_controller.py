import threading
from unittest.mock import Mock

from soomfon_control.config import App, Button, Config
from soomfon_control.controller import Controller, button_image


def test_device_input_wakes_windows_even_when_device_screensaver_consumes_press():
    actions = Mock()
    controller = Controller(Config(70, 1, 1, {}), actions)
    controller._screensaver = Mock()
    try:
        for key in (0, 6, 9, 10, 11):
            controller.on_key(key, True)
            controller.on_key(key, False)
        assert actions.wake_display.call_count == 5
        actions.activate.assert_not_called()
        actions.play_pause.assert_not_called()
        controller.on_encoder(2, 1)
        assert actions.wake_display.call_count == 6
        controller.on_encoder(2, 0)
        assert actions.wake_display.call_count == 6
        controller.close()
        controller.on_key(0, True)
        controller.on_encoder(2, 1)
        assert actions.wake_display.call_count == 6
    finally:
        controller.close()


def test_failed_wake_does_not_block_media_action():
    actions = Mock()
    actions.wake_display.side_effect = OSError("unavailable")
    controller = Controller(Config(70, 1, 1, {}), actions)
    try:
        controller.on_key(10, True)
        actions.play_pause.assert_called_once_with()
        controller.on_encoder(1, 1)
        actions.volume.assert_called_once_with(1)
    finally:
        controller.close()


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


def test_small_knob_presses_skip_tracks_and_releases_do_nothing():
    actions = Mock()
    controller = Controller(Config(70, 1, 1, {}), actions)
    try:
        for key in (9, 10, 11):
            controller.on_key(key, False)
        assert not actions.mock_calls
        controller.on_key(9, True)
        controller.on_key(11, True)
        controller.on_key(10, True)
        actions.previous_track.assert_called_once_with()
        actions.next_track.assert_called_once_with()
        actions.play_pause.assert_called_once_with()
        actions.activate.assert_not_called()
    finally:
        controller.close()


def test_small_knob_press_only_wakes_screensaver_before_skipping():
    actions = Mock()
    controller = Controller(Config(70, 1, 1, {}), actions)
    controller._screensaver = Mock()
    try:
        for key, action in ((9, actions.previous_track), (11, actions.next_track)):
            controller._screensaver.activity.return_value = True
            controller.on_key(key, True)
            action.assert_not_called()
            controller._screensaver.activity.return_value = False
            controller.on_key(key, True)
            action.assert_called_once_with()
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


def test_brightness_knob_clamps_and_does_not_adjust_volume():
    actions, deck = Mock(), Mock()
    controller = Controller(Config(70, 1, 1, {}, brightness_knob=0), actions)
    controller.configure(deck)
    deck.reset_mock()
    try:
        controller.on_encoder(0, 1)
        controller.on_encoder(0, -1)
        controller.on_encoder(0, 100)
        controller.on_encoder(0, 1)
        controller.on_encoder(0, -100)
        controller.on_encoder(0, -1)
        assert [call.args[0] for call in deck.set_brightness.call_args_list] == [75, 70, 100, 0]
        actions.volume.assert_not_called()
        controller.on_encoder(1, 1)
        actions.volume.assert_called_once_with(1)
    finally:
        controller.close()


def test_failed_brightness_write_keeps_previous_level():
    deck = Mock()
    controller = Controller(Config(70, 1, 1, {}, brightness_knob=0), Mock())
    controller.configure(deck)
    deck.set_brightness.side_effect = [OSError("USB error"), None]
    try:
        controller.on_encoder(0, 1)
        controller.on_encoder(0, 1)
        assert controller._brightness == 75
    finally:
        controller.close()
