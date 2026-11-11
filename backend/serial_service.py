import json
import logging
import math
import sqlite3
import threading
import time
from datetime import datetime, timezone

from backend import alert_service, database

logger = logging.getLogger(__name__)
VALID_READING_TIMEOUT_SECONDS = 6


def validate_reading(payload):
    if not isinstance(payload, dict):
        raise ValueError("A sensor message must be a JSON object.")
    result = {}
    for key, minimum, maximum, integer in (
        ("temperature", -40, 85, False),
        ("humidity", 0, 100, False),
        ("air_quality", 0, 1023, True),
        ("rain_value", 0, 1023, True),
    ):
        value = payload.get(key)
        if value is None and key in ("temperature", "humidity"):
            result[key] = None
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be a number" + (" or null." if key in ("temperature", "humidity") else "."))
        if not math.isfinite(value) or value < minimum or value > maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}.")
        result[key] = int(value) if integer else float(value)
    return result


class SerialService:
    def __init__(self, app):
        self.app = app
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self.connected = False
        self._port_open = False
        self.last_message_at = None
        self.last_error = None
        self.last_reading = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="arduino-serial", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def status(self):
        with self._lock:
            last_message_at = self.last_message_at
            port_open = self._port_open
            last_error = self.last_error

        recent_valid_message = False
        if last_message_at:
            try:
                message_time = datetime.fromisoformat(last_message_at)
                if message_time.tzinfo is None:
                    message_time = message_time.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - message_time).total_seconds()
                recent_valid_message = -3 <= age <= VALID_READING_TIMEOUT_SECONDS
            except ValueError:
                logger.warning("Ignoring invalid last-valid-reading timestamp: %s", last_message_at)

        thread_running = self._thread is not None and self._thread.is_alive()
        if recent_valid_message:
            state = "connected"
        elif port_open and last_message_at is None:
            state = "connecting"
        elif thread_running and last_message_at is None and not last_error:
            state = "connecting"
        else:
            state = "disconnected"

        with self._lock:
            return {
                "connected": state == "connected",
                "state": state,
                "port": self.app.config["SERIAL_PORT"] or None,
                "last_message_at": last_message_at,
                "last_error": last_error,
            }

    def accept_line(self, line):
        try:
            payload = json.loads(line)
            reading = validate_reading(payload)
        except (json.JSONDecodeError, ValueError) as error:
            logger.warning("Ignoring invalid Arduino serial data: %s", error)
            with self._lock:
                self.last_error = str(error)
            return False
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db_path = self.app.config["DATABASE_PATH"]
        try:
            database.insert_reading(db_path, reading, timestamp)
            alert_service.evaluate_reading(db_path, reading)
        except sqlite3.Error as error:
            logger.exception("Received valid Arduino data but could not save it.")
            with self._lock:
                self.last_error = f"Sensor data received, but database save failed: {error}"
                self.last_reading = {**reading, "timestamp": timestamp}
                self.last_message_at = timestamp
                self.connected = True
            return True
        with self._lock:
            self.last_reading = {**reading, "timestamp": timestamp}
            self.last_message_at = timestamp
            self.last_error = None
            self.connected = True
        return True

    def _run(self):
        try:
            import serial
        except ImportError as error:
            logger.exception("PySerial is not installed.")
            with self._lock:
                self.last_error = str(error)
            return
        while not self._stop.is_set():
            port = self.app.config["SERIAL_PORT"]
            if not port:
                self._stop.wait(self.app.config["SERIAL_RETRY_SECONDS"])
                continue
            connection = None
            try:
                connection = serial.Serial(
                    port,
                    self.app.config["SERIAL_BAUD_RATE"],
                    timeout=1,
                )
                time.sleep(2)
                with self._lock:
                    self._port_open = True
                    self.last_error = None
                logger.info("Opened Arduino serial port %s; waiting for a valid sensor JSON line.", port)
                while not self._stop.is_set() and connection.is_open:
                    raw = connection.readline()
                    if raw:
                        self.accept_line(raw.decode("utf-8", errors="replace").strip())
            except (serial.SerialException, OSError) as error:
                logger.info("Arduino serial connection unavailable: %s", error)
                with self._lock:
                    self.connected = False
                    self._port_open = False
                    self.last_error = str(error)
            finally:
                if connection:
                    if connection.is_open:
                        connection.close()
                    with self._lock:
                        self._port_open = False
                        self.connected = False
            self._stop.wait(self.app.config["SERIAL_RETRY_SECONDS"])
