import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from flask import Flask, jsonify, make_response, render_template, request
from flask_cors import CORS

from backend import alert_service, database, ml_service
from backend.serial_service import SerialService
from backend.weather_service import DEFAULT_LOCATION, WeatherService
from config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
DEFAULTS = {
    "location": DEFAULT_LOCATION,
    "thresholds": alert_service.DEFAULT_THRESHOLDS,
}
ALLOWED_RANGES = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}
SETTING_KEYS = {"location", "thresholds"}


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    if app.config["DATABASE_PATH"] == ":memory:":
        app.config["DATABASE_PATH"] = f"file:environment_{uuid4().hex}?mode=memory&cache=shared"
    database.init_db(app.config["DATABASE_PATH"])
    current_settings = database.get_settings(app.config["DATABASE_PATH"])
    for key, value in DEFAULTS.items():
        if key not in current_settings:
            database.save_settings(app.config["DATABASE_PATH"], {key: value})
    app.extensions["serial_service"] = SerialService(app)
    app.extensions["weather_service"] = WeatherService(app.config["WEATHER_TIMEOUT_SECONDS"])
    app.extensions["weather_cache"] = {"updated": 0.0, "data": None, "lock": threading.Lock()}
    if app.config.get("CORS_ENABLED", False):
        CORS(app, resources={r"/api/*": {"origins": "*"}})

    def response(data=None, error=None, status=200):
        return jsonify({"success": error is None, "data": data, "error": error}), status

    def location_settings():
        settings = database.get_settings(app.config["DATABASE_PATH"])
        return {**DEFAULTS["location"], **settings.get("location", {})}

    def load_weather(force=False):
        cache = app.extensions["weather_cache"]
        with cache["lock"]:
            if not force and cache["data"] and time.monotonic() - cache["updated"] < 300:
                return cache["data"]
            result = app.extensions["weather_service"].fetch(location_settings())
            cache.update(updated=time.monotonic(), data=result)
            return result

    @app.get("/")
    def dashboard():
        return render_template("index.html", page="dashboard")

    @app.get("/history")
    def history_page():
        return render_template("history.html", page="history")

    @app.get("/analytics")
    def analytics_page():
        return render_template("analytics.html", page="analytics")

    @app.get("/settings")
    def settings_page():
        return render_template("settings.html", page="settings")

    @app.get("/api/live")
    def live():
        reading = database.get_latest_reading(app.config["DATABASE_PATH"])
        serial_status = app.extensions["serial_service"].status()
        return response({"reading": reading, "arduino": serial_status})

    @app.get("/api/history")
    def history():
        try:
            start = request.args.get("start")
            end = request.args.get("end")
            selected_range = request.args.get("range")
            if selected_range:
                if selected_range not in ALLOWED_RANGES:
                    return response(error="Choose a supported range: 1h, 6h, 24h, or 7d.", status=400)
                start = (datetime.now(timezone.utc) - ALLOWED_RANGES[selected_range]).isoformat(timespec="seconds")
            for value in (start, end):
                if value:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
            is_csv = request.args.get("format") == "csv"
            limit = None if is_csv else min(max(int(request.args.get("limit", 500)), 1), 5000)
            offset = max(int(request.args.get("offset", 0)), 0)
            readings, total = database.list_readings(
                app.config["DATABASE_PATH"], start, end, request.args.get("search", "").strip(), limit, offset
            )
            if is_csv:
                csv_response = make_response(database.readings_as_csv(readings))
                csv_response.headers["Content-Type"] = "text/csv; charset=utf-8"
                csv_response.headers["Content-Disposition"] = 'attachment; filename="sensor-readings.csv"'
                return csv_response
            return response({"readings": readings, "total": total, "limit": limit, "offset": offset})
        except (ValueError, OverflowError) as error:
            return response(error=f"Invalid history filter: {error}", status=400)

    @app.get("/api/weather")
    def weather():
        result = load_weather(force=request.args.get("refresh") == "true")
        status = 200 if result["success"] else 503
        return response(result, error=None if result["success"] else result["message"], status=status)

    @app.get("/api/forecast")
    def forecast():
        result = load_weather(force=request.args.get("refresh") == "true")
        data = {"hourly": result.get("hourly", []), "daily": result.get("daily", []), "status": result["status"]}
        return response(data, error=None if result["success"] else result["message"], status=200 if result["success"] else 503)

    @app.get("/api/analysis")
    def analysis():
        try:
            return response(ml_service.analyze(app.config["DATABASE_PATH"]))
        except (sqlite3.Error, ValueError, RuntimeError) as error:
            app.logger.exception("Could not analyze sensor history.")
            return response(error=f"Trend analysis failed: {error}", status=500)

    @app.get("/api/alerts")
    def alerts():
        try:
            limit = min(max(int(request.args.get("limit", 100)), 1), 500)
            items = database.list_alerts(app.config["DATABASE_PATH"], limit)
            return response({"alerts": items, "total": len(items)})
        except ValueError:
            return response(error="Alert limit must be a whole number.", status=400)

    @app.get("/api/ports")
    def ports():
        try:
            from serial.tools import list_ports
            available = [{"device": item.device, "description": item.description} for item in list_ports.comports()]
        except ImportError as error:
            return response(error=f"PySerial port discovery is unavailable: {error}", status=503)
        return response({"ports": available, "selected": app.config["SERIAL_PORT"]})

    @app.get("/api/status")
    def status():
        try:
            with sqlite3.connect(app.config["DATABASE_PATH"], timeout=2) as connection:
                connection.execute("SELECT 1").fetchone()
            database_status = {"connected": True, "message": "Database is ready."}
        except sqlite3.Error as error:
            database_status = {"connected": False, "message": str(error)}
        return response({
            "arduino": app.extensions["serial_service"].status(),
            "database": database_status,
            "weather": {"status": (app.extensions["weather_cache"]["data"] or {}).get("status", "not_checked")},
        })

    @app.get("/api/settings")
    def get_settings():
        values = {**DEFAULTS, **database.get_settings(app.config["DATABASE_PATH"])}
        return response(values)

    @app.post("/api/settings")
    def update_settings():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not payload:
            return response(error="Send a non-empty JSON object with settings to update.", status=400)
        unknown = set(payload) - SETTING_KEYS
        if unknown:
            return response(error=f"Unsupported setting(s): {', '.join(sorted(unknown))}.", status=400)
        updated = {}
        if "location" in payload:
            location = payload["location"]
            if not isinstance(location, dict):
                return response(error="Location must be an object with name, latitude, and longitude.", status=400)
            try:
                name = str(location.get("name", "")).strip()
                latitude = float(location["latitude"])
                longitude = float(location["longitude"])
                if not name or len(name) > 100 or not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                return response(error="Enter a location name, latitude from -90 to 90, and longitude from -180 to 180.", status=400)
            updated["location"] = {"name": name, "latitude": latitude, "longitude": longitude}
        if "thresholds" in payload:
            thresholds = payload["thresholds"]
            if not isinstance(thresholds, dict) or set(thresholds) != set(alert_service.DEFAULT_THRESHOLDS):
                return response(error="Thresholds must include temperature_high, humidity_high, air_quality_high, and rain_wet_below.", status=400)
            try:
                numeric = {key: float(value) for key, value in thresholds.items()}
                bounds = {
                    "temperature_high": (-40, 85), "humidity_high": (0, 100),
                    "air_quality_high": (0, 1023), "rain_wet_below": (0, 1023),
                }
                if any(not (bounds[key][0] <= value <= bounds[key][1]) for key, value in numeric.items()):
                    raise ValueError
                updated["thresholds"] = numeric
            except (TypeError, ValueError):
                return response(error="Threshold values must be valid sensor-range numbers.", status=400)
        database.save_settings(app.config["DATABASE_PATH"], updated)
        if "location" in updated:
            app.extensions["weather_cache"].update(updated=0, data=None)
        return response({**DEFAULTS, **database.get_settings(app.config["DATABASE_PATH"])})

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            return response(error="API endpoint not found.", status=404)
        return "Page not found", 404

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error("Unhandled server error: %s", error)
        return response(error="The server could not complete the request. Check the application log.", status=500)

    return app


app = create_app()


if __name__ == "__main__":
    app.extensions["serial_service"].start()
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False, threaded=True)
