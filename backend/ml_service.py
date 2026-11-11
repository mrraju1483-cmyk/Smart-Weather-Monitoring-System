from datetime import datetime, timezone

import numpy as np
from sklearn.linear_model import LinearRegression

from backend import database

MIN_TRAINING_SAMPLES = 10
TARGETS = {
    "temperature": "Temperature",
    "humidity": "Humidity",
    "air_quality": "MQ-135 raw reading",
}


def analyze(database_path):
    readings, total = database.list_readings(database_path, limit=5000)
    readings.reverse()
    result = {
        "status": "insufficient_data",
        "dataset_size": total,
        "minimum_samples": MIN_TRAINING_SAMPLES,
        "metrics": {},
        "trends": {},
        "disclaimer": (
            "These are experimental trend estimates from recent sensor history, not reliable weather forecasts. "
            "MQ-135 values are raw analog readings, not certified AQI or ppm. The rain sensor alone does not predict rainfall."
        ),
    }
    if total < MIN_TRAINING_SAMPLES:
        result["message"] = f"Collect at least {MIN_TRAINING_SAMPLES} readings to train trend models."
        return result

    trained = 0
    for key, label in TARGETS.items():
        points = [(row["timestamp"], row[key]) for row in readings if row[key] is not None]
        if len(points) < MIN_TRAINING_SAMPLES:
            result["trends"][key] = {"label": label, "status": "insufficient_data", "points": []}
            continue
        timestamps = [datetime.fromisoformat(item[0]) for item in points]
        origin = timestamps[0]
        x = np.array([[(item - origin).total_seconds() / 3600] for item in timestamps])
        y = np.array([item[1] for item in points], dtype=float)
        split = max(1, int(len(points) * 0.8))
        model = LinearRegression().fit(x[:split], y[:split])
        predictions = model.predict(x[split:]) if split < len(points) else model.predict(x)
        expected = y[split:] if split < len(points) else y
        mae = float(np.mean(np.abs(expected - predictions)))
        rmse = float(np.sqrt(np.mean((expected - predictions) ** 2)))
        full_model = LinearRegression().fit(x, y)
        horizon = max((x[-1][0] - x[0][0]) / max(len(points) - 1, 1), 1 / 60)
        future_time = datetime.now(timezone.utc).isoformat(timespec="seconds")
        future_hours = (datetime.now(timezone.utc) - origin).total_seconds() / 3600 + horizon
        estimate = float(full_model.predict(np.array([[future_hours]]))[0])
        result["trends"][key] = {
            "label": label,
            "status": "trained",
            "points": [{"timestamp": stamp, "value": float(value)} for stamp, value in points[-200:]],
            "next_estimate": {"timestamp": future_time, "value": estimate},
        }
        result["metrics"][key] = {"mae": mae, "rmse": rmse, "samples": len(points)}
        trained += 1
    result["status"] = "trained" if trained else "insufficient_data"
    result["message"] = f"{trained} of {len(TARGETS)} trend models trained."
    return result
