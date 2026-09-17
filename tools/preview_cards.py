"""Render a deterministic card preview without network access or device writes."""
from datetime import datetime, timezone
from unittest.mock import Mock

from PIL import Image

from soomfon_control.cards import CardsRenderer
from soomfon_control.weather import Forecast


if __name__ == "__main__":
    day = {"weather_code": 0, "temperature_2m_min": 24, "temperature_2m_max": 30,
           "precipitation_probability_max": 10}
    weather = Mock()
    weather.snapshot.return_value = Forecast({"2026-09-17": day,
        "2026-09-18": {**day, "weather_code": 95, "precipitation_probability_max": 85}})
    renderer = CardsRenderer("Asia/Taipei", weather,
                             now=lambda: datetime(2026, 9, 17, 9, 42, tzinfo=timezone.utc))
    preview = Image.new("RGB", (188, 124), "#080b10")
    for index, card in renderer.render():
        preview.paste(card, ((index % 3) * 64, (index // 3) * 64))
    preview.resize((752, 496), Image.Resampling.NEAREST).save("assets/cards-preview.png")
