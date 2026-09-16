import json

import pytest

from soomfon_control.config import ConfigError, load_config


def write(tmp_path, data):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_paths_are_relative_to_config(tmp_path):
    from PIL import Image
    Image.new("RGB", (16, 16)).save(tmp_path / "icon.png")
    config = load_config(write(tmp_path, {"buttons": {"0": {
        "icon": "icon.png", "app": {"command": ["./app.exe", "a b"],
                                     "process": "app.exe", "cwd": "."}}}}))
    button = config.buttons[0]
    assert button.icon == tmp_path / "icon.png"
    assert button.app.command == (str(tmp_path / "app.exe"), "a b")
    assert button.app.cwd == str(tmp_path)


@pytest.mark.parametrize("data", [
    {"main_knob": 3}, {"main_knob": True}, {"volume_steps": 0}, {"brightness": 101},
    {"buttons": []}, {"buttons": {"9": {}}}, {"buttons": {"01": {}}},
    {"buttons": {"0": {"app": {"command": "notepad.exe", "process": "notepad.exe"}}}},
    {"buttons": {"0": {"app": {"command": ["a"], "process": "a", "timeout": float("nan")}}}},
    {"buttons": {"0": {"icon": "missing.png"}}}, {"brigthness": 40},
])
def test_rejects_bad_config(tmp_path, data):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, data))


def test_rejects_duplicate_keys(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"buttons": {"0": {}, "0": {}}}')
    with pytest.raises(ConfigError, match="Duplicate"):
        load_config(path)

