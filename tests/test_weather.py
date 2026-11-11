from backend.weather_service import WeatherService


def test_current_precipitation_probability_uses_nearest_hour():
    hourly = {
        "time": ["2026-11-10T00:00", "2026-11-10T20:00", "2026-11-10T21:00"],
        "precipitation_probability": [0, 25, 70],
    }

    probability = WeatherService._current_probability(hourly, "2026-11-10T20:40")

    assert probability == 70


def test_current_precipitation_probability_handles_missing_values():
    assert WeatherService._current_probability({"time": [], "precipitation_probability": []}, None) is None
