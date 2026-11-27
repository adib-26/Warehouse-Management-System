"""Time-series model helpers shared by forecast API routes."""

from dataclasses import dataclass
from datetime import date, timedelta
import logging
import math
import threading
import warnings


logger = logging.getLogger(__name__)

ARIMA_ORDER = (1, 1, 1)
ARIMA_MIN_HISTORY_DAYS = 90
ARIMA_MIN_NONZERO_DAYS = 10
MAX_FORECAST_QUANTITY = 9_999_999_999.99

# warnings.catch_warnings() swaps process-wide state. FastAPI runs requests in
# worker threads, so two concurrent fits could record (or swallow) each
# other's ConvergenceWarnings. Fits that capture warnings run one at a time.
_ARIMA_FIT_LOCK = threading.Lock()


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
        with _ARIMA_FIT_LOCK, warnings.catch_warnings(record=True) as caught_warnings:
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


def project_stockout(
    predictions,
    *,
    available_stock: float,
    as_of_date: date,
    lead_time_days: int,
    safety_stock: float,
    replenishments=(),
    critical_max_days: int = 3,
    high_max_days: int = 7,
    warning_max_days: int = 14,
) -> dict:
    """Project daily stock balances, first unmet-demand date, and reorder risk.

    A replenishment is available at the start of its arrival date, before that
    day's forecast demand. Stockout is the first date whose demand exceeds the
    stock available for that day. Exact depletion at the end of a day therefore
    becomes stockout only if a later day has positive demand.
    """

    numeric_stock = float(available_stock)
    numeric_safety_stock = float(safety_stock)
    if not math.isfinite(numeric_stock) or numeric_stock < 0:
        raise ValueError("available_stock must be a finite non-negative number")
    if not math.isfinite(numeric_safety_stock) or numeric_safety_stock < 0:
        raise ValueError("safety_stock must be a finite non-negative number")
    if lead_time_days < 0:
        raise ValueError("lead_time_days must be non-negative")
    if not 0 <= critical_max_days < high_max_days < warning_max_days:
        raise ValueError("Risk thresholds must increase: critical < high < warning")

    daily = []
    previous_date = None
    for item in predictions:
        raw_date = item["date"]
        forecast_date = raw_date if isinstance(raw_date, date) else date.fromisoformat(str(raw_date))
        demand = float(item.get("predicted_demand", item.get("demand")))
        if not math.isfinite(demand) or demand < 0:
            raise ValueError("Predicted demand must be finite and non-negative")
        if previous_date is not None and forecast_date != previous_date + timedelta(days=1):
            raise ValueError("Forecast dates must be consecutive and unique")
        daily.append({"date": forecast_date, "demand": demand})
        previous_date = forecast_date
    if not daily:
        raise ValueError("At least one daily prediction is required")

    receipts_by_date = {}
    for receipt in replenishments:
        raw_date = receipt["arrival_date"]
        arrival_date = raw_date if isinstance(raw_date, date) else date.fromisoformat(str(raw_date))
        quantity = float(receipt["quantity"])
        if not math.isfinite(quantity) or quantity <= 0:
            raise ValueError("Replenishment quantity must be finite and positive")
        receipts_by_date[arrival_date] = receipts_by_date.get(arrival_date, 0.0) + quantity

    lead_time_demand = sum(
        item["demand"] for item in daily[:lead_time_days]
    )
    lead_time_covered = lead_time_days <= len(daily)
    reorder_point = lead_time_demand + numeric_safety_stock if lead_time_covered else None
    lead_time_end = as_of_date + timedelta(days=lead_time_days)
    lead_time_receipts = sum(
        quantity
        for arrival_date, quantity in receipts_by_date.items()
        if as_of_date < arrival_date <= lead_time_end
    )
    inventory_position = numeric_stock + lead_time_receipts
    reorder_required = (
        inventory_position <= reorder_point if reorder_point is not None else None
    )

    stock = numeric_stock
    # A stockout is the first day with unmet demand. Zero opening stock alone
    # is not one: a day-one receipt or zero demand can still cover every day.
    stockout_date = None
    unmet_demand_total = 0.0
    daily_projection = []
    total_demand = 0.0
    for item in daily:
        forecast_date = item["date"]
        demand = item["demand"]
        received = receipts_by_date.get(forecast_date, 0.0)
        opening_stock = stock + received
        unmet = max(0.0, demand - opening_stock)
        if stockout_date is None and unmet > 0:
            stockout_date = forecast_date
        ending_stock = max(0.0, opening_stock - demand)
        stock = ending_stock
        unmet_demand_total += unmet
        total_demand += demand
        daily_projection.append(
            {
                "date": forecast_date.isoformat(),
                "predicted_demand": round(demand, 2),
                "opening_stock": round(opening_stock, 2),
                "replenishment_received": round(received, 2),
                "unmet_demand": round(unmet, 2),
                "ending_stock": round(ending_stock, 2),
            }
        )

    days_remaining = (
        max(0, (stockout_date - as_of_date).days)
        if stockout_date is not None
        else None
    )
    if days_remaining is None:
        risk = "healthy" if len(daily) > warning_max_days else "unrated"
    elif days_remaining <= critical_max_days:
        risk = "critical"
    elif days_remaining <= high_max_days:
        risk = "high"
    elif days_remaining <= warning_max_days:
        risk = "warning"
    else:
        risk = "healthy"

    return {
        "available_stock": round(numeric_stock, 2),
        "lead_time_days": int(lead_time_days),
        "safety_stock": round(numeric_safety_stock, 2),
        "average_daily_demand": round(total_demand / len(daily), 2),
        "forecast_lead_time_demand": round(lead_time_demand, 2),
        "reorder_point": round(reorder_point, 2) if reorder_point is not None else None,
        "incoming_by_lead_time": round(lead_time_receipts, 2),
        "inventory_position": round(inventory_position, 2),
        "reorder_required": reorder_required,
        "lead_time_covered": lead_time_covered,
        "stockout_date": stockout_date.isoformat() if stockout_date else None,
        "days_remaining": days_remaining,
        "risk": risk,
        "forecast_horizon_days": len(daily),
        "ending_stock": round(stock, 2),
        "unmet_demand_total": round(unmet_demand_total, 2),
        "daily_projection": daily_projection,
    }
