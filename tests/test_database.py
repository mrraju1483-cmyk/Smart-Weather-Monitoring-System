from backend import database


def test_database_saves_and_reads_sensor_values(tmp_path):
    database_path = str(tmp_path / "test.db")
    database.init_db(database_path)
    sample = {"temperature": 29.0, "humidity": 65.0, "air_quality": 350, "rain_value": 850}

    timestamp, inserted = database.insert_reading(database_path, sample, "2026-01-01T10:00:00+00:00")
    readings, count = database.list_readings(database_path)

    assert inserted is True
    assert timestamp == "2026-01-01T10:00:00+00:00"
    assert count == 1
    assert readings[0]["temperature"] == 29.0
    assert readings[0]["humidity"] == 65.0
    assert readings[0]["air_quality"] == 350
    assert readings[0]["rain_value"] == 850


def test_database_deduplicates_an_immediate_repeated_line(tmp_path):
    database_path = str(tmp_path / "test.db")
    database.init_db(database_path)
    sample = {"temperature": 29.0, "humidity": 65.0, "air_quality": 350, "rain_value": 850}

    database.insert_reading(database_path, sample, "2026-01-01T10:00:00+00:00")
    _, inserted = database.insert_reading(database_path, sample, "2026-01-01T10:00:00.500000+00:00")
    readings, count = database.list_readings(database_path)

    assert inserted is False
    assert count == 1
    assert len(readings) == 1
