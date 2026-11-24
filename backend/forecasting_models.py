"""Time-series model helpers shared by forecast API routes."""

from dataclasses import dataclass
import logging
import math
import warnings


logger = logging.getLogger(__name__)

ARIMA_ORDER = (1, 1, 1)
ARIMA_MIN_HISTORY_DAYS = 90
ARIMA_MIN_NONZERO_DAYS = 10
MAX_FORECAST_QUANTITY = 9_999_999_999.99


@dataclass(frozen=True)
class ForecastOutcome:
    predictions: tuple[float, ...]
    used_fallback: bool
    fallback_reason: str | None = None


def rolling_average_forecast(
    sales,
    forecast_days: int,
    window_days: int = 7,
) -> tuple[float, ...]:
    """Repeat a fixed-calendar-window daily mean for the requested horizon."""
    if forecast_days < 1:
        raise ValueError("forecast_days must be positive")
    if window_days < 1:
        raise ValueError("window_days must be positive")

    values = [float(value) for value in sales]
    recent = values[-window_days:]
    prediction = round(sum(recent) / window_days, 2)
    return (prediction,) * forecast_days


def rolling_average_fallback(
    sales,
    forecast_days: int,
    window_days: int,
    reason: str,
) -> ForecastOutcome:
    return ForecastOutcome(
        predictions=rolling_average_forecast(sales, forecast_days, window_days),
        used_fallback=True,
        fallback_reason=reason,
    )


def _normalise_sales(sales) -> tuple[list[float], bool]:
    values = []
    invalid = False
    for value in sales:
        try:
            normalized = float(value)
        except (TypeError, ValueError, OverflowError):
            normalized = 0.0
            invalid = True
        if not math.isfinite(normalized) or normalized < 0:
            normalized = 0.0
            invalid = True
        values.append(normalized)
    return values, invalid


def arima_forecast_with_fallback(
    sales,
    forecast_days: int = 14,
    fallback_window_days: int = 7,
) -> ForecastOutcome:
    """Fit ARIMA(1,1,1), returning a rolling average when the fit is unsafe."""
    if forecast_days < 1:
        raise ValueError("forecast_days must be positive")
    if fallback_window_days not in {7, 14, 30}:
        raise ValueError("fallback_window_days must be 7, 14, or 30")

    values, invalid_history = _normalise_sales(sales)

    def fallback(reason: str) -> ForecastOutcome:
        return rolling_average_fallback(
            values,
            forecast_days,
            fallback_window_days,
            reason,
        )

    if invalid_history:
        return fallback("invalid_history")

    nonzero_days = sum(value > 0 for value in values)
    if len(values) < ARIMA_MIN_HISTORY_DAYS:
        return fallback("insufficient_history")
    if nonzero_days < ARIMA_MIN_NONZERO_DAYS:
        return fallback("insufficient_nonzero_history")

    try:
        from statsmodels.tsa.arima.model import ARIMA
        from statsmodels.tools.sm_exceptions import ConvergenceWarning
    except ImportError as exc:
        # A missing declared runtime dependency is a deployment failure, not a
        # data-quality condition. Do not silently present a fallback forecast as
        # an ARIMA run in that case.
        raise RuntimeError("Statsmodels is required for ARIMA forecasting") from exc

    try:
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always", ConvergenceWarning)
            fitted = ARIMA(values, order=ARIMA_ORDER).fit()

        if any(
            issubclass(item.category, ConvergenceWarning)
            for item in caught_warnings
        ):
            return fallback("convergence_warning")

        mle_retvals = getattr(fitted, "mle_retvals", None) or {}
        convergence = mle_retvals.get("converged")
        if convergence is not None and not bool(convergence):
            return fallback("not_converged")

        raw_predictions = fitted.forecast(steps=forecast_days)
        predictions = tuple(float(value) for value in raw_predictions)
        if len(predictions) != forecast_days or any(
            not math.isfinite(value) or abs(value) > MAX_FORECAST_QUANTITY
            for value in predictions
        ):
            return fallback("invalid_predictions")

        return ForecastOutcome(
            predictions=tuple(max(0.0, value) for value in predictions),
            used_fallback=False,
        )
    except (ArithmeticError, FloatingPointError, OverflowError, RuntimeError, ValueError):
        logger.debug("ARIMA fit failed; using rolling-average fallback", exc_info=True)
        return fallback("fit_error")


def arima_forecast(sales, forecast_days: int = 14) -> tuple[float, ...]:
    """Convenience wrapper returning clipped predictions with a 7-day fallback."""
    return arima_forecast_with_fallback(sales, forecast_days).predictions
