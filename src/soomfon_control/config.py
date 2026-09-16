from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
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
class Config:
    brightness: int
    main_knob: int
    volume_steps: int
    buttons: dict[int, Button]


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


def load_config(path: Path) -> Config:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique)
    except (OSError, ValueError) as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc
    raw = _object(raw, "config", {"brightness", "main_knob", "volume_steps", "buttons"})
    brightness = _integer(raw.get("brightness", 70), "brightness", 0, 100)
    knob = _integer(raw.get("main_knob", 0), "main_knob", 0, 2)
    steps = _integer(raw.get("volume_steps", 1), "volume_steps", 1, 10)
    entries = raw.get("buttons", {})
    if not isinstance(entries, dict):
        raise ConfigError("buttons must be an object keyed by button number (0-8)")
    buttons = {}
    base = path.resolve().parent
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
    return Config(brightness, knob, steps, buttons)

