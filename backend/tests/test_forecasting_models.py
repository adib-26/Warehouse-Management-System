"""Focused unit tests for forecasting model safeguards."""

import math
import sys
from types import ModuleType
import warnings

from forecasting_models import (
    arima_forecast_with_fallback,
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
