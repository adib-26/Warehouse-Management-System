"""Focused tests for forecasting route data preparation."""

from datetime import date, datetime, timedelta, timezone
import json

from fastapi import HTTPException
import pytest

from routes.forecasting import (
    ForecastRequestError,
    _evaluate_holdout_predictions,
    _load_candidate_history,
    _load_m5_evaluation_history,
    _m5_evaluation_protocol,
    _m5_evaluation_window,
    _forecast_result_model_filter,
    compat_router as forecast_compat_router,
    list_forecast_alerts,
    project_forecast_stockouts,
    start_forecast,
)
from routes.products import update_product_reorder_settings
from schemas import (
    ArimaForecastRequest,
    ForecastRunRequest,
    M5EvaluationRequest,
    ProductReorderSettingsRequest,
    RollingAverageForecastRequest,
    StockoutRiskRequest,
)


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


@pytest.mark.parametrize(
    "request_type, kwargs",
    [
        (RollingAverageForecastRequest, {"source": "WMS", "horizon_dyas": 28}),
        (ForecastRunRequest, {"source": "M5", "model_typo": "arima"}),
        (StockoutRiskRequest, {"unsupported_threshold": 5}),
        (
            ProductReorderSettingsRequest,
            {"warehouse_id": 1, "lead_time_days": 2, "unsafe_extra": True},
        ),
    ],
)
def test_forecast_and_reorder_requests_reject_unknown_fields(request_type, kwargs):
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        request_type(**kwargs)


class _QueryResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _StockoutConnection:
    def __init__(self, run, rows):
        self.run = run
        self.rows = rows
        self.closed = False

    def execute(self, sql, _params=None):
        if "FROM forecast_runs WHERE id=?" in sql:
            return _QueryResult([self.run])
        if "SELECT DISTINCT model_name FROM forecast_results" in sql:
            return _QueryResult([{"model_name": self.run["model_name"]}])
        if "FROM forecast_results r" in sql:
            return _QueryResult(self.rows)
        raise AssertionError(f"Unexpected SQL: {sql}")

    def close(self):
        self.closed = True


def _stockout_forecast_rows(as_of_date, *, available_stock=120, test_product=False):
    rows = []
    for offset in range(1, 16):
        rows.append(
            {
                "product_id": 7,
                "sku": "SKU-7",
                "product_name": "Widget",
                "available_stock": available_stock,
                "is_forecast_test": int(test_product),
                "warehouse_id": 11,
                "warehouse_code": "WH-1",
                "warehouse_name": "Main",
                "forecast_date": (as_of_date + timedelta(days=offset)).isoformat(),
                "predicted_demand": 10,
                "lead_time_days": 5,
                "safety_stock": 30,
            }
        )
    return rows


def test_stockout_route_uses_live_wms_balance_and_saved_reorder_settings(monkeypatch):
    today = datetime.now(timezone.utc).date()
    connection = _StockoutConnection(
        {
            "id": 91,
            "model_name": "Rolling average",
            "source": "WMS",
            "status": "success",
            "parameters": json.dumps(
                {"resolved_as_of_date": today.isoformat(), "horizon_days": 15}
            ),
        },
        _stockout_forecast_rows(today),
    )
    monkeypatch.setattr("routes.forecasting.get_db", lambda: connection)

    result = project_forecast_stockouts(
        91,
        StockoutRiskRequest(),
        limit=100,
        offset=0,
        user={"id": 1},
    )

    assert result["uses_live_inventory"] is True
    assert result["data"][0]["inventory_source"] == "products.quantity"
    assert result["data"][0]["available_stock"] == 120
    assert result["data"][0]["lead_time_days"] == 5
    assert result["data"][0]["safety_stock"] == 30
    assert result["data"][0]["reorder_point"] == 80
    assert result["data"][0]["stockout_date"] == (today + timedelta(days=13)).isoformat()
    assert connection.closed is True


def test_stockout_route_requires_simulated_balance_for_m5(monkeypatch):
    m5_cutoff = date(2016, 5, 1)
    connection = _StockoutConnection(
        {
            "id": 92,
            "model_name": "Rolling average",
            "source": "M5",
            "status": "success",
            "parameters": json.dumps(
                {"resolved_as_of_date": m5_cutoff.isoformat(), "horizon_days": 15}
            ),
        },
        _stockout_forecast_rows(m5_cutoff, available_stock=0, test_product=True),
    )
    monkeypatch.setattr("routes.forecasting.get_db", lambda: connection)

    with pytest.raises(HTTPException) as error:
        project_forecast_stockouts(
            92,
            StockoutRiskRequest(),
            limit=100,
            offset=0,
            user={"id": 1},
        )

    assert error.value.status_code == 422
    assert "simulated_starting_stock" in error.value.detail
    assert connection.closed is True


def test_stockout_route_includes_a_confirmed_receipt_in_the_daily_path(monkeypatch):
    m5_cutoff = date(2016, 5, 1)
    connection = _StockoutConnection(
        {
            "id": 93,
            "model_name": "Rolling average",
            "source": "M5",
            "status": "success",
            "parameters": json.dumps(
                {"resolved_as_of_date": m5_cutoff.isoformat(), "horizon_days": 15}
            ),
        },
        _stockout_forecast_rows(m5_cutoff, available_stock=0, test_product=True),
    )
    monkeypatch.setattr("routes.forecasting.get_db", lambda: connection)

    result = project_forecast_stockouts(
        93,
        StockoutRiskRequest(
            simulated_starting_stock=10,
            replenishments=[
                {
                    "product_id": 7,
                    "warehouse_id": 11,
                    "arrival_date": (m5_cutoff + timedelta(days=2)).isoformat(),
                    "quantity": 20,
                    "reference": "PO-1042",
                }
            ],
        ),
        limit=100,
        offset=0,
        user={"id": 1},
    )

    row = result["data"][0]
    assert row["stockout_date"] == (m5_cutoff + timedelta(days=4)).isoformat()
    assert row["daily_projection"][1]["replenishment_received"] == 20
    assert row["incoming_receipts"][0]["reference"] == "PO-1042"
    assert result["has_purchase_order_source"] is False


def test_unified_run_contract_accepts_both_sources_and_dispatches_rolling_average(monkeypatch):
    captured = {}

    def fake_run(request, user):
        captured["request"] = request
        captured["user"] = user
        return {"run_id": 123, "source": request.source}

    monkeypatch.setattr("routes.forecasting.run_rolling_average", fake_run)
    request = ForecastRunRequest(
        source="WMS",
        model="rolling_average",
        window_days=14,
        horizon_days=28,
    )
    result = start_forecast(request, user={"id": 7})

    assert captured["request"].source == "WMS"
    assert captured["request"].window_days == 14
    assert captured["request"].horizon_days == 28
    assert captured["user"] == {"id": 7}
    assert result == {"run_id": 123, "source": "WMS", "requested_model": "rolling_average"}


def test_unified_arima_request_adapts_its_series_cap():
    request = ForecastRunRequest(source="M5", model="arima", series_limit=20)

    assert request.max_arima_series == 20


def test_recommended_forecast_compatibility_paths_are_registered():
    paths = {route.path for route in forecast_compat_router.routes}

    assert {
        "/overview",
        "/products",
        "/products/{product_id}",
        "/run",
        "/runs",
        "/runs/{run_id}/stockout-predictions",
        "/alerts",
    } <= paths


def test_multi_model_arima_filter_includes_the_persisted_fallback_label():
    class _ModelNamesConnection:
        def execute(self, _sql, _params=None):
            return _QueryResult(
                [
                    {"model_name": "ARIMA(1,1,1)"},
                    {"model_name": "ARIMA(1,1,1) fallback"},
                    {"model_name": "7-day rolling average"},
                ]
            )

    clause, params, selected = _forecast_result_model_filter(
        _ModelNamesConnection(),
        {"id": 99, "model_name": "Forecast comparison (4 models)"},
        "ARIMA(1,1,1) + rolling fallback",
    )

    assert clause == "AND r.model_name IN (?, ?)"
    assert params == ["ARIMA(1,1,1)", "ARIMA(1,1,1) fallback"]
    assert selected == "ARIMA(1,1,1) + rolling fallback"


class _ReorderSettingsConnection:
    def __init__(self):
        self.closed = False
        self.committed = False
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if "INSERT INTO product_reorder_settings" in sql:
            return self
        if "FROM products" in sql:
            return _QueryResult([{"id": 8, "sku": "SKU-8", "name": "Widget"}])
        if "FROM warehouses" in sql:
            return _QueryResult([{"id": 12, "warehouse_code": "WH-12", "name": "Main"}])
        if "FROM product_reorder_settings" in sql:
            return _QueryResult(
                [
                    {
                        "product_id": 8,
                        "sku": "SKU-8",
                        "product_name": "Widget",
                        "warehouse_id": 12,
                        "warehouse_code": "WH-12",
                        "warehouse_name": "Main",
                        "lead_time_days": 5,
                        "safety_stock": 30,
                        "review_period_days": 1,
                        "updated_at": "2024-01-01 00:00:00",
                    }
                ]
            )
        raise AssertionError(f"Unexpected SQL: {sql}")

    def cursor(self):
        return self

    def execute_update(self, sql, params):
        self.executed.append((sql, params))

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def test_reorder_settings_are_saved_for_a_real_product_and_warehouse(monkeypatch):
    connection = _ReorderSettingsConnection()
    monkeypatch.setattr("routes.products.get_db", lambda: connection)
    monkeypatch.setattr(
        "routes.products.log_audit",
        lambda cur, *args: cur.executed.append(("audit", args)),
    )

    result = update_product_reorder_settings(
        8,
        ProductReorderSettingsRequest(
            warehouse_id=12,
            lead_time_days=5,
            safety_stock=30,
        ),
        user={"id": 1, "username": "admin"},
    )

    assert result["lead_time_days"] == 5
    assert result["safety_stock"] == 30
    assert connection.committed is True
    assert connection.closed is True
    assert any("ON DUPLICATE KEY UPDATE" in sql for sql, _ in connection.executed)


def test_alerts_return_current_live_low_stock_when_no_wms_run_exists(monkeypatch):
    class _AlertsConnection:
        closed = False

        def execute(self, sql, _params=None):
            if "COUNT(*) AS total" in sql:
                return _QueryResult([{"total": 1}])
            if "FROM forecast_runs" in sql:
                return _QueryResult([])
            return _QueryResult(
                [
                    {
                        "product_id": 8,
                        "sku": "SKU-8",
                        "product_name": "Widget",
                        "available_stock": 2,
                        "alert_threshold": 5,
                        "units_below_threshold": 3,
                        "updated_at": "2024-01-01 00:00:00",
                    }
                ]
            )

        def close(self):
            self.closed = True

    connection = _AlertsConnection()
    monkeypatch.setattr("routes.forecasting.get_db", lambda: connection)
    result = list_forecast_alerts(
        model_name=None,
        limit=100,
        offset=0,
        user={"id": 1},
    )

    assert result["source"] == "WMS"
    assert result["latest_wms_forecast_run"] is None
    assert result["forecast_alerts"] is None
    assert result["data"][0]["units_below_threshold"] == 3
    assert connection.closed is True


def test_alerts_project_stockout_risk_once_and_omit_daily_detail(monkeypatch):
    class _AlertsConnection:
        closed = False

        def execute(self, sql, _params=None):
            if "COUNT(*) AS total" in sql:
                return _QueryResult([{"total": 0}])
            if "FROM forecast_runs" in sql:
                return _QueryResult(
                    [
                        {
                            "id": 44,
                            "model_name": "Rolling average",
                            "started_at": "2024-01-01 00:00:00",
                            "completed_at": "2024-01-01 00:01:00",
                        }
                    ]
                )
            return _QueryResult([])

        def close(self):
            self.closed = True

    calls = []

    def project_once(run_id, request, *, limit, offset, user):
        calls.append((run_id, request.model_name, limit, offset, user))
        return {
            "run_id": run_id,
            "model_name": "Rolling average",
            "summary": {"product_count": 2, "critical": 1},
            "data": [
                {
                    "product_id": 8,
                    "sku": "SKU-8",
                    "product_name": "Critical widget",
                    "inventory_source": "products.quantity",
                    "available_stock": 2,
                    "average_daily_demand": 4,
                    "lead_time_days": 5,
                    "safety_stock": 10,
                    "reorder_point": 30,
                    "inventory_position": 2,
                    "reorder_required": True,
                    "stockout_date": "2024-01-03",
                    "days_remaining": 2,
                    "risk": "critical",
                    "warehouses": [{"warehouse_id": 1}],
                    "daily_projection": [{"date": "2024-01-02"}],
                },
                {
                    "product_id": 9,
                    "sku": "SKU-9",
                    "product_name": "Healthy widget",
                    "inventory_source": "products.quantity",
                    "available_stock": 100,
                    "average_daily_demand": 1,
                    "lead_time_days": 5,
                    "safety_stock": 10,
                    "reorder_point": 15,
                    "inventory_position": 100,
                    "reorder_required": False,
                    "stockout_date": None,
                    "days_remaining": None,
                    "risk": "healthy",
                    "warehouses": [{"warehouse_id": 1}],
                    "daily_projection": [{"date": "2024-01-02"}],
                },
            ],
            "meta": {"total": 2},
        }

    connection = _AlertsConnection()
    monkeypatch.setattr("routes.forecasting.get_db", lambda: connection)
    monkeypatch.setattr("routes.forecasting.project_forecast_stockouts", project_once)

    result = list_forecast_alerts(
        model_name=None,
        limit=100,
        offset=0,
        user={"id": 1},
    )

    assert calls == [(44, None, 10_000, 0, {"id": 1})]
    assert result["forecast_warning"] is None
    assert result["forecast_alerts"]["meta"] == {"total": 1}
    alert = result["forecast_alerts"]["data"][0]
    assert alert["product_id"] == 8
    assert alert["warehouse_count"] == 1
    assert "daily_projection" not in alert
    assert connection.closed is True
