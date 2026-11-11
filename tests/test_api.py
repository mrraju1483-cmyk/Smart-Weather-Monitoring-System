import json
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import create_app
from backend.serial_service import VALID_READING_TIMEOUT_SECONDS, validate_reading


@pytest.fixture
def client(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE_PATH": str(tmp_path / "api-test.db"),
        "SERIAL_PORT": "COM3",
        "CORS_ENABLED": False,
    })
    return app.test_client(), app


def test_dashboard_pages_render(client):
    test_client, _app = client
    for path in ("/", "/history", "/analytics", "/settings"):
        assert test_client.get(path).status_code == 200


def test_serial_json_validation_accepts_expected_data_and_dht_errors():
    valid = validate_reading(json.loads(
        '{"temperature":29.0,"humidity":65.0,"air_quality":350,"rain_value":850}'
    ))
    assert valid == {"temperature": 29.0, "humidity": 65.0, "air_quality": 350, "rain_value": 850}
    assert validate_reading({
        "temperature": None, "humidity": None, "air_quality": 350, "rain_value": 850,
    })["temperature"] is None


@pytest.mark.parametrize("payload", [
    {"temperature": 200, "humidity": 65, "air_quality": 350, "rain_value": 850},
    {"temperature": 20, "humidity": 101, "air_quality": 350, "rain_value": 850},
    {"temperature": 20, "humidity": 50, "air_quality": 1024, "rain_value": 850},
    {"temperature": 20, "humidity": 50, "air_quality": 350},
])
def test_serial_json_validation_rejects_out_of_range_or_missing_fields(payload):
    with pytest.raises(ValueError):
        validate_reading(payload)


def test_live_history_csv_alerts_and_status_endpoints(client):
    test_client, app = client
    service = app.extensions["serial_service"]
    assert service.accept_line(
        '{"temperature":29.0,"humidity":65.0,"air_quality":350,"rain_value":850}'
    )

    live = test_client.get("/api/live").get_json()
    history = test_client.get("/api/history?range=24h").get_json()
    search = test_client.get("/api/history?search=350").get_json()
    csv_response = test_client.get("/api/history?format=csv")
    alerts = test_client.get("/api/alerts").get_json()
    status = test_client.get("/api/status").get_json()

    assert live["success"] and live["data"]["reading"]["air_quality"] == 350
    assert history["success"] and history["data"]["total"] == 1
    assert search["success"] and search["data"]["total"] == 1
    assert csv_response.status_code == 200
    assert "text/csv" in csv_response.content_type
    assert "air_quality" in csv_response.get_data(as_text=True)
    assert alerts["success"]
    assert status["success"] and status["data"]["database"]["connected"]


def test_serial_status_requires_a_recent_valid_sensor_line(client):
    test_client, app = client
    service = app.extensions["serial_service"]
    service._port_open = True

    waiting = test_client.get("/api/status").get_json()["data"]["arduino"]
    assert waiting["connected"] is False
    assert waiting["state"] == "connecting"

    assert service.accept_line(
        '{"temperature":29.0,"humidity":65.0,"air_quality":350,"rain_value":850}'
    )
    connected = test_client.get("/api/live").get_json()["data"]["arduino"]
    assert connected["connected"] is True
    assert connected["state"] == "connected"

    service.last_message_at = (
        datetime.now(timezone.utc) - timedelta(seconds=VALID_READING_TIMEOUT_SECONDS + 1)
    ).isoformat()
    stale_live = test_client.get("/api/live").get_json()["data"]["arduino"]
    stale_status = test_client.get("/api/status").get_json()["data"]["arduino"]
    assert stale_live["connected"] is False
    assert stale_live["state"] == "disconnected"
    assert stale_status["state"] == stale_live["state"]


def test_invalid_serial_data_does_not_mark_arduino_connected(client):
    test_client, app = client
    service = app.extensions["serial_service"]
    service._port_open = True

    assert service.accept_line("booting...") is False
    status = test_client.get("/api/status").get_json()["data"]["arduino"]

    assert status["connected"] is False
    assert status["state"] == "connecting"
    assert status["last_error"]


def test_serial_service_retries_after_port_error_and_accepts_reconnected_data(client, monkeypatch):
    _test_client, app = client
    app.config["SERIAL_PORT"] = "COM_TEST"
    app.config["SERIAL_RETRY_SECONDS"] = 0.01
    service = app.extensions["serial_service"]
    attempts = 0
    line = b'{"temperature":29.0,"humidity":65.0,"air_quality":350,"rain_value":850}\n'

    class FakeSerialException(Exception):
        pass

    class FakeConnection:
        def __init__(self, close_after_line):
            self.is_open = True
            self.close_after_line = close_after_line
            self.pending = True

        def readline(self):
            if self.pending:
                self.pending = False
                if self.close_after_line:
                    self.is_open = False
                return line
            threading.Event().wait(0.01)
            return b""

        def close(self):
            self.is_open = False

    def fake_serial(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise FakeSerialException("simulated COM3 disconnect")
        return FakeConnection(close_after_line=attempts == 2)

    monkeypatch.setitem(
        sys.modules,
        "serial",
        SimpleNamespace(Serial=fake_serial, SerialException=FakeSerialException),
    )
    monkeypatch.setattr("backend.serial_service.time.sleep", lambda _seconds: None)
    service.start()
    try:
        deadline = time.monotonic() + 2
        while attempts < 3 and time.monotonic() < deadline:
            threading.Event().wait(0.01)

        assert attempts >= 3
        assert service.status()["state"] == "connected"
    finally:
        service.stop()


def test_settings_are_saved_and_validated(client):
    test_client, _app = client
    saved = test_client.post("/api/settings", json={
        "location": {"name": "Test City", "latitude": 10, "longitude": 20},
        "thresholds": {
            "temperature_high": 34, "humidity_high": 80,
            "air_quality_high": 700, "rain_wet_below": 500,
        },
    })
    settings = test_client.get("/api/settings").get_json()
    invalid = test_client.post("/api/settings", json={
        "location": {"name": "", "latitude": 100, "longitude": 20},
    })

    assert saved.status_code == 200
    assert settings["data"]["location"]["name"] == "Test City"
    assert settings["data"]["thresholds"]["temperature_high"] == 34
    assert invalid.status_code == 400


def test_weather_and_forecast_routes_return_cached_service_data(client):
    test_client, app = client
    weather_data = {
        "success": True, "status": "online", "location": {"name": "Test City"},
        "current": {"temperature": 24, "condition": "Clear sky"},
        "hourly": [{"time": "2026-01-01T10:00", "temperature": 24}],
        "daily": [{"date": "2026-01-01", "temperature_max": 28}],
    }
    app.extensions["weather_service"].fetch = lambda location: weather_data

    weather = test_client.get("/api/weather").get_json()
    forecast = test_client.get("/api/forecast").get_json()

    assert weather["success"] and weather["data"]["current"]["temperature"] == 24
    assert forecast["success"] and len(forecast["data"]["daily"]) == 1


def test_invalid_history_filters_return_client_error(client):
    test_client, _app = client
    assert test_client.get("/api/history?range=2h").status_code == 400
    assert test_client.get("/api/history?start=not-a-date").status_code == 400


def test_analysis_reports_insufficient_dataset_without_training(client):
    test_client, _app = client
    result = test_client.get("/api/analysis").get_json()
    assert result["success"]
    assert result["data"]["status"] == "insufficient_data"
    assert result["data"]["dataset_size"] == 0
    assert "not reliable weather forecasts" in result["data"]["disclaimer"]


def test_in_memory_database_persists_across_api_requests():
    app = create_app({"TESTING": True, "DATABASE_PATH": ":memory:", "CORS_ENABLED": False})
    client = app.test_client()

    saved = client.post("/api/settings", json={
        "location": {"name": "Memory City", "latitude": 10, "longitude": 20},
    })
    loaded = client.get("/api/settings").get_json()

    assert saved.status_code == 200
    assert loaded["data"]["location"]["name"] == "Memory City"
