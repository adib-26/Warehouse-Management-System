"""High-value API contract tests using an isolated MySQL database."""

import csv
import importlib
import io
import os
import sys

import pytest
from fastapi.testclient import TestClient


APP_MODULES = (
    "main",
    "config",
    "database",
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
