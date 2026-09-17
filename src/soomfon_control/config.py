from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class App:
    command: tuple[str, ...]
    process: str
    title: str = ""
    cwd: str | None = None
    timeout: float = 15


@dataclass(frozen=True)
class Button:
    label: str
    icon: Path | None = None
    app: App | None = None


@dataclass(frozen=True)
class WeatherConfig:
    city: str = "Xindian"
    country: str = "Taiwan"
    region: str = "New Taipei City"
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True)
class ScreensaverConfig:
    images: tuple[Path, ...]
    idle_seconds: float = 10
    frame_seconds: float = 60
    mode: str = "faces"
    local_timezone: str = "local"
    weather: WeatherConfig = field(default_factory=WeatherConfig)


@dataclass(frozen=True)
class Page:
    name: str
    buttons: dict[int, Button]


@dataclass(frozen=True)
class Config:
    brightness: int
    main_knob: int
    volume_steps: int
    buttons: dict[int, Button]
    screensaver: ScreensaverConfig | None = None
    brightness_knob: int | None = None
    brightness_step: int = 5
    pages: dict[int, Page] = field(default_factory=dict)


def _object(value, name, allowed):
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be an object")
    unknown = value.keys() - allowed
    if unknown:
        raise ConfigError(f"Unknown {name} fields: {', '.join(sorted(unknown))}")
    return value


def _text(value, name, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ConfigError(f"{name} must be a {'non-empty ' if not empty else ''}string")
    return value


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ConfigError(f"{name} must be an integer from {low} to {high}")
    return value


def _path(value, base):
    path = Path(os.path.expandvars(os.path.expanduser(value)))
    return (base / path).resolve()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _buttons(entries, base, *, display_only=False):
    if not isinstance(entries, dict):
        raise ConfigError("buttons must be an object keyed by button number (0-8)")
    buttons = {}
    for key, value in entries.items():
        if key not in {str(i) for i in range(9)}:
            raise ConfigError(f"Invalid button number: {key}; expected 0-8")
        entry = _object(value, f"button {key}", {"label", "icon", "app"})
        label = _text(entry.get("label", key), f"button {key} label", empty=True)
        icon = None
        if "icon" in entry:
            if int(key) > 5:
                raise ConfigError(f"Button {key} has no display; icons are only supported on 0-5")
            icon = _path(_text(entry["icon"], "icon"), base)
            if not icon.is_file():
                raise ConfigError(f"Icon does not exist: {icon}")
            from PIL import Image
            try:
                with Image.open(icon) as image:
                    image.verify()
            except (OSError, ValueError) as exc:
                raise ConfigError(f"Invalid icon {icon}: {exc}") from exc
        app = None
        if "app" in entry:
            spec = _object(entry["app"], f"button {key} app",
                           {"command", "process", "title", "cwd", "timeout"})
            command = spec.get("command")
            if not isinstance(command, list) or not command:
                raise ConfigError(f"Button {key}: app.command must be a non-empty array")
            args = [os.path.expandvars(_text(arg, "command argument", empty=i > 0))
                    for i, arg in enumerate(command)]
            args[0] = os.path.expanduser(args[0])
            if "/" in args[0] or "\\" in args[0]:
                args[0] = str(_path(args[0], base))
            process = _text(spec.get("process"), "app.process")
            if "/" in process or "\\" in process:
                raise ConfigError("app.process must be a filename, e.g. notepad.exe")
            title = _text(spec.get("title", ""), "app.title", empty=True)
            cwd = str(_path(_text(spec["cwd"], "app.cwd"), base)) if "cwd" in spec else None
            if cwd and not Path(cwd).is_dir():
                raise ConfigError(f"Working directory does not exist: {cwd}")
            timeout = spec.get("timeout", 15)
            if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 120:
                raise ConfigError("app.timeout must be a number greater than 0 and at most 120")
            app = App(tuple(args), process, title, cwd, timeout)
        buttons[int(key)] = Button(label, icon, app)
    if display_only and any(key > 5 for key in buttons):
        raise ConfigError("Page buttons must be display keys 0-5; keys 6-8 select pages")
    return buttons


def load_config(path: Path) -> Config:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique)
    except (OSError, ValueError) as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc
    raw = _object(raw, "config", {"brightness", "main_knob", "volume_steps", "buttons", "screensaver",
                                  "brightness_knob", "brightness_step", "pages"})
    brightness = _integer(raw.get("brightness", 70), "brightness", 0, 100)
    knob = _integer(raw.get("main_knob", 0), "main_knob", 0, 2)
    steps = _integer(raw.get("volume_steps", 1), "volume_steps", 1, 10)
    brightness_knob = raw.get("brightness_knob")
    if brightness_knob is not None:
        brightness_knob = _integer(brightness_knob, "brightness_knob", 0, 2)
        if brightness_knob == knob:
            raise ConfigError("brightness_knob and main_knob must be different")
    brightness_step = _integer(raw.get("brightness_step", 5), "brightness_step", 1, 100)
    base = path.resolve().parent
    pages = {}
    if "pages" in raw:
        if "buttons" in raw:
            raise ConfigError("Use either pages or buttons, not both")
        page_specs = raw["pages"]
        if not isinstance(page_specs, dict) or not page_specs:
            raise ConfigError("pages must be a non-empty object keyed by 6, 7, or 8")
        for key, value in page_specs.items():
            if key not in {"6", "7", "8"}:
                raise ConfigError("Page selector must be 6, 7, or 8")
            spec = _object(value, f"page {key}", {"name", "buttons"})
            pages[int(key)] = Page(_text(spec.get("name", f"Page {int(key)-5}"), "page name"),
                                   _buttons(spec.get("buttons", {}), base, display_only=True))
        buttons = pages[min(pages)].buttons
    else:
        buttons = _buttons(raw.get("buttons", {}), base)
    screensaver = None
    if "screensaver" in raw:
        spec = _object(raw["screensaver"], "screensaver",
                       {"enabled", "images", "idle_seconds", "frame_seconds", "mode", "local_timezone", "weather"})
        enabled = spec.get("enabled", True)
        if type(enabled) is not bool:
            raise ConfigError("screensaver.enabled must be true or false")
        mode = spec.get("mode", "faces")
        if mode not in ("faces", "cards"):
            raise ConfigError("screensaver.mode must be faces or cards")
        local_zone = _text(spec.get("local_timezone", "local"), "local_timezone")
        if local_zone != "local":
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
            try:
                ZoneInfo(local_zone)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ConfigError(f"Unknown local_timezone: {local_zone}") from exc
        weather_spec = _object(spec.get("weather", {}), "weather",
                               {"city", "country", "region", "latitude", "longitude"})
        if ("latitude" in weather_spec) != ("longitude" in weather_spec):
            raise ConfigError("Set both weather.latitude and weather.longitude")
        for coordinate, limit in (("latitude", 90), ("longitude", 180)):
            if coordinate in weather_spec:
                value = weather_spec[coordinate]
                if type(value) not in (float, int) or not math.isfinite(value) or not -limit <= value <= limit:
                    raise ConfigError(f"weather.{coordinate} must be between {-limit} and {limit}")
        weather_values = dict(weather_spec)
        for name in ("city", "country", "region"):
            if name in weather_spec:
                _text(weather_spec[name], f"weather.{name}", empty=name == "region")
        if "city" in weather_spec or "country" in weather_spec:
            weather_values.setdefault("region", "")
        weather = WeatherConfig(**weather_values)
        intervals = {}
        for name, default, minimum in (("idle_seconds", 10, 1), ("frame_seconds", 60, 0.5)):
            value = spec.get(name, default)
            if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= 3600:
                raise ConfigError(f"screensaver.{name} must be a number from {minimum} to 3600")
            intervals[name] = value
        images = ()
        if enabled and mode == "faces":
            directory = _path(_text(spec.get("images"), "screensaver.images"), base)
            if not directory.is_dir():
                raise ConfigError(f"Screensaver image directory does not exist: {directory}")
            images = tuple(sorted(p for p in directory.iterdir()
                                  if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}))
            if len(images) < 6:
                raise ConfigError("Screensaver needs at least six images")
            from PIL import Image
            for image_path in images:
                try:
                    with Image.open(image_path) as image:
                        image.verify()
                except (OSError, ValueError) as exc:
                    raise ConfigError(f"Invalid screensaver image {image_path}: {exc}") from exc
        if enabled:
            screensaver = ScreensaverConfig(images, **intervals, mode=mode,
                                            local_timezone=local_zone, weather=weather)
    return Config(brightness, knob, steps, buttons, screensaver, brightness_knob, brightness_step, pages)
