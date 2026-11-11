# Smart Environment Monitoring System

A complete Arduino UNO + Flask application for collecting local sensor readings, viewing live and historical data, checking Open-Meteo weather, and trying simple experimental trend models.

> **Measurement note:** MQ-135 and rain sensor values in this project are raw Arduino analog readings from 0 to 1023. They are not certified AQI, gas concentration, or rainfall measurements. Machine-learning output is an experimental trend estimate, not a weather forecast.

## What is included

- Arduino UNO R3 firmware for DHT11 (D4), MQ-135 (A0), rain sensor (A1), and 16×2 I2C LCD (SDA A4 / SCL A5).
- Flask REST API, SQLite storage, automatic COM3 reconnect, and a web dashboard that remains usable if the Arduino or internet is unavailable.
- Live readings, threshold alerts, CSV export, paginated history, four sensor charts, Open-Meteo current/hourly/7-day weather, and linear-regression trend analysis.
- Automated database/API tests, including a simulated Arduino JSON sample.

## 1. Wire the hardware

| Part | Connection |
|---|---|
| DHT11 DATA | Arduino D4 |
| MQ-135 AO | Arduino A0 |
| Rain sensor AO | Arduino A1 |
| LCD SDA | Arduino A4 |
| LCD SCL | Arduino A5 |
| Sensor/LCD VCC | Arduino 5V |
| Sensor/LCD GND | Arduino GND |

Use the Arduino 5V and GND rails on your breadboard for the modules. **No buzzer is used.** The sketch uses LCD I2C address `0x27`; if the display lights but shows no text, check the backpack address (some use `0x3F`) and change the address in the sketch.

## 2. Upload the Arduino sketch

1. Install Arduino IDE 2.3.10 and connect the UNO by USB.
2. In **Tools → Board**, select **Arduino Uno**. In **Tools → Port**, select **COM3** (or the COM port shown on your PC).
3. Open `arduino\smart_environment.ino`.
4. In **Tools → Manage Libraries**, install **DHT sensor library** by Adafruit, **Adafruit Unified Sensor**, and **LiquidCrystal I2C** (use the library providing `LiquidCrystal_I2C.h`).
5. Upload the sketch and confirm that the LCD displays readings.
6. Close Arduino IDE Serial Monitor before starting the Python application. Only one program can use COM3 at a time. To compare output, stop Flask, inspect the JSON lines in Serial Monitor, close Serial Monitor, and restart Flask.

The Arduino sends a JSON line every two seconds at 9600 baud, for example:

```json
{"temperature":29.0,"humidity":65.0,"air_quality":350,"rain_value":850}
```

If DHT11 reading fails, its temperature and humidity fields are sent as JSON `null`. No status text is added to the serial data stream.

## 3. Install and start the web application (Windows CMD)

Open **Command Prompt** and run these commands from the parent folder containing `smart_environment_monitor`:

```bat
cd smart_environment_monitor
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
python app.py
```

If `copy .env.example .env` says the destination already exists, keep your current `.env`; do not overwrite your own settings. The default serial port in the example is `COM3`, and the default baud rate is `9600`.

Open **http://127.0.0.1:5000** in your browser. Use `Ctrl+C` in the same Command Prompt to stop the server. The first run creates `data\environment.db`. If the Arduino is disconnected, the site still starts and displays a clear connection status; it retries the serial port every five seconds. The dashboard only shows **Connected** after valid sensor JSON is received, and marks the link disconnected if no valid reading arrives for six seconds.

### Optional configuration

Edit `.env` before starting the app:

```text
SERIAL_PORT=COM3
SERIAL_BAUD_RATE=9600
SERIAL_RETRY_SECONDS=5
WEATHER_TIMEOUT_SECONDS=8
```

Change the weather coordinates and alert thresholds on the **Settings** page. The default coordinates are Visakhapatnam (17.6868, 83.2185). Weather values come from Open-Meteo and are never substituted for local Arduino readings.

## 4. Dashboard pages

- **Overview** — local DHT11/MQ-135/rain sensor cards, Arduino/database/weather status, current local weather, hourly outlook, recent alerts, and a temperature/humidity chart.
- **Sensor history** — 1-hour, 6-hour, 24-hour, 7-day, or all-time filters; custom date bounds; reading-ID search; pagination; and CSV download.
- **Trend analysis** — trains separate linear regression models from available temperature, humidity, and MQ-135 raw readings. Fewer than 10 samples is not enough to train a model. MAE and RMSE are displayed when training data allows evaluation.
- **Settings** — weather coordinates, sensor alert thresholds, detected COM ports, and alert history.

Temperature, humidity, air-quality raw, and rain raw alert thresholds are configurable. Repeated alerts of the same type are rate-limited to one per ten minutes. There is no buzzer hardware or buzzer code.

## 5. Run the tests (Windows CMD)

With the virtual environment active and the project folder as the current directory:

```bat
python -m pytest -q
```

The tests use temporary SQLite databases and simulated sensor JSON; they do not require an Arduino or a live weather API.

## API reference

All JSON API responses use `success`, `data`, and `error` fields. `GET /api/history?format=csv` returns a CSV file.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/live` | Latest sensor reading and Arduino serial state |
| GET | `/api/history` | Paginated readings and time-range filters |
| GET | `/api/weather` | Current Open-Meteo weather |
| GET | `/api/forecast` | Hourly and 7-day forecast |
| GET | `/api/analysis` | Model status, metrics, and experimental trends |
| GET | `/api/alerts` | Recent threshold alerts |
| GET | `/api/ports` | Detected serial ports |
| GET | `/api/status` | Arduino, database, and weather service status |
| GET / POST | `/api/settings` | Read or update weather location and alert thresholds |

Example history queries:

```text
/api/history?range=6h&limit=100
/api/history?start=2026-01-01T00:00:00%2B00:00&end=2026-01-02T00:00:00%2B00:00
/api/history?range=24h&format=csv
```

## Common troubleshooting

- **Arduino shows Offline:** ensure the USB cable supports data, check the COM number in Windows Device Manager, set `SERIAL_PORT` in `.env`, and close Serial Monitor/Plotter.
- **Port is busy:** close Arduino IDE Serial Monitor and any other serial application, then restart `python app.py`.
- **LCD is blank:** check 5V/GND and SDA/SCL, adjust the LCD contrast potentiometer, and verify `0x27` versus `0x3F`.
- **No DHT values:** check the DHT11 DATA wire is on D4 and sensor power/ground. Failed DHT reads are represented as `null`; analog sensors still report.
- **Weather unavailable:** check internet access. Sensor storage and the rest of the dashboard work without the weather service.
- **No history or ML charts:** historical charts appear after sensor readings are stored; each trend model needs at least ten usable readings.
- **Library installation fails:** activate the project virtual environment first, then rerun `pip install -r requirements.txt`.

## Privacy and project notes

The Flask server binds to `127.0.0.1` by default. Sensor data is stored locally in SQLite. `.env` and database files are excluded from Git. Open-Meteo is a public API and does not require an API key.
