from unittest.mock import Mock

import pytest

from soomfon_control.config import Config
from soomfon_control.controller import Controller
from soomfon_control.offline import offline_images


@pytest.mark.parametrize("screensaver_running", [False, True])
def test_shutdown_stops_animation_before_displaying_offline_tiles(screensaver_running):
    controller = Controller(Config(70, 1, 1, {}), Mock())
    deck = Mock()
    controller.configure(deck)
    saver = Mock()
    if screensaver_running:
        controller._screensaver = saver
        deck.set_key_image.side_effect = lambda *args: saver.close.assert_called_once_with(restore_icons=False)
    deck.reset_mock()
    controller.close()
    tiles = offline_images()
    assert len(tiles) == 6
    assert all(tile.size == (60, 60) for tile in tiles)
    assert [call.args[0] for call in deck.set_key_image.call_args_list] == list(range(6))
    for call, tile in zip(deck.set_key_image.call_args_list, tiles):
        assert call.args[1].tobytes() == tile.tobytes()
    controller.on_key(10, True)
    controller.on_encoder(1, 1)
    controller.actions.play_pause.assert_not_called()
    controller.actions.volume.assert_not_called()
    controller.close()
    assert deck.set_key_image.call_count == 6


def test_offline_tiles_reassemble_the_original_panorama():
    from importlib.resources import files
    from PIL import Image
    joined = Image.new("RGB", (180, 120))
    for key, tile in enumerate(offline_images()):
        joined.paste(tile, ((key % 3) * 60, (key // 3) * 60))
    with files("soomfon_control").joinpath("assets/offline.png").open("rb") as stream:
        with Image.open(stream) as source:
            assert joined.tobytes() == source.convert("RGB").tobytes()
