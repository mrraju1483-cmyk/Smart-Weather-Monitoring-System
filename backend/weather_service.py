from datetime import datetime, timezone

import requests

DEFAULT_LOCATION = {"name": "Visakhapatnam, Andhra Pradesh, India", "latitude": 17.6868, "longitude": 83.2185}
WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
    55: "Dense drizzle", 56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain", 66: "Light freezing rain",
    67: "Heavy freezing rain", 71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    77: "Snow grains", 80: "Rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers", 95: "Thunderstorm",
    96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}


class WeatherService:
    def __init__(self, timeout=8):
        self.timeout = timeout

    def fetch(self, location=DEFAULT_LOCATION):
        params = {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
            "hourly": "temperature_2m,precipitation_probability,precipitation,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,precipitation_probability_max,precipitation_sum",
            "forecast_days": 7,
            "timezone": "auto",
        }
        try:
            response = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=self.timeout)
            response.raise_for_status()
            raw = response.json()
            current = raw.get("current", {})
            hourly = raw.get("hourly", {})
            daily = raw.get("daily", {})
            code = current.get("weather_code")
            return {
                "success": True,
                "status": "online",
                "location": location,
                "current": {
                    "temperature": current.get("temperature_2m"),
                    "humidity": current.get("relative_humidity_2m"),
                    "apparent_temperature": current.get("apparent_temperature"),
                    "condition": WEATHER_CODES.get(code, "Unknown conditions"),
                    "weather_code": code,
                    "wind_speed": current.get("wind_speed_10m"),
                    "precipitation": current.get("precipitation"),
                    "precipitation_probability": self._current_probability(hourly, current.get("time")),
                    "time": current.get("time"),
                },
                "hourly": self._hourly_forecast(hourly),
                "daily": self._daily_forecast(daily),
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        except (requests.RequestException, ValueError, TypeError) as error:
            return {
                "success": False,
                "status": "offline",
                "location": location,
                "error": str(error),
                "message": "Weather data is temporarily unavailable. Check your internet connection and try again.",
                "current": None,
                "hourly": [],
                "daily": [],
            }

    @staticmethod
    def _current_probability(hourly, current_time):
        times = hourly.get("time", [])
        probabilities = hourly.get("precipitation_probability", [])
        if not current_time or not times:
            return None
        try:
            current = datetime.fromisoformat(current_time.replace("Z", "+00:00"))
            candidates = [
                (abs((datetime.fromisoformat(value.replace("Z", "+00:00")) - current).total_seconds()), index)
                for index, value in enumerate(times)
                if index < len(probabilities)
            ]
            return probabilities[min(candidates)[1]] if candidates else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _hourly_forecast(hourly):
        times = hourly.get("time", [])
        return [
            {
                "time": times[index],
                "temperature": hourly.get("temperature_2m", [None] * len(times))[index],
                "precipitation_probability": hourly.get("precipitation_probability", [None] * len(times))[index],
                "precipitation": hourly.get("precipitation", [None] * len(times))[index],
                "condition": WEATHER_CODES.get(hourly.get("weather_code", [None] * len(times))[index], "Unknown"),
            }
            for index in range(min(24, len(times)))
        ]

    @staticmethod
    def _daily_forecast(daily):
        times = daily.get("time", [])
        return [
            {
                "date": times[index],
                "condition": WEATHER_CODES.get(daily.get("weather_code", [None] * len(times))[index], "Unknown"),
                "temperature_max": daily.get("temperature_2m_max", [None] * len(times))[index],
                "temperature_min": daily.get("temperature_2m_min", [None] * len(times))[index],
                "precipitation_probability": daily.get("precipitation_probability_max", [None] * len(times))[index],
                "precipitation": daily.get("precipitation_sum", [None] * len(times))[index],
            }
            for index in range(min(7, len(times)))
        ]
