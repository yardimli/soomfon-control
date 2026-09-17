"""Open-Meteo forecasts fetched on a separate thread, never in the HID callbacks."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import math
import threading
import urllib.parse
import urllib.request

from .config import WeatherConfig

log = logging.getLogger(__name__)
REFRESH_SECONDS = 3 * 60 * 60
RETRY_SECONDS = 5 * 60


def request_json(url, params):
    request = urllib.request.Request(url + "?" + urllib.parse.urlencode(params),
                                     headers={"User-Agent": "soomfon-control/0.1"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def resolve_location(config, request=request_json):
    if config.latitude is not None:
        return config.latitude, config.longitude
    params = {"name": config.city, "count": 100, "language": "en", "format": "json"}
    if len(config.country) == 2:
        params["countryCode"] = config.country.upper()
    else:
        params["name"] = f"{config.city}, {config.country}"
    results = request("https://geocoding-api.open-meteo.com/v1/search", params).get("results", [])
    matches = [r for r in results if config.country.casefold() in
               (r.get("country", "").casefold(), r.get("country_code", "").casefold())]
    if config.region:
        matches = [r for r in matches if any(config.region.casefold() == r.get(f"admin{i}", "").casefold()
                                           for i in range(1, 5))]
    if not matches:
        raise ValueError(f"Weather location not found: {config.city}, {config.region}, {config.country}")
    place = matches[0]
    log.info("Weather location: %s (%s, %s)", place["name"], place["latitude"], place["longitude"])
    return place["latitude"], place["longitude"]


@dataclass(frozen=True)
class Forecast:
    days: dict = field(default_factory=dict)
    timezone: str = "Asia/Taipei"
    stale: bool = False
    error: str | None = None
    revision: int = 0


def parse_forecast(data):
    from datetime import date
    from zoneinfo import ZoneInfo
    zone = data["timezone"]
    ZoneInfo(zone)
    daily = data["daily"]
    days = {}
    for i, day in enumerate(daily["time"]):
        date.fromisoformat(day)
        values = {}
        for key in ("weather_code", "temperature_2m_min", "temperature_2m_max", "precipitation_probability_max"):
            value = daily[key][i]
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                raise ValueError(f"Invalid forecast value: {key}")
            values[key] = value
        days[day] = values
    if not days:
        raise ValueError("Empty weather forecast")
    return Forecast(days, zone)


class WeatherService:
    def __init__(self, config: WeatherConfig, request=request_json):
        self.config = config
        self.request = request
        self._coordinates = None
        self._snapshot = Forecast()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def snapshot(self):
        with self._lock:
            return self._snapshot

    def refresh(self):
        try:
            if self._coordinates is None:
                self._coordinates = resolve_location(self.config, self.request)
            latitude, longitude = self._coordinates
            data = self.request("https://api.open-meteo.com/v1/forecast", {
                "latitude": latitude, "longitude": longitude, "timezone": "auto", "forecast_days": 3,
                "temperature_unit": "celsius",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            })
            forecast = parse_forecast(data)
            with self._lock:
                self._snapshot = Forecast(forecast.days, forecast.timezone, revision=self._snapshot.revision + 1)
            log.info("Open-Meteo weather refreshed; next refresh in 3 hours")
            return REFRESH_SECONDS
        except Exception as exc:
            log.warning("Weather refresh failed: %s; retrying in 5 minutes", exc)
            with self._lock:
                old = self._snapshot
                self._snapshot = Forecast(old.days, old.timezone, True, str(exc), old.revision + 1)
            return RETRY_SECONDS

    def start(self):
        def run():
            while not self._stop.is_set():
                if self._stop.wait(self.refresh()):
                    break
        self._thread = threading.Thread(target=run, name="weather", daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread:
            # An outstanding HTTP request can finish on the daemon; it never touches the device.
            self._thread.join(timeout=0.2)
