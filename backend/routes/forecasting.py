from datetime import date, timedelta
import json
import logging
import math
from typing import Literal, Optional
import zlib

from fastapi import APIRouter, Depends, HTTPException, Query

from database import get_db
from forecasting_models import (
    ARIMA_MIN_HISTORY_DAYS,
    ARIMA_MIN_NONZERO_DAYS,
    ForecastOutcome,
    arima_forecast_with_fallback,
    rolling_average_forecast,
)
from schemas import (
    ArimaForecastRequest,
    ForecastComparisonRequest,
    M5EvaluationRequest,
    RollingAverageForecastRequest,
)
from security import log_audit, require_permission


router = APIRouter()
logger = logging.getLogger(__name__)

MODEL_NAME = "Rolling average"
MODEL_VERSION_PREFIX = "rolling-average-v1"
ARIMA_MODEL_NAME = "ARIMA(1,1,1)"
ARIMA_MODEL_VERSION_PREFIX = "arima-1-1-1-v1"
ARIMA_FALLBACK_MODEL_NAME = "Rolling average (fallback)"
COMPARISON_RUN_MODEL_NAME = "Forecast comparison (4 models)"
M5_EVALUATION_RUN_MODEL_NAME = "M5 fixed evaluation (4 models)"
M5_IMPORT_LOCK_NAME = "novaledger_m5_forecast_import"
M5_DAY_ONE = date(2011, 1, 29)
M5_EVALUATION_EXPERIMENTS = {
    "development": {
        "label": "Development validation",
        "source_file": "sales_train_validation.csv",
        "training_start_day": 1,
        "training_end_day": 1885,
        "test_start_day": 1886,
        "test_end_day": 1913,
    },
    "final": {
        "label": "Final validation",
        "source_file": "sales_train_evaluation.csv",
        "training_start_day": 1,
        "training_end_day": 1913,
        "test_start_day": 1914,
        "test_end_day": 1941,
    },
}


class ForecastRequestError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _eligible_records(source: str) -> str:
    """Keep M5 sandbox series separate from real WMS products and warehouses."""
    if source == "M5":
        return (
            "p.is_forecast_test=1 AND w.is_forecast_test=1 "
            "AND p.deleted=0 AND p.archived=0 AND w.active=1"
        )
    return (
        "p.is_forecast_test=0 AND w.is_forecast_test=0 "
        "AND p.deleted=0 AND p.archived=0 AND w.active=1"
    )


def _mark_run_failed(conn, run_id: int, message: str) -> None:
    try:
        conn.rollback()
        conn.execute(
            "UPDATE forecast_runs SET status='failed', completed_at=UTC_TIMESTAMP(), "
            "error_message=? WHERE id=?",
            (message[:2000], run_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Could not mark forecast run %s as failed", run_id)


def _acquire_m5_import_lock(conn, source: str) -> bool:
    """Keep a forecast from observing a partially committed M5 import."""
    if source != "M5":
        return False
    row = conn.execute(
        "SELECT GET_LOCK(?, 0) AS acquired", (M5_IMPORT_LOCK_NAME,)
    ).fetchone()
    if row is None or int(row["acquired"] or 0) != 1:
        raise ForecastRequestError(
            409,
            "An M5 import is in progress. Retry forecasting after it completes.",
        )
    return True


def _release_m5_import_lock(conn, acquired: bool) -> None:
    if not acquired:
        return
    try:
        conn.execute("SELECT RELEASE_LOCK(?)", (M5_IMPORT_LOCK_NAME,))
    except Exception:
        logger.debug("Could not release M5 forecast lock", exc_info=True)


def _serialize_run_parameters(request, resolved_as_of_date=None, summary=None):
    parameters = request.model_dump(mode="json")
    if resolved_as_of_date is not None:
        parameters["resolved_as_of_date"] = resolved_as_of_date.isoformat()
    if summary:
        parameters.update(summary)
    return json.dumps(parameters, sort_keys=True, separators=(",", ":"))


def _iter_cursor_rows(cursor, batch_size: int = 2000):
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            return
        yield from rows


def _record_errors(totals, predictions, actuals):
    for prediction, actual in zip(predictions, actuals):
        absolute_error = abs(float(prediction) - float(actual))
        totals["absolute_error"] += absolute_error
        totals["squared_error"] += absolute_error**2
        totals["absolute_actual"] += abs(float(actual))
        totals["count"] += 1


def _summarize_errors(totals):
    count = totals["count"]
    if not count:
        return {"mae": None, "rmse": None, "wape_pct": None}
    return {
        "mae": round(totals["absolute_error"] / count, 4),
        "rmse": round(math.sqrt(totals["squared_error"] / count), 4),
        "wape_pct": (
            round(100 * totals["absolute_error"] / totals["absolute_actual"], 2)
            if totals["absolute_actual"] > 0
            else None
        ),
    }


def _better_model(metrics, metric_name):
    values = [
        (model_key, result[metric_name])
        for model_key, result in metrics.items()
        if result[metric_name] is not None
    ]
    if not values:
        return None
    best_value = min(value for _, value in values)
    winners = [
        model_key
        for model_key, value in values
        if math.isclose(value, best_value, rel_tol=1e-9, abs_tol=1e-9)
    ]
    if len(winners) != 1:
        return "tie"
    return winners[0]


def _lowest_absolute_metric_model(metrics, metric_name):
    values = [
        (model_key, result[metric_name])
        for model_key, result in metrics.items()
        if result[metric_name] is not None
    ]
    if not values:
        return None
    best_value = min(abs(value) for _, value in values)
    winners = [
        model_key
        for model_key, value in values
        if math.isclose(abs(value), best_value, rel_tol=1e-9, abs_tol=1e-9)
    ]
    return winners[0] if len(winners) == 1 else "tie"


def _sample_sort_key(row):
    product_id = int(row["product_id"])
    warehouse_id = int(row["warehouse_id"])
    return (
        zlib.crc32(f"{product_id}:{warehouse_id}".encode("ascii")),
        product_id,
        warehouse_id,
    )


def _series_pair_clause(series_rows):
    return ", ".join("(?, ?)" for _ in series_rows)


def _series_pair_params(series_rows):
    return [
        value
        for row in series_rows
        for value in (int(row["product_id"]), int(row["warehouse_id"]))
    ]


def _list_eligible_series(conn, source, as_of_date, series_limit):
    """Select a stable, bounded series sample with its first observed date."""
    eligibility = _eligible_records(source)
    limit = series_limit + 1
    if source == "M5":
        rows = conn.execute(
            f"""
            SELECT m.product_id, m.warehouse_id, MIN(d.demand_date) AS first_date
            FROM forecast_m5_mappings m
            JOIN products p ON p.id=m.product_id
            JOIN warehouses w ON w.id=m.warehouse_id
            JOIN forecast_demand_history d
              ON d.product_id=m.product_id
             AND d.warehouse_id=m.warehouse_id
             AND d.source='M5'
             AND d.demand_date<=?
            WHERE {eligibility}
            GROUP BY m.product_id, m.warehouse_id
            ORDER BY CRC32(CONCAT(m.product_id, ':', m.warehouse_id)),
                     m.product_id, m.warehouse_id
            LIMIT ?
            """,
            (as_of_date.isoformat(), limit),
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            SELECT d.product_id, d.warehouse_id, MIN(d.demand_date) AS first_date
            FROM forecast_demand_history d
            JOIN products p ON p.id=d.product_id
            JOIN warehouses w ON w.id=d.warehouse_id
            WHERE d.source=? AND d.demand_date<=? AND {eligibility}
            GROUP BY d.product_id, d.warehouse_id
            ORDER BY CRC32(CONCAT(d.product_id, ':', d.warehouse_id)),
                     d.product_id, d.warehouse_id
            LIMIT ?
            """,
            (source, as_of_date.isoformat(), limit),
        ).fetchall()
    return rows[:series_limit], len(rows) > series_limit


def _rolling_average_values(conn, source, series_rows, as_of_date, window_days):
    """Calculate fixed-calendar-window means without materializing zero-filled history."""
    values = {
        (int(row["product_id"]), int(row["warehouse_id"])): 0.0
        for row in series_rows
    }
    if not series_rows:
        return values
    window_start = as_of_date - timedelta(days=window_days - 1)
    pair_clause = _series_pair_clause(series_rows)
    rows = conn.execute(
        f"""
        SELECT product_id, warehouse_id,
               ROUND(COALESCE(SUM(quantity_sold), 0) / ?, 2) AS predicted_demand
        FROM forecast_demand_history
        WHERE source=? AND demand_date BETWEEN ? AND ?
          AND (product_id, warehouse_id) IN ({pair_clause})
        GROUP BY product_id, warehouse_id
        """,
        [
            window_days,
            source,
            window_start.isoformat(),
            as_of_date.isoformat(),
            *_series_pair_params(series_rows),
        ],
    ).fetchall()
    for row in rows:
        values[(int(row["product_id"]), int(row["warehouse_id"]))] = float(
            row["predicted_demand"]
        )
    return values


def _nonzero_days_by_series(conn, source, series_rows, history_start, as_of_date):
    if not series_rows:
        return {}
    pair_clause = _series_pair_clause(series_rows)
    rows = conn.execute(
        f"""
        SELECT product_id, warehouse_id,
               SUM(CASE WHEN quantity_sold > 0 THEN 1 ELSE 0 END) AS nonzero_days
        FROM forecast_demand_history
        WHERE source=? AND demand_date BETWEEN ? AND ?
          AND (product_id, warehouse_id) IN ({pair_clause})
        GROUP BY product_id, warehouse_id
        """,
        [
            source,
            history_start.isoformat(),
            as_of_date.isoformat(),
            *_series_pair_params(series_rows),
        ],
    ).fetchall()
    return {
        (int(row["product_id"]), int(row["warehouse_id"])): int(
            row["nonzero_days"] or 0
        )
        for row in rows
    }


def _load_candidate_history(conn, source, series_rows, history_start, as_of_date):
    """Load ARIMA candidates, zero filling gaps after each series begins."""
    series_starts = {
        (int(row["product_id"]), int(row["warehouse_id"])): max(
            history_start, date.fromisoformat(row["first_date"])
        )
        for row in series_rows
    }
    histories = {
        key: [0.0] * ((as_of_date - series_start).days + 1)
        for key, series_start in series_starts.items()
    }
    if not histories:
        return histories
    pair_clause = _series_pair_clause(series_rows)
    cursor = conn.stream_cursor()
    try:
        cursor.execute(
            f"""
            SELECT product_id, warehouse_id, demand_date, quantity_sold
            FROM forecast_demand_history
            WHERE source=? AND demand_date BETWEEN ? AND ?
              AND (product_id, warehouse_id) IN ({pair_clause})
            ORDER BY product_id, warehouse_id, demand_date
            """,
            [
                source,
                history_start.isoformat(),
                as_of_date.isoformat(),
                *_series_pair_params(series_rows),
            ],
        )
        for row in _iter_cursor_rows(cursor):
            key = (int(row["product_id"]), int(row["warehouse_id"]))
            offset = (
                date.fromisoformat(row["demand_date"]) - series_starts[key]
            ).days
            histories[key][offset] = float(row["quantity_sold"])
    finally:
        cursor.close()
    return histories


def _m5_day_date(day_number: int) -> date:
    return M5_DAY_ONE + timedelta(days=day_number - 1)


def _m5_evaluation_window(experiment: str) -> dict:
    specification = M5_EVALUATION_EXPERIMENTS[experiment]
    return {
        **specification,
        "experiment": experiment,
        "training_start": _m5_day_date(specification["training_start_day"]),
        "training_end": _m5_day_date(specification["training_end_day"]),
        "test_start": _m5_day_date(specification["test_start_day"]),
        "test_end": _m5_day_date(specification["test_end_day"]),
        "training_days": (
            specification["training_end_day"]
            - specification["training_start_day"]
            + 1
        ),
        "test_days": (
            specification["test_end_day"] - specification["test_start_day"] + 1
        ),
    }


def _m5_evaluation_protocol(window: dict) -> dict:
    """Return a JSON-safe description of a fixed M5 backtest split."""
    return {
        "experiment": window["experiment"],
        "label": window["label"],
        "source_file": window["source_file"],
        "training_days": window["training_days"],
        "test_days": window["test_days"],
        "training_day_range": (
            f"d_{window['training_start_day']}–d_{window['training_end_day']}"
        ),
        "test_day_range": f"d_{window['test_start_day']}–d_{window['test_end_day']}",
        "training_start": window["training_start"].isoformat(),
        "training_end": window["training_end"].isoformat(),
        "test_start": window["test_start"].isoformat(),
        "test_end": window["test_end"].isoformat(),
    }


def _list_m5_evaluation_series(conn, window: dict, series_limit: int):
    """Choose only M5 mappings with an exact, gap-free fixed evaluation span."""
    eligibility = _eligible_records("M5")
    required_days = window["training_days"] + window["test_days"]
    limit = series_limit + 1
    rows = conn.execute(
        f"""
        SELECT m.product_id, m.warehouse_id
        FROM forecast_m5_mappings m
        JOIN products p ON p.id=m.product_id
        JOIN warehouses w ON w.id=m.warehouse_id
        JOIN forecast_demand_history d
          ON d.product_id=m.product_id
         AND d.warehouse_id=m.warehouse_id
         AND d.source='M5'
         AND d.demand_date BETWEEN ? AND ?
        WHERE {eligibility}
        GROUP BY m.product_id, m.warehouse_id
        HAVING COUNT(DISTINCT d.demand_date)=?
           AND MIN(d.demand_date)=?
           AND MAX(d.demand_date)=?
        ORDER BY CRC32(CONCAT(m.product_id, ':', m.warehouse_id)),
                 m.product_id, m.warehouse_id
        LIMIT ?
        """,
        (
            window["training_start"].isoformat(),
            window["test_end"].isoformat(),
            required_days,
            window["training_start"].isoformat(),
            window["test_end"].isoformat(),
            limit,
        ),
    ).fetchall()
    return rows[:series_limit], len(rows) > series_limit


def _load_m5_evaluation_history(conn, series_rows, window: dict):
    """Read the complete fixed M5 split and fail rather than invent missing days."""
    training_days = window["training_days"]
    test_days = window["test_days"]
    values = {
        (int(row["product_id"]), int(row["warehouse_id"])): (
            [None] * training_days,
            [None] * test_days,
        )
        for row in series_rows
    }
    if not values:
        return values

    cursor = conn.stream_cursor()
    try:
        cursor.execute(
            f"""
            SELECT product_id, warehouse_id, demand_date, quantity_sold
            FROM forecast_demand_history
            WHERE source='M5' AND demand_date BETWEEN ? AND ?
              AND (product_id, warehouse_id) IN ({_series_pair_clause(series_rows)})
            ORDER BY product_id, warehouse_id, demand_date
            """,
            [
                window["training_start"].isoformat(),
                window["test_end"].isoformat(),
                *_series_pair_params(series_rows),
            ],
        )
        for row in _iter_cursor_rows(cursor):
            key = (int(row["product_id"]), int(row["warehouse_id"]))
            sale_date = date.fromisoformat(row["demand_date"])
            quantity = float(row["quantity_sold"])
            training_sales, test_sales = values[key]
            if sale_date <= window["training_end"]:
                index = (sale_date - window["training_start"]).days
                if training_sales[index] is not None:
                    raise ForecastRequestError(409, "M5 history contains a duplicate daily observation.")
                training_sales[index] = quantity
            else:
                index = (sale_date - window["test_start"]).days
                if test_sales[index] is not None:
                    raise ForecastRequestError(409, "M5 history contains a duplicate daily observation.")
                test_sales[index] = quantity
    finally:
        cursor.close()

    incomplete = [
        key
        for key, (training_sales, test_sales) in values.items()
        if any(value is None for value in training_sales)
        or any(value is None for value in test_sales)
    ]
    if incomplete:
        raise ForecastRequestError(
            409,
            "M5 history changed or has gaps in the required fixed evaluation range.",
        )
    return {
        key: (
            tuple(float(value) for value in training_sales),
            tuple(float(value) for value in test_sales),
        )
        for key, (training_sales, test_sales) in values.items()
    }


def _naive_mae_scale(training_sales) -> float | None:
    """One-step naive in-sample MAE used to scale MASE."""
    if len(training_sales) < 2:
        return None
    scale = sum(
        abs(float(current) - float(previous))
        for previous, current in zip(training_sales, training_sales[1:])
    ) / (len(training_sales) - 1)
    return scale if scale > 0 else None


def _evaluate_holdout_predictions(predictions, actual_sales, training_sales) -> dict:
    """Calculate series-level metrics from the exact predictions saved for a holdout."""
    if len(predictions) != len(actual_sales) or not predictions:
        raise ValueError("predictions and actual_sales must have the same nonzero length")
    errors = [
        float(prediction) - float(actual)
        for prediction, actual in zip(predictions, actual_sales)
    ]
    absolute_error_total = sum(abs(error) for error in errors)
    squared_error_total = sum(error**2 for error in errors)
    actual_demand_total = sum(float(value) for value in actual_sales)
    observation_count = len(actual_sales)
    mae = absolute_error_total / observation_count
    naive_scale = _naive_mae_scale(training_sales)
    return {
        "observation_count": observation_count,
        "actual_demand_total": actual_demand_total,
        "absolute_error_total": absolute_error_total,
        "squared_error_total": squared_error_total,
        "signed_error_total": sum(errors),
        "mae": mae,
        "rmse": math.sqrt(squared_error_total / observation_count),
        "wape_pct": (
            100 * absolute_error_total / actual_demand_total
            if actual_demand_total > 0
            else None
        ),
        "bias": sum(errors) / observation_count,
        "mase": mae / naive_scale if naive_scale is not None else None,
        "naive_mae_scale": naive_scale,
        "zero_demand_holdout": actual_demand_total == 0,
    }


def _new_evaluation_totals() -> dict:
    return {
        "absolute_error_total": 0.0,
        "squared_error_total": 0.0,
        "signed_error_total": 0.0,
        "actual_demand_total": 0.0,
        "observation_count": 0,
        "series_count": 0,
        "zero_demand_series": 0,
        "mase_total": 0.0,
        "mase_series_count": 0,
    }


def _add_evaluation_metrics(totals: dict, metrics: dict) -> None:
    for field in (
        "absolute_error_total",
        "squared_error_total",
        "signed_error_total",
        "actual_demand_total",
        "observation_count",
    ):
        totals[field] += metrics[field]
    totals["series_count"] += 1
    if metrics["zero_demand_holdout"]:
        totals["zero_demand_series"] += 1
    if metrics["mase"] is not None:
        totals["mase_total"] += metrics["mase"]
        totals["mase_series_count"] += 1


def _summarize_evaluation_totals(totals: dict) -> dict:
    observations = totals["observation_count"]
    if not observations:
        return {
            "mae": None,
            "rmse": None,
            "wape_pct": None,
            "bias": None,
            "mase": None,
            "evaluated_series": 0,
            "zero_demand_series": 0,
            "mase_undefined_series": 0,
            "observations": 0,
            "actual_demand_total": 0,
        }
    return {
        "mae": round(totals["absolute_error_total"] / observations, 4),
        "rmse": round(math.sqrt(totals["squared_error_total"] / observations), 4),
        "wape_pct": (
            round(
                100 * totals["absolute_error_total"] / totals["actual_demand_total"],
                4,
            )
            if totals["actual_demand_total"] > 0
            else None
        ),
        "bias": round(totals["signed_error_total"] / observations, 4),
        # Aggregate MASE is the mean of defined per-series MASE values.
        "mase": (
            round(totals["mase_total"] / totals["mase_series_count"], 4)
            if totals["mase_series_count"]
            else None
        ),
        "evaluated_series": totals["series_count"],
        "zero_demand_series": totals["zero_demand_series"],
        "mase_undefined_series": (
            totals["series_count"] - totals["mase_series_count"]
        ),
        "observations": observations,
        "actual_demand_total": round(totals["actual_demand_total"], 2),
    }


@router.post("/rolling-average", status_code=201)
def run_rolling_average(
    request: RollingAverageForecastRequest,
    user: dict = Depends(require_permission("reports", "write")),
):
    """Forecast each eligible product/warehouse series from its trailing daily mean."""
    conn = get_db()
    run_id = None
    m5_lock_acquired = False
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO forecast_runs (model_name, source, status, parameters) "
            "VALUES (?, ?, 'running', ?)",
            (MODEL_NAME, request.source, _serialize_run_parameters(request)),
        )
        run_id = int(cur.lastrowid)
        conn.commit()

        m5_lock_acquired = _acquire_m5_import_lock(conn, request.source)
        eligibility = _eligible_records(request.source)
        latest = conn.execute(
            f"""
            SELECT MAX(d.demand_date) AS latest_date
            FROM forecast_demand_history d
            JOIN products p ON p.id=d.product_id
            JOIN warehouses w ON w.id=d.warehouse_id
            WHERE d.source=? AND {eligibility}
            """,
            (request.source,),
        ).fetchone()
        if latest is None or latest["latest_date"] is None:
            raise ForecastRequestError(
                409, f"No eligible {request.source} demand history is available."
            )

        latest_date = date.fromisoformat(latest["latest_date"])
        as_of_date = request.as_of_date or latest_date
        if as_of_date > latest_date:
            raise ForecastRequestError(
                422,
                f"as_of_date cannot be later than the latest available date ({latest_date}).",
            )

        conn.execute(
            "UPDATE forecast_runs SET parameters=? WHERE id=?",
            (_serialize_run_parameters(request, as_of_date), run_id),
        )
        conn.commit()

        series_rows, series_sample_truncated = _list_eligible_series(
            conn, request.source, as_of_date, request.series_limit
        )
        if not series_rows:
            raise ForecastRequestError(
                409, f"No eligible product/warehouse series exist for {request.source}."
            )
        rolling_values = _rolling_average_values(
            conn, request.source, series_rows, as_of_date, request.window_days
        )
        # The source snapshot is complete. Do not make an M5 import wait for
        # result persistence, which is independent of imported demand history.
        _release_m5_import_lock(conn, m5_lock_acquired)
        m5_lock_acquired = False

        model_version = f"{MODEL_VERSION_PREFIX}-w{request.window_days}"
        forecast_dates = [
            as_of_date + timedelta(days=offset)
            for offset in range(1, request.horizon_days + 1)
        ]
        insert_sql = """
            INSERT INTO forecast_results
                (run_id, product_id, warehouse_id, forecast_date,
                 predicted_demand, model_name, model_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        for forecast_date in forecast_dates:
            result_rows = [
                (
                    run_id,
                    int(row["product_id"]),
                    int(row["warehouse_id"]),
                    forecast_date.isoformat(),
                    rolling_values[(int(row["product_id"]), int(row["warehouse_id"]))],
                    MODEL_NAME,
                    model_version,
                )
                for row in series_rows
            ]
            cur.executemany(insert_sql, result_rows)

        products_processed = len({int(row["product_id"]) for row in series_rows})
        predictions_written = len(series_rows) * len(forecast_dates)
        cur.execute(
            "UPDATE forecast_runs SET status='success', completed_at=UTC_TIMESTAMP(), "
            "products_processed=?, parameters=? WHERE id=?",
            (
                products_processed,
                _serialize_run_parameters(
                    request,
                    as_of_date,
                    {
                        "series_processed": len(series_rows),
                        "predictions_written": predictions_written,
                        "series_sample_truncated": series_sample_truncated,
                    },
                ),
                run_id,
            ),
        )
        log_audit(
            cur,
            user,
            "CREATE",
            "reports",
            "forecast_run",
            run_id,
            (
                f"Generated {request.source} rolling-average forecasts using "
                f"a {request.window_days}-day window for {len(series_rows)} series."
            ),
        )
        conn.commit()
        return {
            "run_id": run_id,
            "model_name": MODEL_NAME,
            "model_version": model_version,
            "source": request.source,
            "window_days": request.window_days,
            "series_limit": request.series_limit,
            "series_sample_truncated": series_sample_truncated,
            "as_of_date": as_of_date.isoformat(),
            "forecast_dates": [value.isoformat() for value in forecast_dates],
            "products_processed": products_processed,
            "series_processed": len(series_rows),
            "predictions_written": predictions_written,
        }
    except ForecastRequestError as exc:
        if run_id is not None:
            _mark_run_failed(conn, run_id, exc.detail)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        if run_id is not None:
            _mark_run_failed(conn, run_id, str(exc))
        logger.exception("Rolling-average forecast failed")
        raise
    finally:
        _release_m5_import_lock(conn, m5_lock_acquired)
        conn.close()


@router.post("/arima", status_code=201)
def run_arima_forecast(
    request: ArimaForecastRequest,
    user: dict = Depends(require_permission("reports", "write")),
):
    """Fit ARIMA per eligible series, falling back safely when needed."""
    conn = get_db()
    history_conn = None
    run_id = None
    m5_lock_acquired = False
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO forecast_runs (model_name, source, status, parameters) "
            "VALUES (?, ?, 'running', ?)",
            (ARIMA_MODEL_NAME, request.source, _serialize_run_parameters(request)),
        )
        run_id = int(cur.lastrowid)
        conn.commit()

        m5_lock_acquired = _acquire_m5_import_lock(conn, request.source)
        eligibility = _eligible_records(request.source)
        latest = conn.execute(
            f"""
            SELECT MAX(d.demand_date) AS latest_date
            FROM forecast_demand_history d
            JOIN products p ON p.id=d.product_id
            JOIN warehouses w ON w.id=d.warehouse_id
            WHERE d.source=? AND {eligibility}
            """,
            (request.source,),
        ).fetchone()
        if latest is None or latest["latest_date"] is None:
            raise ForecastRequestError(
                409, f"No eligible {request.source} demand history is available."
            )

        latest_date = date.fromisoformat(latest["latest_date"])
        as_of_date = request.as_of_date or latest_date
        if as_of_date > latest_date:
            raise ForecastRequestError(
                422,
                f"as_of_date cannot be later than the latest available date ({latest_date}).",
            )

        conn.execute(
            "UPDATE forecast_runs SET parameters=? WHERE id=?",
            (_serialize_run_parameters(request, as_of_date), run_id),
        )
        conn.commit()

        series_rows, series_sample_truncated = _list_eligible_series(
            conn, request.source, as_of_date, request.series_limit
        )
        if not series_rows:
            raise ForecastRequestError(
                409, f"No eligible product/warehouse series exist for {request.source}."
            )

        history_start = as_of_date - timedelta(days=request.history_days - 1)
        minimum_arima_start = as_of_date - timedelta(days=ARIMA_MIN_HISTORY_DAYS - 1)
        rolling_values = _rolling_average_values(
            conn,
            request.source,
            series_rows,
            as_of_date,
            request.fallback_window_days,
        )
        sufficiently_old_series = [
            row
            for row in series_rows
            if date.fromisoformat(row["first_date"]) <= minimum_arima_start
        ]
        nonzero_days = _nonzero_days_by_series(
            conn,
            request.source,
            sufficiently_old_series,
            history_start,
            as_of_date,
        )
        arima_candidates = sorted(
            [
                row
                for row in sufficiently_old_series
                if nonzero_days.get(
                    (int(row["product_id"]), int(row["warehouse_id"])), 0
                ) >= ARIMA_MIN_NONZERO_DAYS
            ],
            key=_sample_sort_key,
        )
        arima_series_rows = arima_candidates[:request.max_arima_series]
        arima_candidate_ids = {
            (int(row["product_id"]), int(row["warehouse_id"]))
            for row in arima_series_rows
        }
        arima_sample_truncated = len(arima_candidates) > request.max_arima_series

        candidate_histories = {}
        if arima_series_rows:
            history_conn = get_db()
            candidate_histories = _load_candidate_history(
                history_conn,
                request.source,
                arima_series_rows,
                history_start,
                as_of_date,
            )
        if history_conn is not None:
            history_conn.close()
            history_conn = None
        # All source reads are now in memory. Release the M5 importer before
        # the potentially long serial ARIMA fitting phase.
        _release_m5_import_lock(conn, m5_lock_acquired)
        m5_lock_acquired = False

        forecast_dates = [
            as_of_date + timedelta(days=offset)
            for offset in range(1, request.horizon_days + 1)
        ]
        fallback_counts = {}
        arima_series_processed = 0
        fallback_series_processed = 0
        result_rows = []
        insert_sql = """
            INSERT INTO forecast_results
                (run_id, product_id, warehouse_id, forecast_date,
                 predicted_demand, model_name, model_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """

        for series in series_rows:
            product_id = int(series["product_id"])
            warehouse_id = int(series["warehouse_id"])
            key = (product_id, warehouse_id)
            if key in arima_candidate_ids:
                outcome = arima_forecast_with_fallback(
                    candidate_histories[key],
                    forecast_days=request.horizon_days,
                    fallback_window_days=request.fallback_window_days,
                )
            else:
                first_date = date.fromisoformat(series["first_date"])
                if first_date > minimum_arima_start:
                    fallback_reason = "insufficient_history"
                elif nonzero_days.get(key, 0) < ARIMA_MIN_NONZERO_DAYS:
                    fallback_reason = "insufficient_nonzero_history"
                else:
                    fallback_reason = "fit_limit"
                outcome = ForecastOutcome(
                    predictions=(rolling_values[key],) * request.horizon_days,
                    used_fallback=True,
                    fallback_reason=fallback_reason,
                )
            if outcome.used_fallback:
                fallback_series_processed += 1
                reason = outcome.fallback_reason or "unknown"
                fallback_counts[reason] = fallback_counts.get(reason, 0) + 1
                model_name = ARIMA_FALLBACK_MODEL_NAME
                model_version = f"{MODEL_VERSION_PREFIX}-w{request.fallback_window_days}"
            else:
                arima_series_processed += 1
                model_name = ARIMA_MODEL_NAME
                model_version = (
                    f"{ARIMA_MODEL_VERSION_PREFIX}-h{request.history_days}"
                )

            result_rows.extend(
                (
                    run_id,
                    product_id,
                    warehouse_id,
                    forecast_date.isoformat(),
                    round(float(prediction), 2),
                    model_name,
                    model_version,
                )
                for forecast_date, prediction in zip(
                    forecast_dates, outcome.predictions
                )
            )
            if len(result_rows) >= 5000:
                cur.executemany(insert_sql, result_rows)
                result_rows.clear()

        if result_rows:
            cur.executemany(insert_sql, result_rows)

        products_processed = len({int(row["product_id"]) for row in series_rows})
        predictions_written = len(series_rows) * len(forecast_dates)
        cur.execute(
            "UPDATE forecast_runs SET status='success', completed_at=UTC_TIMESTAMP(), "
            "products_processed=?, parameters=? WHERE id=?",
            (
                products_processed,
                _serialize_run_parameters(
                    request,
                    as_of_date,
                    {
                        "series_processed": len(series_rows),
                        "predictions_written": predictions_written,
                        "arima_series_processed": arima_series_processed,
                        "fallback_series_processed": fallback_series_processed,
                        "fallback_reasons": fallback_counts,
                        "arima_sample_truncated": arima_sample_truncated,
                        "series_sample_truncated": series_sample_truncated,
                    },
                ),
                run_id,
            ),
        )
        log_audit(
            cur,
            user,
            "CREATE",
            "reports",
            "forecast_run",
            run_id,
            (
                f"Generated {request.source} {ARIMA_MODEL_NAME} forecasts for "
                f"{len(series_rows)} series; rolling-average fallback was used for "
                f"{fallback_series_processed}."
            ),
        )
        conn.commit()
        model_version = f"{ARIMA_MODEL_VERSION_PREFIX}-h{request.history_days}"
        return {
            "run_id": run_id,
            "model_name": ARIMA_MODEL_NAME,
            "model_version": model_version,
            "fallback_model": MODEL_NAME,
            "source": request.source,
            "history_days": request.history_days,
            "fallback_window_days": request.fallback_window_days,
            "series_limit": request.series_limit,
            "max_arima_series": request.max_arima_series,
            "arima_sample_truncated": arima_sample_truncated,
            "series_sample_truncated": series_sample_truncated,
            "as_of_date": as_of_date.isoformat(),
            "forecast_dates": [value.isoformat() for value in forecast_dates],
            "products_processed": products_processed,
            "series_processed": len(series_rows),
            "arima_series_processed": arima_series_processed,
            "fallback_series_processed": fallback_series_processed,
            "fallback_reasons": fallback_counts,
            "predictions_written": predictions_written,
        }
    except ForecastRequestError as exc:
        if run_id is not None:
            _mark_run_failed(conn, run_id, exc.detail)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        if run_id is not None:
            _mark_run_failed(conn, run_id, str(exc))
        logger.exception("ARIMA forecast failed")
        raise
    finally:
        for resource in (history_conn,):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    logger.debug("Could not close a forecast database resource", exc_info=True)
        _release_m5_import_lock(conn, m5_lock_acquired)
        conn.close()


@router.get("/runs")
def list_forecast_runs(
    source: Optional[Literal["M5", "WMS"]] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_permission("reports", "read")),
):
    conn = get_db()
    try:
        where = "WHERE 1=1"
        params = []
        if source is not None:
            where += " AND source=?"
            params.append(source)
        total = conn.execute(
            f"SELECT COUNT(*) FROM forecast_runs {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT id, model_name, source, started_at, completed_at,
                   status, products_processed, error_message, parameters
            FROM forecast_runs
            {where}
            ORDER BY started_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()
        return {
            "data": [dict(row) for row in rows],
            "meta": {"total": total, "limit": limit, "offset": offset},
        }
    finally:
        conn.close()


@router.post("/compare")
def compare_forecast_models(
    request: ForecastComparisonRequest,
    user: dict = Depends(require_permission("reports", "write")),
):
    """Persist four-model predictions and score them on the same holdout dates."""
    conn = get_db()
    history_conn = None
    history_cursor = None
    m5_lock_acquired = False
    run_id = None
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO forecast_runs (model_name, source, status, parameters) "
            "VALUES (?, ?, 'running', ?)",
            (
                COMPARISON_RUN_MODEL_NAME,
                request.source,
                _serialize_run_parameters(
                    request,
                    summary={
                        "models": [
                            "7-day rolling average",
                            "14-day rolling average",
                            "30-day rolling average",
                            "ARIMA(1,1,1)",
                        ],
                        "max_arima_series": request.max_arima_series,
                    },
                ),
            ),
        )
        run_id = int(cur.lastrowid)
        conn.commit()

        m5_lock_acquired = _acquire_m5_import_lock(conn, request.source)
        eligibility = _eligible_records(request.source)
        latest = conn.execute(
            f"""
            SELECT MAX(d.demand_date) AS latest_date
            FROM forecast_demand_history d
            JOIN products p ON p.id=d.product_id
            JOIN warehouses w ON w.id=d.warehouse_id
            WHERE d.source=? AND {eligibility}
            """,
            (request.source,),
        ).fetchone()
        if latest is None or latest["latest_date"] is None:
            raise ForecastRequestError(
                409, f"No eligible {request.source} demand history is available."
            )

        latest_date = date.fromisoformat(latest["latest_date"])
        as_of_date = request.as_of_date or latest_date
        if as_of_date > latest_date:
            raise ForecastRequestError(
                422,
                f"as_of_date cannot be later than the latest available date ({latest_date}).",
            )

        conn.execute(
            "UPDATE forecast_runs SET parameters=? WHERE id=?",
            (
                _serialize_run_parameters(
                    request,
                    as_of_date,
                    {
                        "models": [
                            "7-day rolling average",
                            "14-day rolling average",
                            "30-day rolling average",
                            "ARIMA(1,1,1)",
                        ],
                        "max_arima_series": request.max_arima_series,
                    },
                ),
                run_id,
            ),
        )
        conn.commit()

        holdout_start = as_of_date - timedelta(days=request.horizon_days - 1)
        training_end = holdout_start - timedelta(days=1)
        training_start = training_end - timedelta(days=request.history_days - 1)
        limit = request.series_limit + 1

        if request.source == "M5":
            series_rows = conn.execute(
                f"""
                SELECT m.product_id, m.warehouse_id
                FROM forecast_m5_mappings m
                JOIN products p ON p.id=m.product_id
                JOIN warehouses w ON w.id=m.warehouse_id
                WHERE {eligibility}
                  AND EXISTS (
                      SELECT 1 FROM forecast_demand_history d
                      WHERE d.product_id=m.product_id
                        AND d.warehouse_id=m.warehouse_id
                        AND d.source='M5'
                        AND d.demand_date=?
                  )
                ORDER BY CRC32(CONCAT(m.product_id, ':', m.warehouse_id)),
                         m.product_id, m.warehouse_id
                LIMIT ?
                """,
                (training_start.isoformat(), limit),
            ).fetchall()
        else:
            series_rows = conn.execute(
                f"""
                SELECT d.product_id, d.warehouse_id
                FROM forecast_demand_history d
                JOIN products p ON p.id=d.product_id
                JOIN warehouses w ON w.id=d.warehouse_id
                WHERE d.source=? AND d.demand_date<=? AND {eligibility}
                GROUP BY d.product_id, d.warehouse_id
                HAVING MIN(d.demand_date)<=?
                ORDER BY CRC32(CONCAT(d.product_id, ':', d.warehouse_id)),
                         d.product_id, d.warehouse_id
                LIMIT ?
                """,
                (
                    request.source,
                    as_of_date.isoformat(),
                    training_start.isoformat(),
                    limit,
                ),
            ).fetchall()

        sample_truncated = len(series_rows) > request.series_limit
        series_rows = sorted(
            series_rows[:request.series_limit],
            key=lambda row: (int(row["product_id"]), int(row["warehouse_id"])),
        )
        if not series_rows:
            raise ForecastRequestError(
                409,
                "No product/warehouse series have enough history before the selected holdout period.",
            )

        pair_clause = ", ".join("(?, ?)" for _ in series_rows)
        pair_params = [
            value
            for row in series_rows
            for value in (int(row["product_id"]), int(row["warehouse_id"]))
        ]
        history_conn = get_db()
        history_cursor = history_conn.stream_cursor()
        history_cursor.execute(
            f"""
            SELECT d.product_id, d.warehouse_id, d.demand_date, d.quantity_sold
            FROM forecast_demand_history d
            WHERE d.source=? AND d.demand_date BETWEEN ? AND ?
              AND (d.product_id, d.warehouse_id) IN ({pair_clause})
            ORDER BY d.product_id, d.warehouse_id, d.demand_date
            """,
            [
                request.source,
                training_start.isoformat(),
                as_of_date.isoformat(),
                *pair_params,
            ],
        )
        series_history = {
            (int(row["product_id"]), int(row["warehouse_id"])): (
                [0.0] * request.history_days,
                [0.0] * request.horizon_days,
            )
            for row in series_rows
        }
        for history_row in _iter_cursor_rows(history_cursor):
            key = (int(history_row["product_id"]), int(history_row["warehouse_id"]))
            training_sales, actual_sales = series_history[key]
            demand_date = date.fromisoformat(history_row["demand_date"])
            quantity = float(history_row["quantity_sold"])
            if demand_date <= training_end:
                training_sales[(demand_date - training_start).days] = quantity
            else:
                actual_sales[(demand_date - holdout_start).days] = quantity
        history_cursor.close()
        history_cursor = None
        history_conn.close()
        history_conn = None
        # The entire comparison snapshot is in memory, so model fitting should
        # not keep an M5 import from starting.
        conn.commit()
        _release_m5_import_lock(conn, m5_lock_acquired)
        m5_lock_acquired = False

        model_keys = (
            "rolling_average_7d",
            "rolling_average_14d",
            "rolling_average_30d",
            "arima_with_fallback",
        )
        totals = {
            name: {
                "absolute_error": 0.0,
                "squared_error": 0.0,
                "absolute_actual": 0.0,
                "count": 0,
            }
            for name in model_keys
        }
        arima_candidates = sorted(
            [
                row
                for row in series_rows
                if sum(
                    value > 0
                    for value in series_history[
                        (int(row["product_id"]), int(row["warehouse_id"]))
                    ][0]
                )
                >= ARIMA_MIN_NONZERO_DAYS
            ],
            key=_sample_sort_key,
        )
        arima_series_rows = arima_candidates[: request.max_arima_series]
        arima_series_ids = {
            (int(row["product_id"]), int(row["warehouse_id"]))
            for row in arima_series_rows
        }
        arima_sample_truncated = len(arima_candidates) > request.max_arima_series
        arima_series_processed = 0
        fallback_series_processed = 0
        fallback_reasons = {}
        prediction_rows = []
        insert_sql = """
            INSERT INTO forecast_results
                (run_id, product_id, warehouse_id, forecast_date,
                 predicted_demand, model_name, model_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        rolling_models = (
            ("rolling_average_7d", "7-day rolling average", 7),
            ("rolling_average_14d", "14-day rolling average", 14),
            ("rolling_average_30d", "30-day rolling average", 30),
        )

        for series in series_rows:
            product_id = int(series["product_id"])
            warehouse_id = int(series["warehouse_id"])
            key = (product_id, warehouse_id)
            training_sales, actual_sales = series_history[key]
            series_predictions = {}
            for metric_key, model_name, window_days in rolling_models:
                predictions = rolling_average_forecast(
                    training_sales,
                    forecast_days=request.horizon_days,
                    window_days=window_days,
                )
                series_predictions[metric_key] = (
                    model_name,
                    f"{MODEL_VERSION_PREFIX}-w{window_days}",
                    predictions,
                )
                _record_errors(totals[metric_key], predictions, actual_sales)

            if key in arima_series_ids:
                arima_outcome = arima_forecast_with_fallback(
                    training_sales,
                    forecast_days=request.horizon_days,
                    fallback_window_days=7,
                )
            else:
                nonzero_days = sum(value > 0 for value in training_sales)
                fallback_reason = (
                    "insufficient_history"
                    if len(training_sales) < ARIMA_MIN_HISTORY_DAYS
                    else "insufficient_nonzero_history"
                    if nonzero_days < ARIMA_MIN_NONZERO_DAYS
                    else "fit_limit"
                )
                arima_outcome = ForecastOutcome(
                    predictions=rolling_average_forecast(
                        training_sales,
                        forecast_days=request.horizon_days,
                        window_days=7,
                    ),
                    used_fallback=True,
                    fallback_reason=fallback_reason,
                )

            if arima_outcome.used_fallback:
                fallback_series_processed += 1
                reason = arima_outcome.fallback_reason or "unknown"
                fallback_reasons[reason] = fallback_reasons.get(reason, 0) + 1
                arima_model_name = "ARIMA(1,1,1) fallback"
                arima_model_version = "arima-1-1-1-v1-fallback-w7"
            else:
                arima_series_processed += 1
                arima_model_name = ARIMA_MODEL_NAME
                arima_model_version = (
                    f"{ARIMA_MODEL_VERSION_PREFIX}-h{request.history_days}"
                )
            arima_predictions = tuple(
                round(float(value), 2) for value in arima_outcome.predictions
            )
            series_predictions["arima_with_fallback"] = (
                arima_model_name,
                arima_model_version,
                arima_predictions,
            )
            _record_errors(
                totals["arima_with_fallback"], arima_predictions, actual_sales
            )

            for metric_key, _, _ in rolling_models:
                model_name, model_version, predictions = series_predictions[metric_key]
                for offset, prediction in enumerate(predictions):
                    prediction_rows.append(
                        (
                            run_id,
                            product_id,
                            warehouse_id,
                            (holdout_start + timedelta(days=offset)).isoformat(),
                            round(float(prediction), 2),
                            model_name,
                            model_version,
                        )
                    )
            model_name, model_version, predictions = series_predictions[
                "arima_with_fallback"
            ]
            for offset, prediction in enumerate(predictions):
                prediction_rows.append(
                    (
                        run_id,
                        product_id,
                        warehouse_id,
                        (holdout_start + timedelta(days=offset)).isoformat(),
                        prediction,
                        model_name,
                        model_version,
                    )
                )
            if len(prediction_rows) >= 5000:
                cur.executemany(insert_sql, prediction_rows)
                prediction_rows.clear()

        if prediction_rows:
            cur.executemany(insert_sql, prediction_rows)

        metrics = {name: _summarize_errors(value) for name, value in totals.items()}
        predictions_written = len(series_rows) * request.horizon_days * len(model_keys)
        run_parameters = _serialize_run_parameters(
            request,
            as_of_date,
            {
                "models": [
                    "7-day rolling average",
                    "14-day rolling average",
                    "30-day rolling average",
                    "ARIMA(1,1,1)",
                ],
                "training_start": training_start.isoformat(),
                "training_end": training_end.isoformat(),
                "holdout_start": holdout_start.isoformat(),
                "holdout_end": as_of_date.isoformat(),
                "series_processed": len(series_rows),
                "predictions_written": predictions_written,
                "max_arima_series": request.max_arima_series,
                "arima_sample_truncated": arima_sample_truncated,
                "arima_series_processed": arima_series_processed,
                "fallback_series_processed": fallback_series_processed,
                "fallback_reasons": fallback_reasons,
                "series_sample_truncated": sample_truncated,
            },
        )
        cur.execute(
            "UPDATE forecast_runs SET status='success', completed_at=UTC_TIMESTAMP(), "
            "products_processed=?, parameters=? WHERE id=?",
            (
                len({int(row["product_id"]) for row in series_rows}),
                run_parameters,
                run_id,
            ),
        )
        log_audit(
            cur,
            user,
            "CREATE",
            "reports",
            "forecast_run",
            run_id,
            (
                f"Generated four-model historical forecasts for {request.source} "
                f"across {len(series_rows)} product/warehouse series and "
                f"{request.horizon_days} holdout days."
            ),
        )
        conn.commit()
        return {
            "run_id": run_id,
            "model_name": COMPARISON_RUN_MODEL_NAME,
            "source": request.source,
            "as_of_date": as_of_date.isoformat(),
            "training_start": training_start.isoformat(),
            "training_end": training_end.isoformat(),
            "holdout_start": holdout_start.isoformat(),
            "holdout_end": as_of_date.isoformat(),
            "history_days": request.history_days,
            "horizon_days": request.horizon_days,
            "models": [
                "7-day rolling average",
                "14-day rolling average",
                "30-day rolling average",
                "ARIMA(1,1,1)",
            ],
            "sampled_series": len(series_rows),
            "series_limit": request.series_limit,
            "sample_truncated": sample_truncated,
            "observations_scored": len(series_rows) * request.horizon_days,
            "predictions_written": predictions_written,
            "arima_series_processed": arima_series_processed,
            "fallback_series_processed": fallback_series_processed,
            "fallback_reasons": fallback_reasons,
            "arima_sample_truncated": arima_sample_truncated,
            "max_arima_series": request.max_arima_series,
            "metrics": metrics,
            "better_by": {
                metric_name: _better_model(metrics, metric_name)
                for metric_name in ("mae", "rmse", "wape_pct")
            },
        }
    except ForecastRequestError as exc:
        if run_id is not None:
            _mark_run_failed(conn, run_id, exc.detail)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        if run_id is not None:
            _mark_run_failed(conn, run_id, str(exc))
        logger.exception("Forecast model comparison failed")
        raise
    finally:
        for resource in (history_cursor, history_conn):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    logger.debug("Could not close a forecast database resource", exc_info=True)
        _release_m5_import_lock(conn, m5_lock_acquired)
        conn.close()


@router.post("/m5-evaluations", status_code=201)
def run_m5_evaluation(
    request: M5EvaluationRequest,
    user: dict = Depends(require_permission("reports", "write")),
):
    """Run one immutable, 28-day M5 backtest without training on its holdout."""
    conn = get_db()
    history_conn = None
    m5_lock_acquired = False
    run_id = None
    try:
        window = _m5_evaluation_window(request.experiment)
        protocol = _m5_evaluation_protocol(window)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO forecast_runs (model_name, source, status, parameters) "
            "VALUES (?, 'M5', 'running', ?)",
            (
                M5_EVALUATION_RUN_MODEL_NAME,
                _serialize_run_parameters(
                    request,
                    summary={
                        "evaluation_protocol": protocol,
                        "models": [
                            "7-day rolling average",
                            "14-day rolling average",
                            "30-day rolling average",
                            "ARIMA(1,1,1) + 7-day fallback",
                        ],
                        "max_arima_series": request.max_arima_series,
                    },
                ),
            ),
        )
        run_id = int(cur.lastrowid)
        conn.commit()

        m5_lock_acquired = _acquire_m5_import_lock(conn, "M5")
        series_rows, series_sample_truncated = _list_m5_evaluation_series(
            conn, window, request.series_limit
        )
        if not series_rows:
            raise ForecastRequestError(
                409,
                (
                    "No eligible M5 series has complete daily coverage for "
                    f"{protocol['training_day_range']} and {protocol['test_day_range']}."
                ),
            )
        series_rows = sorted(
            series_rows,
            key=lambda row: (int(row["product_id"]), int(row["warehouse_id"])),
        )

        history_conn = get_db()
        series_history = _load_m5_evaluation_history(
            history_conn, series_rows, window
        )
        history_conn.close()
        history_conn = None
        # The complete fixed split is now in memory, so ARIMA fitting and report
        # persistence must not make an M5 import wait for the named lock.
        conn.commit()
        _release_m5_import_lock(conn, m5_lock_acquired)
        m5_lock_acquired = False

        model_keys = (
            "rolling_average_7d",
            "rolling_average_14d",
            "rolling_average_30d",
            "arima_with_fallback",
        )
        model_totals = {key: _new_evaluation_totals() for key in model_keys}
        nonzero_days = {
            (int(row["product_id"]), int(row["warehouse_id"])): sum(
                value > 0
                for value in series_history[
                    (int(row["product_id"]), int(row["warehouse_id"]))
                ][0]
            )
            for row in series_rows
        }
        arima_candidates = sorted(
            [
                row
                for row in series_rows
                if nonzero_days[
                    (int(row["product_id"]), int(row["warehouse_id"]))
                ]
                >= ARIMA_MIN_NONZERO_DAYS
            ],
            key=_sample_sort_key,
        )
        arima_series_rows = arima_candidates[: request.max_arima_series]
        arima_series_ids = {
            (int(row["product_id"]), int(row["warehouse_id"]))
            for row in arima_series_rows
        }
        arima_sample_truncated = len(arima_candidates) > request.max_arima_series

        rolling_models = (
            ("rolling_average_7d", "7-day rolling average", 7),
            ("rolling_average_14d", "14-day rolling average", 14),
            ("rolling_average_30d", "30-day rolling average", 30),
        )
        forecast_rows = []
        metric_rows = []
        fallback_reasons = {}
        arima_series_processed = 0
        fallback_series_processed = 0
        forecast_insert_sql = """
            INSERT INTO forecast_results
                (run_id, product_id, warehouse_id, forecast_date,
                 predicted_demand, model_name, model_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        metric_insert_sql = """
            INSERT INTO forecast_evaluation_metrics
                (run_id, product_id, warehouse_id, model_key, model_name,
                 model_version, observation_count, actual_demand_total,
                 absolute_error_total, mae, rmse, wape_pct, bias, mase,
                 naive_mae_scale, zero_demand_holdout)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        for series in series_rows:
            product_id = int(series["product_id"])
            warehouse_id = int(series["warehouse_id"])
            key = (product_id, warehouse_id)
            training_sales, actual_sales = series_history[key]
            series_models = []
            for model_key, model_name, window_days in rolling_models:
                predictions = rolling_average_forecast(
                    training_sales,
                    forecast_days=window["test_days"],
                    window_days=window_days,
                )
                predictions = tuple(round(float(value), 2) for value in predictions)
                series_models.append(
                    (
                        model_key,
                        model_name,
                        f"{MODEL_VERSION_PREFIX}-w{window_days}",
                        predictions,
                    )
                )

            if key in arima_series_ids:
                arima_outcome = arima_forecast_with_fallback(
                    training_sales,
                    forecast_days=window["test_days"],
                    fallback_window_days=7,
                )
            else:
                fallback_reason = (
                    "insufficient_nonzero_history"
                    if nonzero_days[key] < ARIMA_MIN_NONZERO_DAYS
                    else "fit_limit"
                )
                arima_outcome = ForecastOutcome(
                    predictions=rolling_average_forecast(
                        training_sales,
                        forecast_days=window["test_days"],
                        window_days=7,
                    ),
                    used_fallback=True,
                    fallback_reason=fallback_reason,
                )

            if arima_outcome.used_fallback:
                fallback_series_processed += 1
                fallback_reason = arima_outcome.fallback_reason or "unknown"
                fallback_reasons[fallback_reason] = (
                    fallback_reasons.get(fallback_reason, 0) + 1
                )
                arima_model_name = "ARIMA(1,1,1) fallback"
                arima_model_version = "arima-1-1-1-v1-fallback-w7"
            else:
                arima_series_processed += 1
                arima_model_name = ARIMA_MODEL_NAME
                arima_model_version = (
                    f"{ARIMA_MODEL_VERSION_PREFIX}-h{window['training_days']}"
                )
            arima_predictions = tuple(
                round(float(value), 2) for value in arima_outcome.predictions
            )
            series_models.append(
                (
                    "arima_with_fallback",
                    arima_model_name,
                    arima_model_version,
                    arima_predictions,
                )
            )

            for model_key, model_name, model_version, predictions in series_models:
                metrics = _evaluate_holdout_predictions(
                    predictions, actual_sales, training_sales
                )
                _add_evaluation_metrics(model_totals[model_key], metrics)
                for offset, prediction in enumerate(predictions):
                    forecast_rows.append(
                        (
                            run_id,
                            product_id,
                            warehouse_id,
                            (window["test_start"] + timedelta(days=offset)).isoformat(),
                            prediction,
                            model_name,
                            model_version,
                        )
                    )
                metric_rows.append(
                    (
                        run_id,
                        product_id,
                        warehouse_id,
                        model_key,
                        model_name,
                        model_version,
                        metrics["observation_count"],
                        round(metrics["actual_demand_total"], 2),
                        round(metrics["absolute_error_total"], 4),
                        round(metrics["mae"], 4),
                        round(metrics["rmse"], 4),
                        (
                            round(metrics["wape_pct"], 4)
                            if metrics["wape_pct"] is not None
                            else None
                        ),
                        round(metrics["bias"], 4),
                        (
                            round(metrics["mase"], 4)
                            if metrics["mase"] is not None
                            else None
                        ),
                        (
                            round(metrics["naive_mae_scale"], 4)
                            if metrics["naive_mae_scale"] is not None
                            else None
                        ),
                        int(metrics["zero_demand_holdout"]),
                    )
                )

            if len(forecast_rows) >= 5000:
                cur.executemany(forecast_insert_sql, forecast_rows)
                forecast_rows.clear()

        if forecast_rows:
            cur.executemany(forecast_insert_sql, forecast_rows)
        if metric_rows:
            cur.executemany(metric_insert_sql, metric_rows)

        metrics = {
            model_key: _summarize_evaluation_totals(totals)
            for model_key, totals in model_totals.items()
        }
        predictions_written = len(series_rows) * window["test_days"] * len(model_keys)
        report_rows_written = len(series_rows) * len(model_keys)
        better_by = {
            metric_name: _better_model(metrics, metric_name)
            for metric_name in ("mae", "rmse", "wape_pct", "mase")
        }
        better_by["absolute_bias"] = _lowest_absolute_metric_model(metrics, "bias")
        run_parameters = _serialize_run_parameters(
            request,
            summary={
                "evaluation_protocol": protocol,
                "models": [
                    "7-day rolling average",
                    "14-day rolling average",
                    "30-day rolling average",
                    "ARIMA(1,1,1) + 7-day fallback",
                ],
                "series_processed": len(series_rows),
                "series_sample_truncated": series_sample_truncated,
                "max_arima_series": request.max_arima_series,
                "arima_candidates": len(arima_candidates),
                "arima_attempted_series": len(arima_series_rows),
                "arima_series_processed": arima_series_processed,
                "arima_sample_truncated": arima_sample_truncated,
                "fallback_series_processed": fallback_series_processed,
                "fallback_reasons": fallback_reasons,
                "predictions_written": predictions_written,
                "evaluation_report_rows": report_rows_written,
                "evaluation_summary": metrics,
                "better_by": better_by,
            },
        )
        cur.execute(
            "UPDATE forecast_runs SET status='success', completed_at=UTC_TIMESTAMP(), "
            "products_processed=?, parameters=? WHERE id=?",
            (
                len({int(row["product_id"]) for row in series_rows}),
                run_parameters,
                run_id,
            ),
        )
        log_audit(
            cur,
            user,
            "CREATE",
            "reports",
            "forecast_run",
            run_id,
            (
                f"Ran fixed M5 {protocol['label'].lower()} for "
                f"{len(series_rows)} product/warehouse series over "
                f"{window['test_days']} holdout days."
            ),
        )
        conn.commit()
        return {
            "run_id": run_id,
            "model_name": M5_EVALUATION_RUN_MODEL_NAME,
            "source": "M5",
            "protocol": protocol,
            "sampled_series": len(series_rows),
            "series_limit": request.series_limit,
            "sample_truncated": series_sample_truncated,
            "observations_scored": len(series_rows) * window["test_days"],
            "predictions_written": predictions_written,
            "evaluation_report_rows": report_rows_written,
            "arima_candidates": len(arima_candidates),
            "arima_attempted_series": len(arima_series_rows),
            "arima_series_processed": arima_series_processed,
            "fallback_series_processed": fallback_series_processed,
            "fallback_reasons": fallback_reasons,
            "arima_sample_truncated": arima_sample_truncated,
            "max_arima_series": request.max_arima_series,
            "metrics": metrics,
            "better_by": better_by,
        }
    except ForecastRequestError as exc:
        if run_id is not None:
            _mark_run_failed(conn, run_id, exc.detail)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        if run_id is not None:
            _mark_run_failed(conn, run_id, str(exc))
        logger.exception("M5 fixed evaluation failed")
        raise
    finally:
        if history_conn is not None:
            try:
                history_conn.close()
            except Exception:
                logger.debug("Could not close M5 evaluation history connection", exc_info=True)
        _release_m5_import_lock(conn, m5_lock_acquired)
        conn.close()


@router.get("/runs/{run_id}/evaluation")
def list_m5_evaluation_metrics(
    run_id: int,
    product_id: Optional[int] = Query(default=None, gt=0),
    warehouse_id: Optional[int] = Query(default=None, gt=0),
    model_key: Optional[str] = Query(default=None, max_length=50),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_permission("reports", "read")),
):
    """Return persisted product/warehouse metrics for a fixed M5 evaluation run."""
    conn = get_db()
    try:
        run = conn.execute(
            "SELECT id, model_name, source, started_at, completed_at, status, "
            "products_processed, error_message, parameters FROM forecast_runs WHERE id=?",
            (run_id,),
        ).fetchone()
        if run is None:
            raise HTTPException(status_code=404, detail="Forecast run not found")
        if run["model_name"] != M5_EVALUATION_RUN_MODEL_NAME:
            raise HTTPException(
                status_code=404,
                detail="This forecast run does not have a fixed M5 evaluation report.",
            )

        where = "WHERE e.run_id=?"
        params = [run_id]
        if product_id is not None:
            where += " AND e.product_id=?"
            params.append(product_id)
        if warehouse_id is not None:
            where += " AND e.warehouse_id=?"
            params.append(warehouse_id)
        if model_key is not None:
            where += " AND e.model_key=?"
            params.append(model_key)
        total = conn.execute(
            f"SELECT COUNT(*) FROM forecast_evaluation_metrics e {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT e.id, e.run_id, e.product_id, p.sku, p.name AS product_name,
                   e.warehouse_id, w.warehouse_code, w.name AS warehouse_name,
                   e.model_key, e.model_name, e.model_version,
                   e.observation_count, e.actual_demand_total,
                   e.absolute_error_total, e.mae, e.rmse, e.wape_pct, e.bias,
                   e.mase, e.naive_mae_scale, e.zero_demand_holdout, e.generated_at
            FROM forecast_evaluation_metrics e
            JOIN products p ON p.id=e.product_id
            JOIN warehouses w ON w.id=e.warehouse_id
            {where}
            ORDER BY p.sku, w.warehouse_code,
                     CASE e.model_key
                         WHEN 'rolling_average_7d' THEN 1
                         WHEN 'rolling_average_14d' THEN 2
                         WHEN 'rolling_average_30d' THEN 3
                         WHEN 'arima_with_fallback' THEN 4
                         ELSE 5
                     END,
                     e.model_name
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()
        parameters = run["parameters"]
        if isinstance(parameters, str):
            try:
                parameters = json.loads(parameters)
            except json.JSONDecodeError:
                parameters = {}
        return {
            "run": dict(run),
            "protocol": (parameters or {}).get("evaluation_protocol"),
            "summary": (parameters or {}).get("evaluation_summary"),
            "better_by": (parameters or {}).get("better_by"),
            "data": [dict(row) for row in rows],
            "meta": {"total": total, "limit": limit, "offset": offset},
        }
    finally:
        conn.close()


@router.get("/runs/{run_id}/results")
def list_forecast_results(
    run_id: int,
    product_id: Optional[int] = Query(default=None, gt=0),
    warehouse_id: Optional[int] = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_permission("reports", "read")),
):
    conn = get_db()
    try:
        run = conn.execute(
            "SELECT id, model_name, source, started_at, completed_at, status, "
            "products_processed, error_message, parameters FROM forecast_runs WHERE id=?",
            (run_id,),
        ).fetchone()
        if run is None:
            raise HTTPException(status_code=404, detail="Forecast run not found")

        where = "WHERE fr.id=?"
        params = [run_id]
        if product_id is not None:
            where += " AND r.product_id=?"
            params.append(product_id)
        if warehouse_id is not None:
            where += " AND r.warehouse_id=?"
            params.append(warehouse_id)
        total = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM forecast_results r
            JOIN forecast_runs fr ON fr.id=r.run_id
            {where}
            """,
            params,
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT r.id, r.run_id, r.product_id, p.sku, p.name AS product_name,
                   r.warehouse_id, w.warehouse_code, w.name AS warehouse_name,
                   r.forecast_date, r.predicted_demand, r.model_name,
                   r.model_version, r.generated_at
            FROM forecast_results r
            JOIN forecast_runs fr ON fr.id=r.run_id
            JOIN products p ON p.id=r.product_id
            JOIN warehouses w ON w.id=r.warehouse_id
            {where}
            ORDER BY r.forecast_date, p.sku, w.warehouse_code,
                     CASE r.model_name
                         WHEN '7-day rolling average' THEN 1
                         WHEN '14-day rolling average' THEN 2
                         WHEN '30-day rolling average' THEN 3
                         WHEN 'ARIMA(1,1,1)' THEN 4
                         WHEN 'ARIMA(1,1,1) fallback' THEN 4
                         ELSE 5
                     END,
                     r.model_name
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()
        return {
            "run": dict(run),
            "data": [dict(row) for row in rows],
            "meta": {"total": total, "limit": limit, "offset": offset},
        }
    finally:
        conn.close()
