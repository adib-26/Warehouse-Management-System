"""High-value API contract tests using an isolated MySQL database."""

import csv
from datetime import date, timedelta
import importlib
import io
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient


APP_MODULES = (
    "main",
    "config",
    "database",
    "forecasting_models",
    "file_utils",
    "security",
    "routes.attachments",
    "routes.admin",
    "routes.auth",
    "routes.customers",
    "routes.inbound",
    "routes.movements",
    "routes.outbound",
    "routes.products",
    "routes.forecasting",
    "routes.suppliers",
    "routes.warehouses",
    "routes",
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Create a new app instance backed by disposable data for every test."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv(
        "DATABASE_URL",
        os.environ.get(
            "DATABASE_URL",
            "mysql://novaledger:novaledger@127.0.0.1:3306/novaledger_test",
        ),
    )
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough-for-isolated-tests")
    monkeypatch.setenv("INITIAL_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "admin123")

    for module_name in APP_MODULES:
        sys.modules.pop(module_name, None)

    app = importlib.import_module("main").app
    with TestClient(app) as test_client:
        yield test_client


def auth_headers(client):
    response = client.post(
        "/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def create_product(client, headers, **overrides):
    payload = {
        "name": "Widget",
        "sku": "WIDGET-001",
        "category": "Hardware",
        "tags": "warehouse,featured",
        "description": "A stockable widget",
        "quantity": 5,
        "low_stock": 2,
    }
    payload.update(overrides)
    response = client.post("/v1/products", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def create_warehouse(client, headers, **overrides):
    payload = {
        "warehouse_code": "FORECAST-001",
        "name": "Forecast warehouse",
        "address": "1 Forecast Way",
    }
    payload.update(overrides)
    response = client.post("/v1/warehouses", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def seed_wms_demand(client, headers, sales, start_date=date(2024, 1, 1)):
    """Seed sparse daily demand directly; None deliberately means no row/zero day."""
    product = create_product(
        client,
        headers,
        name="Forecast widget",
        sku="FORECAST-001",
        quantity=1_000,
    )
    warehouse = create_warehouse(client, headers)
    rows = [
        (
            product["id"],
            warehouse["id"],
            (start_date + timedelta(days=offset)).isoformat(),
            quantity,
            "WMS",
        )
        for offset, quantity in enumerate(sales)
        if quantity is not None
    ]
    database = importlib.import_module("database")
    conn = database.get_db()
    try:
        conn.cursor().executemany(
            """
            INSERT INTO forecast_demand_history
                (product_id, warehouse_id, demand_date, quantity_sold, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    return product, warehouse


def parse_parameters(value):
    return value if isinstance(value, dict) else json.loads(value)


def test_authentication_blocks_anonymous_requests_and_returns_current_user(client):
    assert client.get("/v1/products").status_code == 401

    headers = auth_headers(client)
    response = client.get("/v1/auth/me", headers=headers)

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "admin"
    assert response.json()["permissions"]["products"]["write"] is True


def test_catalog_filters_facets_pagination_and_csv_export(client):
    headers = auth_headers(client)
    create_product(client, headers, name="=FORMULA", sku="SKU-ONE")
    create_product(
        client,
        headers,
        name="Cable",
        sku="SKU-TWO",
        category="Electrical",
        tags="featured,critical",
    )

    page = client.get("/v1/products?limit=1&offset=0", headers=headers)
    assert page.status_code == 200
    assert page.json()["meta"] == {"total": 2, "limit": 1, "offset": 0}

    filtered = client.get("/v1/products?category=electrical&tag=critical", headers=headers)
    assert filtered.status_code == 200
    assert [item["sku"] for item in filtered.json()["data"]] == ["SKU-TWO"]

    facets = client.get("/v1/products/facets", headers=headers)
    assert facets.status_code == 200
    assert facets.json() == {
        "categories": ["Electrical", "Hardware"],
        "tags": ["critical", "featured", "warehouse"],
    }

    exported = client.get("/v1/products/export?q=FORMULA", headers=headers)
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "products-" in exported.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(exported.text.removeprefix("\ufeff"))))
    assert rows[0][0:2] == ["SKU", "Name"]
    assert rows[1][0:2] == ["SKU-ONE", "'=FORMULA"]
    assert len(rows[1]) == 10


def test_inbound_and_outbound_keep_stock_and_movements_consistent(client):
    headers = auth_headers(client)
    product = create_product(client, headers, quantity=5, sku="FLOW-001")

    supplier = client.post("/v1/suppliers", headers=headers, json={"name": "North Supply"})
    assert supplier.status_code == 201, supplier.text
    inbound = client.post(
        "/v1/inbound-shipments",
        headers=headers,
        json={"product_id": product["id"], "supplier_id": supplier.json()["id"], "quantity": 3},
    )
    assert inbound.status_code == 201, inbound.text
    assert inbound.json()["quantity_after"] == 8

    customer = client.post("/v1/customers", headers=headers, json={"name": "Acme Retail"})
    assert customer.status_code == 201, customer.text
    outbound = client.post(
        "/v1/outbound-shipments",
        headers=headers,
        json={"product_id": product["id"], "customer_id": customer.json()["id"], "quantity": 6},
    )
    assert outbound.status_code == 201, outbound.text
    assert outbound.json()["quantity_after"] == 2

    oversell = client.post(
        "/v1/outbound-shipments",
        headers=headers,
        json={"product_id": product["id"], "customer_id": customer.json()["id"], "quantity": 3},
    )
    assert oversell.status_code in {400, 409}

    stored = client.get(f"/v1/products/{product['id']}", headers=headers)
    assert stored.status_code == 200
    assert stored.json()["quantity"] == 2

    movements = client.get(
        f"/v1/movements?product_id={product['id']}&limit=50", headers=headers
    )
    assert movements.status_code == 200
    assert [movement["delta"] for movement in movements.json()["data"]] == [-6, 3, 5]


def test_new_users_need_a_strong_password(client):
    headers = auth_headers(client)

    weak = client.post(
        "/v1/admin/users",
        headers=headers,
        json={"username": "weak-user", "password": "short", "role": "operator"},
    )
    assert weak.status_code == 422

    created = client.post(
        "/v1/admin/users",
        headers=headers,
        json={
            "username": "warehouse-user",
            "password": "a-long-test-password",
            "full_name": "Warehouse User",
            "role": "operator",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["username"] == "warehouse-user"


def test_only_manual_movements_can_be_undone(client):
    headers = auth_headers(client)
    product = create_product(client, headers, sku="UNDO-001", quantity=10)

    manual = client.post(
        "/v1/movements",
        headers=headers,
        json={"sku": product["sku"], "delta": -2, "reason": "Cycle count"},
    )
    assert manual.status_code == 201, manual.text
    assert manual.json()["source"] == "manual"

    undo = client.delete(f"/v1/movements/{manual.json()['id']}", headers=headers)
    assert undo.status_code == 204, undo.text
    assert client.get(f"/v1/products/{product['id']}", headers=headers).json()["quantity"] == 10

    supplier = client.post("/v1/suppliers", headers=headers, json={"name": "Undo Supply"})
    assert supplier.status_code == 201, supplier.text
    inbound = client.post(
        "/v1/inbound-shipments",
        headers=headers,
        json={"product_id": product["id"], "supplier_id": supplier.json()["id"], "quantity": 1},
    )
    assert inbound.status_code == 201, inbound.text

    movements = client.get(
        f"/v1/movements?product_id={product['id']}&limit=50", headers=headers
    ).json()["data"]
    inbound_movement = next(movement for movement in movements if movement["source"] == "inbound")
    protected = client.delete(f"/v1/movements/{inbound_movement['id']}", headers=headers)
    assert protected.status_code == 409
    assert client.get(f"/v1/products/{product['id']}", headers=headers).json()["quantity"] == 11


def test_final_active_admin_cannot_be_demoted_or_deactivated(client):
    headers = auth_headers(client)
    current_user = client.get("/v1/auth/me", headers=headers).json()["user"]

    demote_last = client.patch(
        f"/v1/admin/users/{current_user['id']}",
        headers=headers,
        json={"role": "operator"},
    )
    assert demote_last.status_code == 400
    assert "active administrator" in demote_last.json()["detail"]

    deactivate_last = client.patch(
        f"/v1/admin/users/{current_user['id']}",
        headers=headers,
        json={"active": False},
    )
    assert deactivate_last.status_code == 400

    second_admin = client.post(
        "/v1/admin/users",
        headers=headers,
        json={
            "username": "backup-admin",
            "password": "a-long-backup-password",
            "role": "admin",
        },
    )
    assert second_admin.status_code == 201, second_admin.text

    demote_with_backup = client.patch(
        f"/v1/admin/users/{current_user['id']}",
        headers=headers,
        json={"role": "operator"},
    )
    assert demote_with_backup.status_code == 200, demote_with_backup.text


def test_rolling_average_forecast_zero_fills_missing_days_and_records_parameters(client):
    headers = auth_headers(client)
    start_date = date(2024, 1, 1)
    product, warehouse = seed_wms_demand(
        client,
        headers,
        [7, None, None, None, None, None, 7],
        start_date,
    )

    response = client.post(
        "/v1/forecasts/rolling-average",
        headers=headers,
        json={
            "source": "WMS",
            "window_days": 7,
            "horizon_days": 2,
            "series_limit": 1,
            "as_of_date": (start_date + timedelta(days=6)).isoformat(),
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["series_processed"] == 1
    assert payload["predictions_written"] == 2
    assert payload["series_sample_truncated"] is False

    results = client.get(
        f"/v1/forecasts/runs/{payload['run_id']}/results", headers=headers
    )
    assert results.status_code == 200, results.text
    assert [float(row["predicted_demand"]) for row in results.json()["data"]] == [2.0, 2.0]
    assert {
        row["product_id"] for row in results.json()["data"]
    } == {product["id"]}
    assert {
        row["warehouse_id"] for row in results.json()["data"]
    } == {warehouse["id"]}

    run = results.json()["run"]
    parameters = parse_parameters(run["parameters"])
    assert parameters["resolved_as_of_date"] == "2024-01-07"
    assert parameters["series_limit"] == 1
    assert parameters["series_processed"] == 1
    assert parameters["predictions_written"] == 2


def test_arima_uses_recorded_fallback_for_short_history(client):
    headers = auth_headers(client)
    start_date = date(2024, 1, 1)
    seed_wms_demand(
        client,
        headers,
        [7, None, None, None, None, None, 7],
        start_date,
    )

    response = client.post(
        "/v1/forecasts/arima",
        headers=headers,
        json={
            "source": "WMS",
            "history_days": 90,
            "fallback_window_days": 7,
            "horizon_days": 2,
            "series_limit": 1,
            "max_arima_series": 1,
            "as_of_date": (start_date + timedelta(days=6)).isoformat(),
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["arima_series_processed"] == 0
    assert payload["fallback_series_processed"] == 1
    assert payload["fallback_reasons"] == {"insufficient_history": 1}

    results = client.get(
        f"/v1/forecasts/runs/{payload['run_id']}/results", headers=headers
    )
    assert results.status_code == 200, results.text
    assert [row["model_name"] for row in results.json()["data"]] == [
        "Rolling average (fallback)",
        "Rolling average (fallback)",
    ]
    assert [float(row["predicted_demand"]) for row in results.json()["data"]] == [2.0, 2.0]

    parameters = parse_parameters(results.json()["run"]["parameters"])
    assert parameters["max_arima_series"] == 1
    assert parameters["fallback_reasons"] == {"insufficient_history": 1}


def test_model_comparison_saves_all_models_for_the_same_holdout(client):
    headers = auth_headers(client)
    start_date = date(2024, 1, 1)
    sales = [None] * 104
    sales[0] = 10
    sales[100] = 4
    sales[103] = 0  # Establish the selected cutoff while preserving a zero day.
    seed_wms_demand(client, headers, sales, start_date)
    before = client.get("/v1/forecasts/runs", headers=headers).json()["meta"]["total"]

    response = client.post(
        "/v1/forecasts/compare",
        headers=headers,
        json={
            "source": "WMS",
            "history_days": 90,
            "horizon_days": 14,
            "series_limit": 1,
            "as_of_date": (start_date + timedelta(days=103)).isoformat(),
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["run_id"]
    assert payload["sampled_series"] == 1
    assert payload["observations_scored"] == 14
    assert payload["predictions_written"] == 56
    assert payload["arima_series_processed"] == 0
    assert payload["fallback_reasons"] == {"insufficient_nonzero_history": 1}
    assert payload["metrics"]["rolling_average_7d"] == {
        "mae": pytest.approx(0.2857),
        "rmse": pytest.approx(1.069),
        "wape_pct": 100.0,
    }
    assert payload["metrics"]["arima_with_fallback"] == payload["metrics"]["rolling_average_7d"]
    after = client.get("/v1/forecasts/runs", headers=headers).json()["meta"]["total"]
    assert after == before + 1

    saved = client.get(
        f"/v1/forecasts/runs/{payload['run_id']}/results?limit=100", headers=headers
    )
    assert saved.status_code == 200, saved.text
    data = saved.json()["data"]
    assert len(data) == 56
    assert {row["model_name"] for row in data} == {
        "7-day rolling average",
        "14-day rolling average",
        "30-day rolling average",
        "ARIMA(1,1,1) fallback",
    }
    assert {row["forecast_date"] for row in data} == {
        (start_date + timedelta(days=offset)).isoformat()
        for offset in range(90, 104)
    }
    assert all(row["generated_at"] for row in data)


def test_forecasts_require_reports_write_permission(client):
    admin_headers = auth_headers(client)
    created = client.post(
        "/v1/admin/users",
        headers=admin_headers,
        json={
            "username": "forecast-viewer",
            "password": "a-long-test-password",
            "role": "operator",
        },
    )
    assert created.status_code == 201, created.text
    login = client.post(
        "/v1/auth/login",
        json={"username": "forecast-viewer", "password": "a-long-test-password"},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['token']}"}

    assert client.get("/v1/forecasts/runs", headers=headers).status_code == 200
    assert client.post(
        "/v1/forecasts/rolling-average", headers=headers, json={"source": "WMS"}
    ).status_code == 403
    assert client.post(
        "/v1/forecasts/compare", headers=headers, json={"source": "WMS"}
    ).status_code == 403


def test_m5_forecasts_wait_for_the_import_lock(client):
    headers = auth_headers(client)
    database = importlib.import_module("database")
    conn = database.get_db()
    try:
        acquired = conn.execute(
            "SELECT GET_LOCK(?, 0) AS acquired", ("novaledger_m5_forecast_import",)
        ).fetchone()
        assert int(acquired["acquired"] or 0) == 1
        response = client.post(
            "/v1/forecasts/rolling-average", headers=headers, json={"source": "M5"}
        )
        assert response.status_code == 409
        assert "import is in progress" in response.json()["detail"]
    finally:
        conn.execute("SELECT RELEASE_LOCK(?)", ("novaledger_m5_forecast_import",))
        conn.close()
