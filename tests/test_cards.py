from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

from PIL import Image

from soomfon_control.cards import CardsRenderer, card_lines, gradient
from soomfon_control.config import ScreensaverConfig
from soomfon_control.screensaver import Screensaver
from soomfon_control.weather import Forecast


def values(lines):
    return [[entry[0] for entry in card] for card in lines]


def test_clock_zones_24h_and_local_date_rollover():
    now = datetime(2026, 9, 16, 17, 45, tzinfo=timezone.utc)
    result = values(card_lines(now, "Asia/Taipei", Forecast()))
    assert result[0] == ["HOME", "01:45"]
    assert result[1] == ["TÜRKIYE", "20:45"]
    assert result[2] == ["NORWAY", "19:45"]
    assert result[3] == ["Thursday", "09-17"]
    winter = values(card_lines(datetime(2026, 1, 1, 12, tzinfo=timezone.utc), "Asia/Taipei", Forecast()))
    assert winter[1][1] == "15:00"
    assert winter[2][1] == "13:00"


def test_weather_selects_dates_not_fixed_array_indices_after_midnight():
    day = {"weather_code": 61, "temperature_2m_min": 20, "temperature_2m_max": 25,
           "precipitation_probability_max": 80}
    forecast = Forecast({"2026-09-17": day, "2026-09-18": {**day, "weather_code": 0}})
    now = datetime(2026, 9, 16, 16, tzinfo=timezone.utc)
    result = values(card_lines(now, "Asia/Taipei", forecast))
    assert result[4] == ["TODAY", "Rain", "20–25°C", "80%"]
    assert result[5][1] == "Clear"
    result = values(card_lines(now + timedelta(days=1), "Asia/Taipei", forecast))
    assert result[4][1] == "Clear"
    assert result[5][1] == "No data"


def test_renderer_updates_on_minute_boundary_or_new_weather_only():
    now = [datetime(2026, 9, 16, 12, 30, 59, tzinfo=timezone.utc)]
    weather = Mock()
    weather.snapshot.return_value = Forecast()
    renderer = CardsRenderer("Asia/Taipei", weather, now=lambda: now[0])
    assert len(renderer.render()) == 6
    assert renderer.render() == []
    now[0] += timedelta(seconds=1)
    assert len(renderer.render()) == 6
    weather.snapshot.return_value = Forecast(revision=1)
    assert [key for key, _ in renderer.render()] == [4, 5]
    assert renderer.render() == []
    assert len(renderer.render(force=True)) == 6


def test_gradients_change_subtly_and_stay_dark():
    first, second = gradient(0, 123456), gradient(0, 123457)
    assert first.size == (60, 60)
    assert first.tobytes() != second.tobytes()
    assert max(first.tobytes()) < 100
    assert max(abs(a-b) for a,b in zip(first.tobytes(),second.tobytes())) <= 3


def test_clock_and_date_layouts_match():
    lines = card_lines(datetime(2026, 9, 17, tzinfo=timezone.utc), "Asia/Taipei", Forecast())
    assert all([entry[1:] for entry in card] == [(13, 10), (37, 19)] for card in lines[:4])


def test_weather_sprites_and_distinct_backgrounds_across_updates():
    from soomfon_control.cards import weather_sprites, weather_sprite_index, weather_background
    tiles = weather_sprites()
    assert len(tiles) == 8
    assert all(tile.size == (60, 60) for tile in tiles)
    assert len({tile.tobytes() for tile in tiles}) == 8
    for code, index in ((0, 0), (1, 1), (2, 1), (3, 2), (45, 3), (55, 4),
                        (65, 4), (82, 4), (75, 5), (86, 5), (99, 6), (67, 7)):
        assert weather_sprite_index(code) == index
    assert weather_sprite_index(None) is None
    assert weather_sprite_index(999) is None
    for minute in range(100, 130):
        backgrounds = [gradient(i, minute) for i in range(6)]
        assert len({image.tobytes() for image in backgrounds}) == 6
        today = weather_background(backgrounds[4], 61)
        tomorrow = weather_background(backgrounds[5], 61)
        assert today.tobytes() != tomorrow.tobytes()
        assert today.tobytes() != backgrounds[4].tobytes()


def test_weather_revision_changes_artwork():
    weather = Mock()
    day = {"weather_code": 0, "temperature_2m_min": 20, "temperature_2m_max": 25,
           "precipitation_probability_max": 50}
    weather.snapshot.return_value = Forecast({"2026-09-17": day})
    renderer = CardsRenderer("Asia/Taipei", weather,
                             now=lambda: datetime(2026, 9, 17, tzinfo=timezone.utc))
    first = dict(renderer.render())[4]
    weather.snapshot.return_value = Forecast({"2026-09-17": {**day, "weather_code": 95}}, revision=1)
    updated = dict(renderer.render())
    assert set(updated) == {4, 5}
    assert updated[4].tobytes() != first.tobytes()


def test_cards_mode_idle_wake_and_reentry_without_network():
    now = [0.0]
    deck = Mock()
    icons = [Image.new("RGB", (60, 60), "white") for _ in range(6)]
    saver = Screensaver(deck, ScreensaverConfig((), idle_seconds=60, mode="cards"), icons, clock=lambda: now[0])
    # tick never starts the weather thread or performs an HTTP request.
    now[0] = 59
    saver.tick()
    deck.set_key_image.assert_not_called()
    now[0] = 60
    saver.tick()
    assert deck.set_key_image.call_count == 6
    saver.tick()
    assert deck.set_key_image.call_count == 6
    assert saver.activity()
    saver.tick()
    assert [call.args[1] for call in deck.set_key_image.call_args_list[-6:]] == icons
    now[0] = 120
    saver.tick()
    assert deck.set_key_image.call_count == 18
    saver.close()
