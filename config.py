import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "environment.db"))
    SERIAL_PORT = os.getenv("SERIAL_PORT", "COM3")
    SERIAL_BAUD_RATE = int(os.getenv("SERIAL_BAUD_RATE", "9600"))
    SERIAL_RETRY_SECONDS = float(os.getenv("SERIAL_RETRY_SECONDS", "5"))
    WEATHER_TIMEOUT_SECONDS = float(os.getenv("WEATHER_TIMEOUT_SECONDS", "8"))
    JSON_SORT_KEYS = False


class TestConfig(Config):
    TESTING = True
    DATABASE_PATH = ":memory:"
    SERIAL_PORT = ""
