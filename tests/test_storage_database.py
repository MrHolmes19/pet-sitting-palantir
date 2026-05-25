from pet_sitting_palantir.settings import (
    POSTGRES_CONNECT_TIMEOUT_SECONDS,
    POSTGRES_KEEPALIVES_COUNT,
    POSTGRES_KEEPALIVES_IDLE_SECONDS,
    POSTGRES_KEEPALIVES_INTERVAL_SECONDS,
)
from pet_sitting_palantir.storage.database import connect_database


def test_database_connection_has_bounded_remote_failure_detection(monkeypatch) -> None:
    captured_arguments = {}
    expected_connection = object()

    def fake_connect(database_url, **kwargs):
        captured_arguments["database_url"] = database_url
        captured_arguments.update(kwargs)
        return expected_connection

    monkeypatch.setattr("pet_sitting_palantir.storage.database.psycopg.connect", fake_connect)

    connection = connect_database("postgresql://example.test/palantir")

    assert connection is expected_connection
    assert captured_arguments["database_url"] == "postgresql://example.test/palantir"
    assert captured_arguments["connect_timeout"] == POSTGRES_CONNECT_TIMEOUT_SECONDS
    assert captured_arguments["keepalives"] == 1
    assert captured_arguments["keepalives_idle"] == POSTGRES_KEEPALIVES_IDLE_SECONDS
    assert captured_arguments["keepalives_interval"] == POSTGRES_KEEPALIVES_INTERVAL_SECONDS
    assert captured_arguments["keepalives_count"] == POSTGRES_KEEPALIVES_COUNT
