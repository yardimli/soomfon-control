from unittest.mock import Mock

import pytest

from soomfon_control.config import WeatherConfig
from soomfon_control.weather import WeatherService, resolve_location, parse_forecast, REFRESH_SECONDS, RETRY_SECONDS


def response():
    return {"timezone": "Asia/Taipei", "daily": {"time": ["2026-09-17", "2026-09-18", "2026-09-19"],
            "weather_code": [0, 3, 61], "temperature_2m_min": [20, 21, None],
            "temperature_2m_max": [30, 31, None], "precipitation_probability_max": [0, 20, None]}}


def test_coordinates_bypass_geocoder():
    request = Mock()
    assert resolve_location(WeatherConfig(latitude=0, longitude=0), request) == (0, 0)
    request.assert_not_called()


def test_geocoding_country_and_region_disambiguation():
    request = Mock(return_value={"results": [
        {"name": "Xindian", "country": "Taiwan", "country_code": "TW", "admin2": "Yilan County", "latitude": 24, "longitude": 122},
        {"name": "Xindian District", "country": "Taiwan", "country_code": "TW", "admin2": "New Taipei City", "latitude": 24.96005, "longitude": 121.53892},
    ]})
    assert resolve_location(WeatherConfig(), request) == (24.96005, 121.53892)
    with pytest.raises(ValueError, match="not found"):
        resolve_location(WeatherConfig(country="Norway"), request)


def test_refresh_interval_and_failed_refresh_preserves_marked_data():
    request = Mock(side_effect=[response(), OSError("offline"), response()])
    service = WeatherService(WeatherConfig(latitude=24.96, longitude=121.54), request)
    assert service.refresh() == REFRESH_SECONDS == 10800
    first = service.snapshot()
    assert len(first.days) == 3
    assert not first.stale
    assert service.refresh() == RETRY_SECONDS == 300
    assert service.snapshot().days == first.days
    assert service.snapshot().stale
    assert service.snapshot().error == "offline"
    assert service.refresh() == REFRESH_SECONDS
    assert not service.snapshot().stale
    assert service.snapshot().revision == 3
    assert request.call_args.args[1]["forecast_days"] == 3


def test_malformed_forecast_is_not_accepted():
    data = response()
    data["daily"]["temperature_2m_max"][0] = float("nan")
    with pytest.raises(ValueError):
        parse_forecast(data)
