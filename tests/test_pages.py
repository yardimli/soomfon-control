import json
from unittest.mock import Mock

import pytest

from soomfon_control.config import App, Button, Config, ConfigError, Page, load_config
from soomfon_control.controller import Controller


def test_page_switch_changes_all_icons_and_the_launched_app():
    apps = [App((f"app{i}.exe",), f"app{i}.exe") for i in range(3)]
    pages = {6+i: Page(f"Page {i+1}", {0: Button(f"App{i}", app=app)}) for i, app in enumerate(apps)}
    controller = Controller(Config(70, 1, 1, pages[6].buttons, pages=pages), Mock())
    deck = Mock()
    controller.configure(deck)
    # Keep launch execution synchronous so page/action assertions are deterministic.
    controller._pool.shutdown()
    controller._pool = Mock()
    controller._pool.submit.side_effect = lambda fn, *args: fn(*args)
    try:
        controller.on_key(0, True)
        for selector in (7, 8, 6):
            deck.reset_mock()
            controller.on_key(selector, True)
            assert controller._page == selector
            assert [call.args[0] for call in deck.set_key_image.call_args_list] == list(range(6))
            selected = controller._buttons[0].app
            controller.on_key(0, True)
            controller.actions.activate.assert_called_with(selected)
            assert controller._page == 6
        assert controller.actions.activate.call_count == 4
        controller.on_key(8, False)
        assert controller._page == 6
    finally:
        controller.close()


def test_page_selection_wakes_screensaver_in_one_press():
    pages = {6: Page("First", {}), 7: Page("Second", {0: Button("Second")})}
    controller = Controller(Config(70, 1, 1, {}, pages=pages), Mock())
    controller.configure(Mock())
    controller._screensaver = Mock()
    try:
        controller.on_key(7, True)
        assert controller._page == 7
        controller._screensaver.set_icons.assert_called_once_with(controller._page_icons[7])
        controller.actions.activate.assert_not_called()
    finally:
        controller.close()


def test_recent_apps_move_across_page_boundaries_and_reset_on_restart():
    buttons = [Button(f"App {i}", app=App((f"app{i}.exe",), f"app{i}.exe")) for i in range(18)]
    pages = {6 + p: Page(f"Page {p+1}", {i: buttons[p*6+i] for i in range(6)}) for p in range(3)}
    config = Config(70, 1, 1, pages[6].buttons, pages=pages)
    controller = Controller(config, Mock())
    controller.configure(Mock())
    controller._pool.shutdown()
    controller._pool = Mock()
    controller._pool.submit.side_effect = lambda fn, *args: fn(*args)
    expected = list(buttons)
    try:
        for selector, key in ((7, 3), (8, 5), (6, 2), (6, 0)):
            controller.on_key(selector, True)
            index = (selector - 6) * 6 + key
            selected = expected.pop(index)
            expected.insert(0, selected)
            controller.on_key(key, True)
            assert controller._page == 6
            assert controller._ordered_buttons == expected
            controller.actions.activate.assert_called_with(selected.app)
            for page in range(3):
                assert list(controller._runtime_pages[6+page].values()) == expected[page*6:page*6+6]
                assert controller._page_icons[6+page] == [controller._icon_cache[id(b)] for b in expected[page*6:page*6+6]]
        # Releases and page selection do not change recency.
        controller.on_key(1, False)
        controller.on_key(8, True)
        assert controller._ordered_buttons == expected
        assert [b for p in pages.values() for b in p.buttons.values()] == buttons
        fresh = Controller(config, Mock())
        assert fresh._ordered_buttons == buttons
        fresh.close()
    finally:
        controller.close()


def test_recent_app_updates_screensaver_restore_icons():
    first = Button("First", app=App(("first.exe",), "first.exe"))
    second = Button("Second", app=App(("second.exe",), "second.exe"))
    pages = {6: Page("First", {0: first}), 7: Page("Second", {0: second})}
    controller = Controller(Config(70, 1, 1, pages[6].buttons, pages=pages), Mock())
    controller.configure(Mock())
    saver = Mock()
    saver.activity.return_value = False
    controller._screensaver = saver
    try:
        controller.on_key(7, True)
        controller.on_key(0, True)
        assert controller._page == 6
        assert controller._buttons[0] == second
        saver.set_icons.assert_called_with(controller._page_icons[6])
        # A wake-only press must not reorder apps or launch anything.
        saver.activity.return_value = True
        controller.on_key(1, True)
        assert controller._buttons[0] == second
    finally:
        controller.close()


def test_page_config_loads_and_resolves_icons(tmp_path):
    from PIL import Image
    Image.new("RGB", (60, 60)).save(tmp_path / "app.png")
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"pages": {"6": {"name": "First", "buttons": {"0": {"icon": "app.png"}}},
                                          "7": {"name": "Second", "buttons": {}}}}))
    config = load_config(path)
    assert set(config.pages) == {6, 7}
    assert config.buttons[0].icon == tmp_path / "app.png"


@pytest.mark.parametrize("data", [
    {"pages": {}}, {"pages": []}, {"pages": {"5": {}}},
    {"pages": {"6": {}}, "buttons": {}},
    {"pages": {"6": {"buttons": {"6": {"label": "invalid"}}}}},
])
def test_invalid_pages(tmp_path, data):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ConfigError):
        load_config(path)
