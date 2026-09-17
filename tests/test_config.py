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


@pytest.mark.parametrize("spec", [
    {"enabled": "yes"}, {"enabled": False, "idle_seconds": 0},
    {"enabled": False, "frame_seconds": float("nan")},
    {"images": "missing"}, {"enabled": True},
])
def test_invalid_screensaver_config(tmp_path, spec):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"screensaver": spec}))


def test_disabled_screensaver_needs_no_assets(tmp_path):
    config = load_config(write(tmp_path, {"screensaver": {"enabled": False}}))
    assert config.screensaver is None


@pytest.mark.parametrize("data", [
    {"main_knob": 0, "brightness_knob": 0}, {"brightness_knob": 3},
    {"brightness_step": 0}, {"brightness_step": True},
])
def test_invalid_brightness_controls(tmp_path, data):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, data))


def test_screensaver_loads_images_relative_to_json(tmp_path):
    from PIL import Image
    faces = tmp_path / "faces"
    faces.mkdir()
    for i in range(6):
        Image.new("RGB", (60, 60)).save(faces / f"{i}.png")
    config = load_config(write(tmp_path, {"screensaver": {"images": "faces"}}))
    assert len(config.screensaver.images) == 6
    assert config.screensaver.idle_seconds == 10
    (faces / "0.png").write_bytes(b"invalid image")
    with pytest.raises(ConfigError, match="Invalid screensaver image"):
        load_config(tmp_path / "config.json")


def test_cards_mode_does_not_require_face_assets(tmp_path):
    config = load_config(write(tmp_path, {"screensaver": {"mode": "cards"}}))
    assert config.screensaver.images == ()
    assert config.screensaver.weather.city == "Xindian"
    assert config.screensaver.weather.region == "New Taipei City"
    config = load_config(write(tmp_path, {"screensaver": {"mode": "cards", "weather": {"city": "Oslo", "country": "NO"}}}))
    assert config.screensaver.weather.region == ""


@pytest.mark.parametrize("spec", [
    {"mode": "bad"}, {"mode": "cards", "local_timezone": "Not/AZone"},
    {"mode": "cards", "weather": {"latitude": 10}},
    {"mode": "cards", "weather": {"latitude": 91, "longitude": 0}},
    {"mode": "cards", "weather": {"latitude": False, "longitude": 0}},
    {"mode": "cards", "weather": {"latitude": 0, "longitude": float("nan")}},
])
def test_invalid_cards_settings(tmp_path, spec):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"screensaver": spec}))
