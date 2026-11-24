"""Focused tests for forecasting route data preparation."""

from datetime import date, timedelta

import pytest

from routes.forecasting import (
    ForecastRequestError,
    _evaluate_holdout_predictions,
    _load_candidate_history,
    _load_m5_evaluation_history,
    _m5_evaluation_protocol,
    _m5_evaluation_window,
)
from schemas import ArimaForecastRequest, M5EvaluationRequest


class _FakeStreamCursor:
    def __init__(self, rows):
        self.rows = rows
        self.position = 0
        self.closed = False
        self.params = None

    def execute(self, _sql, params):
        self.params = params
        return self

    def fetchmany(self, size):
        batch = self.rows[self.position : self.position + size]
        self.position += len(batch)
        return batch

    def close(self):
        self.closed = True


class _FakeConnection:
    def __init__(self, rows):
        self.cursor = _FakeStreamCursor(rows)

    def stream_cursor(self):
        return self.cursor


def test_candidate_history_only_zero_fills_dates_after_a_series_starts():
    as_of_date = date(2024, 4, 10)
    first_date = as_of_date - timedelta(days=89)
    history_start = as_of_date - timedelta(days=364)
    conn = _FakeConnection(
        [
            {
                "product_id": 7,
                "warehouse_id": 11,
                "demand_date": first_date.isoformat(),
                "quantity_sold": 3,
            },
            {
                "product_id": 7,
                "warehouse_id": 11,
                "demand_date": as_of_date.isoformat(),
                "quantity_sold": 5,
            },
        ]
    )

    histories = _load_candidate_history(
        conn,
        "WMS",
        [
            {
                "product_id": 7,
                "warehouse_id": 11,
                "first_date": first_date.isoformat(),
            }
        ],
        history_start,
        as_of_date,
    )

    values = histories[(7, 11)]
    assert len(values) == 90
    assert values[0] == 3.0
    assert values[1:-1] == [0.0] * 88
    assert values[-1] == 5.0
    assert conn.cursor.params[1:3] == [history_start.isoformat(), as_of_date.isoformat()]
    assert conn.cursor.closed is True


def test_arima_default_fit_cap_adapts_to_a_small_series_sample():
    assert ArimaForecastRequest(source="WMS", series_limit=1).max_arima_series == 1

    with pytest.raises(ValueError, match="cannot exceed series_limit"):
        ArimaForecastRequest(source="WMS", series_limit=1, max_arima_series=2)


def test_m5_development_protocol_uses_the_fixed_validation_split():
    protocol = _m5_evaluation_protocol(_m5_evaluation_window("development"))

    assert protocol == {
        "experiment": "development",
        "label": "Development validation",
        "source_file": "sales_train_validation.csv",
        "training_days": 1885,
        "test_days": 28,
        "training_day_range": "d_1–d_1885",
        "test_day_range": "d_1886–d_1913",
        "training_start": "2011-01-29",
        "training_end": "2016-03-27",
        "test_start": "2016-03-28",
        "test_end": "2016-04-24",
    }


def test_m5_final_protocol_uses_the_fixed_evaluation_split():
    protocol = _m5_evaluation_protocol(_m5_evaluation_window("final"))

    assert protocol["training_days"] == 1913
    assert protocol["test_days"] == 28
    assert protocol["training_day_range"] == "d_1–d_1913"
    assert protocol["test_day_range"] == "d_1914–d_1941"
    assert protocol["training_end"] == "2016-04-24"
    assert protocol["test_start"] == "2016-04-25"
    assert protocol["test_end"] == "2016-05-22"


def test_holdout_metrics_include_wape_bias_and_mase():
    metrics = _evaluate_holdout_predictions(
        predictions=(1.0, 3.0),
        actual_sales=(0.0, 2.0),
        training_sales=(1.0, 3.0, 2.0),
    )

    assert metrics["mae"] == pytest.approx(1.0)
    assert metrics["rmse"] == pytest.approx(1.0)
    assert metrics["wape_pct"] == pytest.approx(100.0)
    assert metrics["bias"] == pytest.approx(1.0)
    assert metrics["naive_mae_scale"] == pytest.approx(1.5)
    assert metrics["mase"] == pytest.approx(2 / 3)
    assert metrics["zero_demand_holdout"] is False


def test_holdout_metrics_do_not_assign_wape_to_a_zero_demand_period():
    metrics = _evaluate_holdout_predictions(
        predictions=(1.0, 0.0),
        actual_sales=(0.0, 0.0),
        training_sales=(1.0, 2.0, 1.0),
    )

    assert metrics["wape_pct"] is None
    assert metrics["zero_demand_holdout"] is True


def test_holdout_metrics_leave_mase_undefined_for_a_constant_training_series():
    metrics = _evaluate_holdout_predictions(
        predictions=(1.0, 0.0),
        actual_sales=(0.0, 0.0),
        training_sales=(4.0, 4.0, 4.0),
    )

    assert metrics["wape_pct"] is None
    assert metrics["zero_demand_holdout"] is True
    assert metrics["naive_mae_scale"] is None
    assert metrics["mase"] is None


def _tiny_m5_window():
    return {
        "training_days": 2,
        "test_days": 2,
        "training_start": date(2024, 1, 1),
        "training_end": date(2024, 1, 2),
        "test_start": date(2024, 1, 3),
        "test_end": date(2024, 1, 4),
    }


def test_m5_evaluation_history_rejects_a_missing_day_instead_of_fabricating_zero_sales():
    conn = _FakeConnection(
        [
            {"product_id": 7, "warehouse_id": 11, "demand_date": "2024-01-01", "quantity_sold": 2},
            {"product_id": 7, "warehouse_id": 11, "demand_date": "2024-01-02", "quantity_sold": 0},
            # 2024-01-03 is intentionally absent; zero is only valid when stored.
            {"product_id": 7, "warehouse_id": 11, "demand_date": "2024-01-04", "quantity_sold": 3},
        ]
    )

    with pytest.raises(ForecastRequestError, match="gaps"):
        _load_m5_evaluation_history(
            conn,
            [{"product_id": 7, "warehouse_id": 11}],
            _tiny_m5_window(),
        )

    assert conn.cursor.closed is True


def test_m5_evaluation_history_rejects_duplicate_daily_observations():
    conn = _FakeConnection(
        [
            {"product_id": 7, "warehouse_id": 11, "demand_date": "2024-01-01", "quantity_sold": 2},
            {"product_id": 7, "warehouse_id": 11, "demand_date": "2024-01-01", "quantity_sold": 2},
        ]
    )

    with pytest.raises(ForecastRequestError, match="duplicate"):
        _load_m5_evaluation_history(
            conn,
            [{"product_id": 7, "warehouse_id": 11}],
            _tiny_m5_window(),
        )


def test_fixed_m5_evaluation_rejects_custom_horizon_or_cutoff_fields():
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        M5EvaluationRequest(experiment="final", horizon_days=14)
