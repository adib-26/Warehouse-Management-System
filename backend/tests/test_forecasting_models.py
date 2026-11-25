"""Focused unit tests for forecasting model safeguards."""

import math
import sys
from datetime import date, timedelta
from types import ModuleType
import warnings

import pytest

from forecasting_models import (
    arima_forecast_with_fallback,
    project_stockout,
    rolling_average_forecast,
)


def _install_fake_statsmodels(monkeypatch, predictions, *, warn=False, fit_error=None):
    class FakeConvergenceWarning(Warning):
        pass

    class FakeResult:
        mle_retvals = {"converged": True}

        def forecast(self, steps):
            assert steps == len(predictions)
            return predictions

    class FakeARIMA:
        def __init__(self, values, order):
            assert order == (1, 1, 1)
            self.values = values

        def fit(self):
            if fit_error is not None:
                raise fit_error
            if warn:
                warnings.warn("did not converge", FakeConvergenceWarning)
            return FakeResult()

    statsmodels = ModuleType("statsmodels")
    tsa = ModuleType("statsmodels.tsa")
    arima = ModuleType("statsmodels.tsa.arima")
    model = ModuleType("statsmodels.tsa.arima.model")
    tools = ModuleType("statsmodels.tools")
    exceptions = ModuleType("statsmodels.tools.sm_exceptions")
    model.ARIMA = FakeARIMA
    exceptions.ConvergenceWarning = FakeConvergenceWarning
    statsmodels.tsa = tsa
    statsmodels.tools = tools
    tsa.arima = arima
    arima.model = model
    tools.sm_exceptions = exceptions

    monkeypatch.setitem(sys.modules, "statsmodels", statsmodels)
    monkeypatch.setitem(sys.modules, "statsmodels.tsa", tsa)
    monkeypatch.setitem(sys.modules, "statsmodels.tsa.arima", arima)
    monkeypatch.setitem(sys.modules, "statsmodels.tsa.arima.model", model)
    monkeypatch.setitem(sys.modules, "statsmodels.tools", tools)
    monkeypatch.setitem(sys.modules, "statsmodels.tools.sm_exceptions", exceptions)


def test_rolling_average_uses_the_fixed_calendar_window():
    assert rolling_average_forecast([10, 0], forecast_days=2, window_days=7) == (
        1.43,
        1.43,
    )


def test_sparse_history_uses_a_rolling_average_fallback():
    outcome = arima_forecast_with_fallback([0.0] * 89, forecast_days=3)

    assert outcome.used_fallback is True
    assert outcome.fallback_reason == "insufficient_history"
    assert outcome.predictions == (0.0, 0.0, 0.0)


def test_intermittent_full_history_reports_insufficient_nonzero_history():
    outcome = arima_forecast_with_fallback([1.0] + [0.0] * 89, forecast_days=1)

    assert outcome.used_fallback is True
    assert outcome.fallback_reason == "insufficient_nonzero_history"


def test_invalid_history_uses_a_rolling_average_fallback():
    outcome = arima_forecast_with_fallback([1.0] * 89 + [float("nan")], forecast_days=1)

    assert outcome.used_fallback is True
    assert outcome.fallback_reason == "invalid_history"
    assert outcome.predictions == (0.86,)


def test_arima_clips_negative_predictions(monkeypatch):
    _install_fake_statsmodels(monkeypatch, [-3.5, 2.25])
    sales = [1.0 if day % 8 == 0 else 0.0 for day in range(90)]

    outcome = arima_forecast_with_fallback(sales, forecast_days=2)

    assert outcome.used_fallback is False
    assert outcome.predictions == (0.0, 2.25)


def test_arima_convergence_warning_uses_a_fallback(monkeypatch):
    _install_fake_statsmodels(monkeypatch, [99.0], warn=True)
    sales = [1.0 if day % 8 == 0 else 0.0 for day in range(90)]

    outcome = arima_forecast_with_fallback(sales, forecast_days=1)

    assert outcome.used_fallback is True
    assert outcome.fallback_reason == "convergence_warning"


def test_expected_fit_error_uses_a_fallback(monkeypatch):
    _install_fake_statsmodels(monkeypatch, [99.0], fit_error=ValueError("bad fit"))
    sales = [1.0 if day % 8 == 0 else 0.0 for day in range(90)]

    outcome = arima_forecast_with_fallback(sales, forecast_days=1)

    assert outcome.used_fallback is True
    assert outcome.fallback_reason == "fit_error"


def test_installed_statsmodels_runs_an_eligible_series():
    """Exercise the declared production dependency without asserting its fit details."""
    sales = [1.0 if day % 8 == 0 else 0.0 for day in range(90)]

    outcome = arima_forecast_with_fallback(sales, forecast_days=1)

    assert len(outcome.predictions) == 1
    assert math.isfinite(outcome.predictions[0])
    assert outcome.predictions[0] >= 0


def test_stockout_projection_tracks_daily_demand_and_reorder_point():
    as_of = date(2024, 1, 1)
    projection = project_stockout(
        [
            {"date": as_of + timedelta(days=offset), "predicted_demand": demand}
            for offset, demand in enumerate((8, 10, 12, 9, 11), start=1)
        ],
        available_stock=120,
        as_of_date=as_of,
        lead_time_days=5,
        safety_stock=30,
    )

    assert [day["ending_stock"] for day in projection["daily_projection"]] == [
        112, 102, 90, 81, 70
    ]
    assert projection["forecast_lead_time_demand"] == 50
    assert projection["reorder_point"] == 80
    assert projection["reorder_required"] is False
    assert projection["stockout_date"] is None


def test_stockout_projection_identifies_first_unmet_demand_and_risk_band():
    as_of = date(2024, 1, 1)
    projection = project_stockout(
        [
            {"date": as_of + timedelta(days=offset), "predicted_demand": 10}
            for offset in range(1, 16)
        ],
        available_stock=25,
        as_of_date=as_of,
        lead_time_days=5,
        safety_stock=30,
    )

    assert projection["stockout_date"] == "2024-01-04"
    assert projection["days_remaining"] == 3
    assert projection["risk"] == "critical"
    assert projection["daily_projection"][2]["unmet_demand"] == 5


def test_stockout_projection_applies_configured_risk_cutoffs():
    as_of = date(2024, 1, 1)
    projection = project_stockout(
        [
            {"date": as_of + timedelta(days=offset), "predicted_demand": 10}
            for offset in range(1, 16)
        ],
        available_stock=25,
        as_of_date=as_of,
        lead_time_days=5,
        safety_stock=0,
        critical_max_days=1,
        high_max_days=4,
        warning_max_days=10,
    )

    assert projection["days_remaining"] == 3
    assert projection["risk"] == "high"


def test_stockout_projection_applies_receipts_before_arrival_day_demand():
    as_of = date(2024, 1, 1)
    projection = project_stockout(
        [
            {
                "date": as_of + timedelta(days=offset),
                "predicted_demand": 10 if offset <= 2 else 0,
            }
            for offset in range(1, 16)
        ],
        available_stock=10,
        as_of_date=as_of,
        lead_time_days=2,
        safety_stock=0,
        replenishments=[
            {"arrival_date": as_of + timedelta(days=2), "quantity": 20}
        ],
    )

    assert projection["daily_projection"][0]["ending_stock"] == 0
    assert projection["daily_projection"][1]["replenishment_received"] == 20
    assert projection["daily_projection"][1]["ending_stock"] == 10
    assert projection["stockout_date"] is None
    assert projection["reorder_point"] == 20
    assert projection["inventory_position"] == 30
    assert projection["reorder_required"] is False
    assert projection["risk"] == "healthy"


def test_stockout_projection_does_not_erase_a_stockout_before_a_late_receipt():
    as_of = date(2024, 1, 1)
    projection = project_stockout(
        [
            {"date": as_of + timedelta(days=offset), "predicted_demand": 10}
            for offset in range(1, 16)
        ],
        available_stock=5,
        as_of_date=as_of,
        lead_time_days=1,
        safety_stock=0,
        replenishments=[
            {"arrival_date": as_of + timedelta(days=2), "quantity": 30}
        ],
    )

    assert projection["stockout_date"] == "2024-01-02"
    assert projection["daily_projection"][0]["unmet_demand"] == 5
    assert projection["daily_projection"][1]["replenishment_received"] == 30
    assert projection["ending_stock"] == 0


def test_stockout_projection_rejects_short_risk_threshold_order_and_gapped_dates():
    as_of = date(2024, 1, 1)
    with pytest.raises(ValueError, match="thresholds must increase"):
        project_stockout(
            [{"date": as_of + timedelta(days=1), "demand": 1}],
            available_stock=10,
            as_of_date=as_of,
            lead_time_days=1,
            safety_stock=0,
            critical_max_days=7,
            high_max_days=3,
            warning_max_days=14,
        )

    with pytest.raises(ValueError, match="consecutive"):
        project_stockout(
            [
                {"date": as_of + timedelta(days=1), "demand": 1},
                {"date": as_of + timedelta(days=3), "demand": 1},
            ],
            available_stock=10,
            as_of_date=as_of,
            lead_time_days=1,
            safety_stock=0,
        )
