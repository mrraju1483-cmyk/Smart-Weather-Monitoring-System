import csv
import io
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock


_schema_lock = RLock()
_memory_anchors = {}
_memory_lock = RLock()


def _connect(database_path):
    is_memory_uri = database_path.startswith("file:") and "mode=memory" in database_path
    if is_memory_uri:
        with _memory_lock:
            if database_path not in _memory_anchors:
                _memory_anchors[database_path] = sqlite3.connect(
                    database_path, uri=True, check_same_thread=False
                )
        connection = sqlite3.connect(database_path, timeout=10, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
    if database_path != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(database_path):
    with _schema_lock, _connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                temperature REAL,
                humidity REAL,
                air_quality INTEGER,
                rain_value INTEGER,
                timestamp TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sensor_readings_timestamp
                ON sensor_readings(timestamp);
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type TEXT NOT NULL,
                message TEXT NOT NULL,
                sensor_value REAL,
                timestamp TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp);
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_name TEXT NOT NULL UNIQUE,
                setting_value TEXT NOT NULL
            );
            """
        )


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def insert_reading(database_path, reading, timestamp=None):
    timestamp = timestamp or utc_now()
    with _connect(database_path) as connection:
        latest = connection.execute(
            "SELECT temperature, humidity, air_quality, rain_value, timestamp "
            "FROM sensor_readings ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if latest and all(
            latest[key] == reading.get(key)
            for key in ("temperature", "humidity", "air_quality", "rain_value")
        ):
            try:
                previous = datetime.fromisoformat(latest["timestamp"])
                current = datetime.fromisoformat(timestamp)
                if abs((current - previous).total_seconds()) < 1:
                    return latest["timestamp"], False
            except ValueError:
                pass
        connection.execute(
            "INSERT INTO sensor_readings "
            "(temperature, humidity, air_quality, rain_value, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                reading.get("temperature"),
                reading.get("humidity"),
                reading.get("air_quality"),
                reading.get("rain_value"),
                timestamp,
            ),
        )
    return timestamp, True


def list_readings(database_path, start=None, end=None, search=None, limit=500, offset=0):
    clauses = []
    parameters = []
    if start:
        clauses.append("timestamp >= ?")
        parameters.append(start)
    if end:
        clauses.append("timestamp <= ?")
        parameters.append(end)
    if search:
        clauses.append(
            "(CAST(id AS TEXT) LIKE ? OR CAST(temperature AS TEXT) LIKE ? "
            "OR CAST(humidity AS TEXT) LIKE ? OR CAST(air_quality AS TEXT) LIKE ? "
            "OR CAST(rain_value AS TEXT) LIKE ?)"
        )
        parameters.extend([f"%{search}%"] * 5)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(database_path) as connection:
        total = connection.execute(
            f"SELECT COUNT(*) FROM sensor_readings{where}", parameters
        ).fetchone()[0]
        query = (
            f"SELECT id, temperature, humidity, air_quality, rain_value, timestamp "
            f"FROM sensor_readings{where} ORDER BY timestamp DESC"
        )
        query_parameters = list(parameters)
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            query_parameters.extend([limit, offset])
        rows = connection.execute(query, query_parameters).fetchall()
    return [dict(row) for row in rows], total


def get_latest_reading(database_path):
    with _connect(database_path) as connection:
        row = connection.execute(
            "SELECT id, temperature, humidity, air_quality, rain_value, timestamp "
            "FROM sensor_readings ORDER BY timestamp DESC, id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def add_alert(database_path, alert_type, message, sensor_value, timestamp=None):
    timestamp = timestamp or utc_now()
    with _connect(database_path) as connection:
        connection.execute(
            "INSERT INTO alerts (alert_type, message, sensor_value, timestamp) "
            "VALUES (?, ?, ?, ?)",
            (alert_type, message, sensor_value, timestamp),
        )


def list_alerts(database_path, limit=100):
    with _connect(database_path) as connection:
        rows = connection.execute(
            "SELECT id, alert_type, message, sensor_value, timestamp "
            "FROM alerts ORDER BY timestamp DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_settings(database_path):
    with _connect(database_path) as connection:
        rows = connection.execute(
            "SELECT setting_name, setting_value FROM settings"
        ).fetchall()
    result = {}
    for row in rows:
        try:
            result[row["setting_name"]] = json.loads(row["setting_value"])
        except json.JSONDecodeError:
            result[row["setting_name"]] = row["setting_value"]
    return result


def save_settings(database_path, values):
    with _connect(database_path) as connection:
        for key, value in values.items():
            connection.execute(
                "INSERT INTO settings (setting_name, setting_value) VALUES (?, ?) "
                "ON CONFLICT(setting_name) DO UPDATE SET setting_value=excluded.setting_value",
                (key, json.dumps(value)),
            )


def readings_as_csv(readings):
    output = io.StringIO()
    writer = csv.DictWriter(
        output, fieldnames=["id", "temperature", "humidity", "air_quality", "rain_value", "timestamp"]
    )
    writer.writeheader()
    writer.writerows(readings)
    return output.getvalue()
