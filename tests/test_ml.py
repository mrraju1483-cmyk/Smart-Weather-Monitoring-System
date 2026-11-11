from backend import database, ml_service


def test_trend_models_train_with_enough_historical_readings(tmp_path):
    database_path = str(tmp_path / "ml-test.db")
    database.init_db(database_path)
    for index in range(12):
        database.insert_reading(
            database_path,
            {
                "temperature": 20 + index * 0.2,
                "humidity": 60 + index * 0.3,
                "air_quality": 300 + index * 2,
                "rain_value": 850,
            },
            f"2026-01-01T10:{index:02d}:00+00:00",
        )

    result = ml_service.analyze(database_path)

    assert result["status"] == "trained"
    assert result["dataset_size"] == 12
    assert set(result["metrics"]) == {"temperature", "humidity", "air_quality"}
    assert result["trends"]["temperature"]["status"] == "trained"
    assert result["metrics"]["air_quality"]["rmse"] >= 0
