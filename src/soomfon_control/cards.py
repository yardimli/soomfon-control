"""Tiny, readable clock/date/weather cards rendered locally at 60x60."""
from __future__ import annotations

import colorsys
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import math
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont


@lru_cache(maxsize=24)
def font(size):
    for path in (Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    return ImageFont.load_default()


def gradient(index, minute):
    # Slow bounded hue drift; every update is slightly different, never bright behind white text.
    hue = (0.57 + index / 6 + 0.025 * math.sin(minute / 12)) % 1
    image = Image.new("RGB", (60, 60))
    pixels = image.load()
    for y in range(60):
        for x in range(60):
            value = 0.18 + 0.20 * (x + y) / 118
            pixels[x, y] = tuple(round(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.70, value))
    return image


def text(image, value, y, size):
    draw = ImageDraw.Draw(image)
    while size > 6 and draw.textbbox((0, 0), value, font=font(size))[2] > 56:
        size -= 1
    draw.text((30, y), value, fill="white", font=font(size), anchor="mm",
              stroke_width=1, stroke_fill="#101521")


@lru_cache(maxsize=1)
def weather_sprites():
    with Image.open(Path(__file__).parent / "assets/weather-sprites.png") as sheet:
        return tuple(sheet.convert("RGB").crop((col * 60, row * 60, (col + 1) * 60, (row + 1) * 60))
                     for row in range(2) for col in range(4))


def weather_sprite_index(code):
    return {"Clear": 0, "Fair": 1, "Pt cloudy": 1, "Cloudy": 2, "Fog": 3,
            "Drizzle": 4, "Rain": 4, "Showers": 4, "Snow": 5,
            "T-storm": 6, "Icy rain": 7}.get(condition(code))


def weather_background(image, code):
    index = weather_sprite_index(code)
    if index is None:
        return image
    # Retain the card's distinct gradient even when both days have identical weather.
    return Image.blend(image, weather_sprites()[index], 0.45)


def rain_footer(image, value):
    draw = ImageDraw.Draw(image)
    label_font = font(8)
    width = draw.textlength(value, font=label_font)
    left = round((60 - width - 10) / 2)
    # A tiny code-drawn drop avoids reliance on emoji fonts on Windows.
    draw.polygon([(left + 3, 48), (left, 53), (left + 6, 53)], fill="#78ceff")
    draw.ellipse((left, 51, left + 6, 57), fill="#78ceff")
    draw.point((left + 2, 53), fill="white")
    draw.text((left + 10, 53), value, font=label_font, fill="white", anchor="lm",
              stroke_width=1, stroke_fill="#101521")


def condition(code):
    if code is None: return "Unknown"
    if code == 0: return "Clear"
    if code == 1: return "Fair"
    if code == 2: return "Pt cloudy"
    if code == 3: return "Cloudy"
    if code in (45, 48): return "Fog"
    if code in (51, 53, 55): return "Drizzle"
    if code in (56, 57, 66, 67): return "Icy rain"
    if code in (61, 63, 65): return "Rain"
    if code in (71, 73, 75, 77, 85, 86): return "Snow"
    if code in (80, 81, 82): return "Showers"
    if code in (95, 96, 99): return "T-storm"
    return "Unknown"


def card_lines(now, local_timezone, forecast):
    local = now.astimezone() if local_timezone == "local" else now.astimezone(ZoneInfo(local_timezone))
    lines = [
        [("HOME", 13, 10), (local.strftime("%H:%M"), 37, 19)],
        [("TÜRKIYE", 13, 10), (now.astimezone(ZoneInfo("Europe/Istanbul")).strftime("%H:%M"), 37, 19)],
        [("NORWAY", 13, 10), (now.astimezone(ZoneInfo("Europe/Oslo")).strftime("%H:%M"), 37, 19)],
        [(local.strftime("%A"), 13, 10), (local.strftime("%m-%d"), 37, 19)],
    ]
    weather_date = now.astimezone(ZoneInfo(forecast.timezone)).date()
    for offset, label in enumerate(("TODAY", "TOMORROW")):
        day = forecast.days.get((weather_date + timedelta(days=offset)).isoformat())
        if day is None:
            lines.append([(label, 10, 9), ("No data" if forecast.error or forecast.days else "Loading", 32, 10)])
            continue
        low, high = day["temperature_2m_min"], day["temperature_2m_max"]
        temps = f"{low:.0f}–{high:.0f}°C" if low is not None and high is not None else "--°C"
        rain = day["precipitation_probability_max"]
        footer = "STALE" if forecast.stale else (f"{rain:.0f}%" if rain is not None else "--%")
        lines.append([(label, 8, 9), (condition(day["weather_code"]), 23, 9),
                      (temps, 38, 12), (footer, 53, 8)])
    return lines


class CardsRenderer:
    def __init__(self, local_timezone, weather, now=lambda: datetime.now(timezone.utc)):
        self.local_timezone = local_timezone
        self.weather = weather
        self.now = now
        self._stamp = None

    def render(self, *, force=False):
        now = self.now()
        snapshot = self.weather.snapshot()
        minute = int(now.timestamp() // 60)
        stamp = (minute, snapshot.revision)
        if not force and stamp == self._stamp:
            return []
        changed_minute = self._stamp is None or self._stamp[0] != minute
        self._stamp = stamp
        result = []
        for index, lines in enumerate(card_lines(now, self.local_timezone, snapshot)):
            if not force and not changed_minute and index < 4:
                continue
            image = gradient(index, minute)
            if index >= 4:
                weather_date = now.astimezone(ZoneInfo(snapshot.timezone)).date()
                day = snapshot.days.get((weather_date + timedelta(days=index - 4)).isoformat())
                if day:
                    image = weather_background(image, day["weather_code"])
            for value, y, size in lines:
                if index >= 4 and y == 53 and value != "STALE":
                    rain_footer(image, value)
                else:
                    text(image, value, y, size)
            result.append((index, image))
        return result
