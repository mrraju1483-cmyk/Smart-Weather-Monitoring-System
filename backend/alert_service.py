from datetime import datetime, timedelta, timezone

from backend import database


DEFAULT_THRESHOLDS = {
    "temperature_high": 35.0,
    "humidity_high": 80.0,
    "air_quality_high": 700,
    "rain_wet_below": 500,
}


def evaluate_reading(database_path, reading):
    settings = database.get_settings(database_path)
    thresholds = {**DEFAULT_THRESHOLDS, **settings.get("thresholds", {})}
    checks = [
        ("high_temperature", "High temperature", reading.get("temperature"),
         lambda value: value is not None and value >= thresholds["temperature_high"],
         f"Temperature is at or above {thresholds['temperature_high']} °C."),
        ("high_humidity", "High humidity", reading.get("humidity"),
         lambda value: value is not None and value >= thresholds["humidity_high"],
         f"Humidity is at or above {thresholds['humidity_high']}%."),
        ("high_air_quality_raw", "High MQ-135 raw reading", reading.get("air_quality"),
         lambda value: value is not None and value >= thresholds["air_quality_high"],
         f"MQ-135 raw reading is at or above {thresholds['air_quality_high']}. This is not a certified AQI/PPM value."),
        ("rain_detected", "Water detected by rain sensor", reading.get("rain_value"),
         lambda value: value is not None and value <= thresholds["rain_wet_below"],
         f"Rain sensor reading is at or below {thresholds['rain_wet_below']}; the sensor may be wet."),
    ]
    now = datetime.now(timezone.utc)
    existing = database.list_alerts(database_path, limit=200)
    recent_by_type = {}
    for alert in existing:
        if alert["alert_type"] not in recent_by_type:
            recent_by_type[alert["alert_type"]] = alert["timestamp"]

    created = []
    for alert_type, label, value, condition, message in checks:
        if not condition(value):
            continue
        previous = recent_by_type.get(alert_type)
        if previous:
            try:
                if now - datetime.fromisoformat(previous) < timedelta(minutes=10):
                    continue
            except ValueError:
                pass
        database.add_alert(database_path, alert_type, message, value, now.isoformat(timespec="seconds"))
        created.append({"alert_type": alert_type, "message": message, "sensor_value": value})
    return created
