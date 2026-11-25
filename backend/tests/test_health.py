"""Small health-check regressions that do not require a database."""

from fastapi import HTTPException
from pymysql.err import OperationalError

import main


class _FailedProbeConnection:
    def __init__(self):
        self.closed = False

    def execute(self, _sql):
        raise OperationalError(2013, "Lost connection to MySQL server during query")

    def close(self):
        self.closed = True


def test_health_reports_a_dropped_database_connection_as_unavailable(monkeypatch):
    connection = _FailedProbeConnection()
    monkeypatch.setattr(main, "get_db", lambda: connection)

    try:
        main.health()
    except HTTPException as error:
        assert error.status_code == 503
        assert error.detail == "Database unavailable"
    else:  # pragma: no cover - makes the expected HTTP behavior explicit.
        raise AssertionError("health() should reject a dropped database connection")

    assert connection.closed is True
