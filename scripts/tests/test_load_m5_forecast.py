"""Regression tests for the safe, single-pass M5 forecast loader."""

import csv
import gzip
import hashlib
import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "load_m5_forecast.py"
SPEC = importlib.util.spec_from_file_location("load_m5_forecast", SCRIPT)
load_m5_forecast = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = load_m5_forecast
assert SPEC.loader is not None
SPEC.loader.exec_module(load_m5_forecast)


class _CollectingStage:
    def __init__(self):
        self.rows = []
        self.row_count = 0

    def add(self, item_id, store_id, demand_date, quantity_sold):
        self.rows.append((item_id, store_id, demand_date, quantity_sold))

    def flush(self):
        self.row_count = len(self.rows)


def _write_gzip_csv(path: Path, rows: list[list[str]]):
    with gzip.open(path, "wt", encoding="utf-8", newline="") as source_file:
        csv.writer(source_file).writerows(rows)


def test_validation_hashes_gzip_while_staging_only_selected_rows():
    with tempfile.TemporaryDirectory() as temporary_directory:
        source = Path(temporary_directory) / "daily_sales.csv.gz"
        _write_gzip_csv(
            source,
            [
                ["item_id", "store_id", "date", "daily_sales"],
                ["ITEM_A", "STORE_1", "2024-01-01", "0"],
                ["ITEM_A", "STORE_1", "2024-01-02", "4"],
                ["ITEM_B", "STORE_2", "2024-01-01", "1"],
                ["ITEM_B", "STORE_2", "2024-01-02", "0"],
            ],
        )
        stage = _CollectingStage()

        summary = load_m5_forecast.validate_input(
            source,
            {("ITEM_A", "STORE_1"): (101, 201)},
            allow_unmapped=True,
            stage_writer=stage,
        )

        assert summary["dataset_sha256"] == load_m5_forecast.sha256_file(source)
        assert summary["source_row_count"] == 4
        assert summary["selected_row_count"] == 2
        assert summary["skipped_row_count"] == 2
        assert summary["selected_series_count"] == 1
        assert summary["selected_store_count"] == 1
        assert stage.rows == [
            ("ITEM_A", "STORE_1", "2024-01-01", 0),
            ("ITEM_A", "STORE_1", "2024-01-02", 4),
        ]


def test_validation_hashes_plain_csv_while_streaming():
    with tempfile.TemporaryDirectory() as temporary_directory:
        source = Path(temporary_directory) / "daily_sales.csv"
        with source.open("w", encoding="utf-8", newline="") as source_file:
            csv.writer(source_file).writerows(
                [
                    ["item_id", "store_id", "date", "daily_sales"],
                    ["ITEM_A", "STORE_1", "2024-01-01", "2"],
                    ["ITEM_A", "STORE_1", "2024-01-02", "3"],
                ]
            )

        summary = load_m5_forecast.validate_input(
            source,
            {("ITEM_A", "STORE_1"): (101, 201)},
            allow_unmapped=False,
        )

        assert summary["dataset_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
        assert summary["selected_row_count"] == 2


class _StageCursor:
    def __init__(self):
        self.executed = []
        self.executemany_calls = []
        self.rowcount = 0
        self._result = None

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        normalized = " ".join(sql.split())
        if "COUNT(*) AS n FROM `tmp_m5_forecast_stage_scope`" in normalized:
            self._result = {"n": 1}
        elif "COUNT(*) AS n FROM `tmp_m5_forecast_stage`" in normalized:
            self._result = {"n": 2}
        else:
            self._result = None
        return self

    def executemany(self, sql, rows):
        self.executemany_calls.append((sql, list(rows)))
        return self

    def fetchone(self):
        return self._result


class _StageConnection:
    def __init__(self):
        self.cursor_instance = _StageCursor()
        self.commit_count = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commit_count += 1


def test_private_stage_batches_rows_and_builds_a_distinct_scope():
    connection = _StageConnection()
    writer = load_m5_forecast.ImportStageWriter(connection, batch_size=2)

    writer.add("ITEM_A", "STORE_1", "2024-01-01", 1)
    writer.add("ITEM_A", "STORE_1", "2024-01-02", 2)
    writer.prepare_scope(expected_rows=2, expected_series=1)

    assert writer.row_count == 2
    assert connection.commit_count == 2
    assert connection.cursor_instance.executemany_calls[0][1] == [
        ("ITEM_A", "STORE_1", "2024-01-01", 1),
        ("ITEM_A", "STORE_1", "2024-01-02", 2),
    ]
    executed_sql = "\n".join(sql for sql, _ in connection.cursor_instance.executed)
    assert "SELECT DISTINCT item_id, store_id" in executed_sql


class _ActivationCursor:
    def __init__(self, mismatch_count=0):
        self.executed = []
        self.rowcount = 0
        self._result = None
        self._mismatch_count = mismatch_count

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        normalized = " ".join(sql.split())
        self.rowcount = 0
        if "WHERE history.id IS NULL" in normalized:
            self._result = {"n": self._mismatch_count}
        elif "SELECT COUNT(*) AS n FROM `tmp_m5_forecast_stage`" in normalized:
            self._result = {"n": 2}
        elif "AND history.demand_date >= ?" in normalized:
            self._result = {"n": 2}
        elif "AND (history.demand_date < ? OR history.demand_date > ?)" in normalized:
            if normalized.startswith("SELECT"):
                self._result = {"n": 0}
            else:
                self.rowcount = 3
                self._result = None
        elif "UPDATE forecast_m5_imports" in normalized:
            self.rowcount = 1
            self._result = None
        else:
            self._result = None
        return self

    def fetchone(self):
        return self._result


class _ActivationConnection:
    def __init__(self, mismatch_count=0):
        self.cursor_instance = _ActivationCursor(mismatch_count)
        self.commit_count = 0
        self.rollback_count = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


def test_staged_replacement_is_verified_and_finalized_in_one_transaction():
    connection = _ActivationConnection()

    deleted_rows = load_m5_forecast.activate_staged_history(
        connection,
        run_id=44,
        expected_rows=2,
        date_start="2024-01-01",
        date_end="2024-01-02",
        replace_existing=True,
    )

    assert deleted_rows == 3
    assert connection.commit_count == 1
    assert connection.rollback_count == 0
    executed_sql = "\n".join(sql for sql, _ in connection.cursor_instance.executed)
    assert "START TRANSACTION" in executed_sql
    assert "INSERT INTO forecast_demand_history" in executed_sql
    assert "DELETE history" in executed_sql
    assert "UPDATE forecast_m5_imports" in executed_sql


def test_staged_replacement_rolls_back_when_post_upsert_verification_fails():
    connection = _ActivationConnection(mismatch_count=1)

    with pytest.raises(RuntimeError, match="verification failed"):
        load_m5_forecast.activate_staged_history(
            connection,
            run_id=44,
            expected_rows=2,
            date_start="2024-01-01",
            date_end="2024-01-02",
            replace_existing=True,
        )

    assert connection.commit_count == 0
    assert connection.rollback_count == 1
    assert not any(
        "UPDATE forecast_m5_imports" in sql
        for sql, _ in connection.cursor_instance.executed
    )


class _MappingCursor:
    def __init__(self):
        self.executed = []
        self.executemany_calls = []
        self.rows = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if "FROM products" in sql:
            self.rows = [{"id": 101}]
        elif "FROM warehouses" in sql:
            self.rows = [{"id": 201}]
        elif "FROM forecast_m5_mappings" in sql:
            self.rows = [
                {
                    "id": 301,
                    "item_id": "ITEM_A",
                    "store_id": "STORE_1",
                    "product_id": 101,
                    "warehouse_id": 201,
                }
            ]
        else:
            self.rows = []
        return self

    def executemany(self, sql, rows):
        self.executemany_calls.append((sql, list(rows)))
        return self

    def fetchall(self):
        return self.rows


class _MappingConnection:
    def __init__(self):
        self.cursor_instance = _MappingCursor()
        self.commit_count = 0
        self.rollback_count = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


def test_mapping_import_reads_only_requested_database_mapping_pairs():
    connection = _MappingConnection()

    resolved = load_m5_forecast.ensure_database_mappings(
        connection,
        {("ITEM_A", "STORE_1"): (101, 201)},
    )

    assert resolved == {("ITEM_A", "STORE_1"): (301, 101, 201)}
    mapping_reads = [
        sql
        for sql, _ in connection.cursor_instance.executed
        if "FROM forecast_m5_mappings" in sql
    ]
    assert len(mapping_reads) == 1
    assert "WHERE (item_id, store_id) IN ((?, ?))" in mapping_reads[0]
