"""Batch inventory APIs and the shared, lock-safe outbound allocator."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from database import IntegrityError, get_db
from schemas import BatchAllocationRequest, InventoryBatchCreate, InventoryBatchUpdate
from security import log_audit, require_permission


router = APIRouter()
CENT = Decimal("0.01")


def _decimal(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT)


def _utc_naive_datetime(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.replace(microsecond=0)


def _date_value(value):
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _batch_remaining_total(cur, product_id: int) -> Decimal:
    row = cur.execute(
        "SELECT COALESCE(SUM(remaining_quantity), 0) AS quantity "
        "FROM inventory_batches WHERE product_id=?",
        (product_id,),
    ).fetchone()
    return _decimal(row["quantity"] if row else 0)


def _ensure_reconciled(cur, product_id: int, product_quantity=None) -> Decimal:
    if product_quantity is None:
        row = cur.execute(
            "SELECT quantity FROM products WHERE id=? FOR UPDATE",
            (product_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Product not found")
        product_quantity = row["quantity"]
    product_total = _decimal(product_quantity)
    batch_total = _batch_remaining_total(cur, product_id)
    if product_total != batch_total:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Batch stock is out of balance for product {product_id}: "
                f"product quantity is {product_total}, batch balance is {batch_total}. "
                f"Use POST /api/products/{product_id}/batches/reconcile before allocating stock."
            ),
        )
    return batch_total


def _allocation_rows(cur, outbound_id: int):
    return cur.execute(
        """
        SELECT a.id, a.outbound_id, a.batch_id, a.quantity, a.created_at,
               b.batch_number, b.expiry_date, b.warehouse_id, w.warehouse_code
        FROM outbound_batch_allocations a
        JOIN inventory_batches b ON b.id=a.batch_id
        LEFT JOIN warehouses w ON w.id=b.warehouse_id
        WHERE a.outbound_id=?
        ORDER BY a.id
        """,
        (outbound_id,),
    ).fetchall()


def allocate_outbound_shipment(cur, outbound_id: int, requested_method="AUTO") -> dict:
    """Allocate an outbound shipment and decrement product and lot balances.

    Callers must keep this function inside the outbound transaction. Product
    rows are locked before eligible batch rows, so concurrent orders for the
    same product serialize before they can consume the same lot balance. A
    complete prior allocation is idempotent; ambiguous partial allocations
    are rejected so stock is never deducted twice.
    """

    method = (requested_method or "AUTO").upper()
    if method not in {"AUTO", "FIFO", "FEFO"}:
        raise HTTPException(status_code=422, detail="method must be AUTO, FIFO, or FEFO")

    shipment = cur.execute(
        """
        SELECT ob.id, ob.product_id, ob.warehouse_id, ob.quantity, ob.created_at,
               p.quantity AS product_quantity, p.batch_tracking_enabled_at,
               p.is_forecast_test, p.deleted
        FROM outbound_shipments ob
        JOIN products p ON p.id=ob.product_id
        WHERE ob.id=?
        FOR UPDATE
        """,
        (outbound_id,),
    ).fetchone()
    if shipment is None:
        raise HTTPException(status_code=404, detail="Outbound shipment not found")
    if not shipment["batch_tracking_enabled_at"]:
        raise HTTPException(
            status_code=409,
            detail="This product is not batch tracked.",
        )
    if shipment["is_forecast_test"] or shipment["deleted"]:
        raise HTTPException(status_code=404, detail="Operational outbound shipment not found")
    if shipment["warehouse_id"] is None:
        raise HTTPException(
            status_code=409,
            detail="Outbound shipment has no warehouse for batch allocation.",
        )
    product_id = int(shipment["product_id"])
    _ensure_reconciled(cur, product_id, shipment["product_quantity"])
    requested = _decimal(shipment["quantity"])
    existing = cur.execute(
        "SELECT COALESCE(SUM(quantity), 0) AS quantity "
        "FROM outbound_batch_allocations WHERE outbound_id=?",
        (outbound_id,),
    ).fetchone()
    already_allocated = _decimal(existing["quantity"] if existing else 0)
    if already_allocated > requested:
        raise HTTPException(
            status_code=409,
            detail="Existing batch allocations exceed the outbound quantity.",
        )
    if already_allocated == requested:
        allocations = _allocation_rows(cur, outbound_id)
        return {
            "outbound_id": outbound_id,
            "method": "already_allocated",
            "quantity": requested,
            "allocated_quantity": requested,
            "remaining_quantity": Decimal("0.00"),
            "allocations": [dict(row) for row in allocations],
        }
    if already_allocated > 0:
        raise HTTPException(
            status_code=409,
            detail="Partial batch allocations need reconciliation before retrying.",
        )
    active_warehouse = cur.execute(
        "SELECT id FROM warehouses WHERE id=? AND active=1 AND is_forecast_test=0",
        (shipment["warehouse_id"],),
    ).fetchone()
    if active_warehouse is None:
        raise HTTPException(status_code=409, detail="Outbound warehouse is inactive or unavailable.")
    tracking_started = str(shipment["batch_tracking_enabled_at"])
    shipment_created = str(shipment["created_at"])
    if shipment_created < tracking_started:
        raise HTTPException(
            status_code=409,
            detail=(
                "This shipment predates batch tracking and cannot be allocated "
                "against current batch balances."
            ),
        )
    required = requested
    if _decimal(shipment["product_quantity"]) < requested:
        raise HTTPException(status_code=409, detail="Insufficient product stock for this outbound shipment.")

    selected_method = method
    if required > 0:
        # Always lock in FEFO order first. FIFO callers reorder these locked
        # rows in memory, preserving the same safe lock acquisition order.
        batches = cur.execute(
            """
            SELECT id, batch_number, remaining_quantity, received_date, expiry_date
            FROM inventory_batches
            WHERE product_id=? AND warehouse_id=? AND status='available'
              AND remaining_quantity>0
              AND (expiry_date IS NULL OR expiry_date>=UTC_DATE())
            ORDER BY (expiry_date IS NULL), expiry_date, received_date, id
            FOR UPDATE
            """,
            (product_id, shipment["warehouse_id"]),
        ).fetchall()
        has_expiry = any(batch["expiry_date"] is not None for batch in batches)
        if selected_method == "AUTO":
            selected_method = "FEFO" if has_expiry else "FIFO"
        if selected_method == "FIFO":
            batches.sort(key=lambda batch: (str(batch["received_date"]), int(batch["id"])))
        else:
            batches.sort(
                key=lambda batch: (
                    batch["expiry_date"] is None,
                    str(batch["expiry_date"] or "9999-12-31"),
                    str(batch["received_date"]),
                    int(batch["id"]),
                )
            )

        available = sum((_decimal(batch["remaining_quantity"]) for batch in batches), Decimal("0"))
        if available < required:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Insufficient unexpired, unblocked batch stock: "
                    f"{available} available, {required} required."
                ),
            )

        remainder = required
        for batch in batches:
            if remainder <= 0:
                break
            balance = _decimal(batch["remaining_quantity"])
            taken = min(balance, remainder)
            updated_balance = balance - taken
            cur.execute(
                "UPDATE inventory_batches SET remaining_quantity=?, status=? "
                "WHERE id=? AND remaining_quantity>=? AND status='available'",
                (
                    updated_balance,
                    "depleted" if updated_balance == 0 else "available",
                    batch["id"],
                    taken,
                ),
            )
            if cur.rowcount != 1:
                raise HTTPException(
                    status_code=409,
                    detail="A batch changed during allocation; retry the outbound order.",
                )
            cur.execute(
                "INSERT INTO outbound_batch_allocations (outbound_id, batch_id, quantity) "
                "VALUES (?, ?, ?)",
                (outbound_id, batch["id"], taken),
            )
            cur.execute(
                """
                INSERT INTO movements
                    (product_id, action_type, delta, reason, source, batch_id, warehouse_id)
                VALUES (?, 'STOCK_OUT', ?, ?, 'batch-allocation', ?, ?)
                """,
                (
                    product_id,
                    -taken,
                    f"Outbound #{outbound_id} allocated from batch {batch['batch_number']}",
                    batch["id"],
                    shipment["warehouse_id"],
                ),
            )
            remainder -= taken

        if remainder != 0:
            raise HTTPException(
                status_code=409,
                detail="Batch stock changed during allocation; retry the outbound order.",
            )

    cur.execute(
        "UPDATE products SET quantity=quantity-?, updated_at=UTC_TIMESTAMP() "
        "WHERE id=? AND quantity>=?",
        (requested, product_id, requested),
    )
    if cur.rowcount != 1:
        raise HTTPException(status_code=409, detail="Product stock changed; retry the outbound order.")
    product_quantity = cur.execute(
        "SELECT quantity FROM products WHERE id=?",
        (product_id,),
    ).fetchone()["quantity"]
    _ensure_reconciled(cur, product_id, product_quantity)
    allocations = _allocation_rows(cur, outbound_id)
    total_allocated = sum((_decimal(row["quantity"]) for row in allocations), Decimal("0"))
    return {
        "outbound_id": outbound_id,
        "method": selected_method if required > 0 else "already_allocated",
        "quantity": requested,
        "allocated_quantity": total_allocated,
        "remaining_quantity": requested - total_allocated,
        "allocations": [dict(row) for row in allocations],
    }


def _status_for_response(row, today: date):
    if row["status"] == "available" and row["expiry_date"]:
        expiry = date.fromisoformat(str(row["expiry_date"]))
        if expiry < today:
            return "expired"
    return row["status"]


def _batch_select_sql(where_clause: str):
    return f"""
        SELECT b.id, b.batch_number, b.product_id, p.sku, p.name AS product_name,
               p.is_forecast_test, p.deleted AS product_deleted,
               p.quantity AS product_quantity,
               COALESCE(t.batch_remaining_total, 0) AS batch_remaining_total,
               b.warehouse_id, w.warehouse_code, w.name AS warehouse_name,
               COALESCE(w.active, 0) AS warehouse_active,
               b.supplier_id, s.name AS supplier_name, b.received_quantity,
               b.remaining_quantity, b.manufacturing_date, b.expiry_date,
               b.received_date, b.status
        FROM inventory_batches b
        JOIN products p ON p.id=b.product_id
        LEFT JOIN (
            SELECT product_id, SUM(remaining_quantity) AS batch_remaining_total
            FROM inventory_batches GROUP BY product_id
        ) t ON t.product_id=b.product_id
        LEFT JOIN warehouses w ON w.id=b.warehouse_id
        LEFT JOIN suppliers s ON s.id=b.supplier_id
        {where_clause}
    """


def _public_batch(row):
    result = dict(row)
    result["status"] = _status_for_response(row, datetime.now(timezone.utc).date())
    result["is_expired"] = bool(
        result["expiry_date"]
        and date.fromisoformat(str(result["expiry_date"]))
        < datetime.now(timezone.utc).date()
    )
    result["allocatable"] = bool(
        result["status"] == "available"
        and not result["is_expired"]
        and _decimal(result["remaining_quantity"]) > 0
        and result["warehouse_active"]
        and not result["is_forecast_test"]
        and not result["product_deleted"]
    )
    product_total = _decimal(result["product_quantity"])
    batch_total = _decimal(result["batch_remaining_total"])
    result["reconciliation_difference"] = product_total - batch_total
    result["reconciled"] = product_total == batch_total
    return result


def _load_batch(cur, batch_id: int, include_forecast_test: bool):
    filter_sql = " AND p.is_forecast_test=?" if include_forecast_test else " AND p.is_forecast_test=0"
    params = [batch_id]
    if include_forecast_test:
        params.append(1)
    row = cur.execute(
        _batch_select_sql("WHERE b.id=?" + filter_sql),
        params,
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return _public_batch(row)


@router.get("/batches")
def list_batches(
    product_id: Optional[int] = Query(default=None, gt=0),
    warehouse_id: Optional[int] = Query(default=None, gt=0),
    status: Optional[Literal["available", "blocked", "expired", "depleted"]] = None,
    expiry_before: Optional[date] = None,
    expiry_after: Optional[date] = None,
    include_forecast_test: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_permission("stock", "read")),
):
    conn = get_db()
    try:
        conditions = ["p.is_forecast_test=?"]
        params = [1 if include_forecast_test else 0]
        if product_id is not None:
            conditions.append("b.product_id=?")
            params.append(product_id)
        if warehouse_id is not None:
            conditions.append("b.warehouse_id=?")
            params.append(warehouse_id)
        if status == "expired":
            conditions.append(
                "(b.status='expired' OR b.expiry_date<UTC_DATE())"
            )
        elif status:
            conditions.append("b.status=?")
            params.append(status)
            if status == "available":
                conditions.extend(
                    (
                        "b.remaining_quantity>0",
                        "(b.expiry_date IS NULL OR b.expiry_date>=UTC_DATE())",
                        "EXISTS (SELECT 1 FROM warehouses wb WHERE wb.id=b.warehouse_id AND wb.active=1)",
                    )
                )
        if expiry_before is not None:
            conditions.append("b.expiry_date<=?")
            params.append(expiry_before.isoformat())
        if expiry_after is not None:
            conditions.append("b.expiry_date>=?")
            params.append(expiry_after.isoformat())
        where = "WHERE " + " AND ".join(conditions)
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM inventory_batches b "
            "JOIN products p ON p.id=b.product_id " + where,
            params,
        ).fetchone()["n"]
        rows = conn.execute(
            _batch_select_sql(where)
            + " ORDER BY (b.expiry_date IS NULL), b.expiry_date, b.received_date, b.id "
            + "LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return {
            "data": [_public_batch(row) for row in rows],
            "meta": {"total": int(total), "limit": limit, "offset": offset},
        }
    finally:
        conn.close()


@router.get("/batches/reconciliation")
def list_batch_reconciliation(
    include_forecast_test: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_permission("reports", "read")),
):
    conn = get_db()
    try:
        test_filter = 1 if include_forecast_test else 0
        total = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM (
                SELECT p.id
                FROM products p
                LEFT JOIN inventory_batches b ON b.product_id=p.id
                WHERE p.batch_tracking_enabled_at IS NOT NULL
                  AND p.is_forecast_test=?
                GROUP BY p.id, p.quantity
                HAVING ROUND(p.quantity, 2) <>
                       ROUND(COALESCE(SUM(b.remaining_quantity), 0), 2)
            ) mismatches
            """,
            (test_filter,),
        ).fetchone()["n"]
        rows = conn.execute(
            """
            SELECT p.id AS product_id, p.sku, p.name AS product_name,
                   p.quantity AS product_quantity,
                   COALESCE(SUM(b.remaining_quantity), 0) AS batch_remaining_total,
                   p.quantity-COALESCE(SUM(b.remaining_quantity), 0)
                       AS reconciliation_difference,
                   p.batch_tracking_enabled_at,
                   (ROUND(p.quantity, 2)=ROUND(COALESCE(SUM(b.remaining_quantity), 0), 2))
                       AS reconciled
            FROM products p
            LEFT JOIN inventory_batches b ON b.product_id=p.id
            WHERE p.batch_tracking_enabled_at IS NOT NULL AND p.is_forecast_test=?
            GROUP BY p.id, p.sku, p.name, p.quantity, p.batch_tracking_enabled_at
            HAVING reconciled=0
            ORDER BY ABS(reconciliation_difference) DESC, p.sku, p.id
            LIMIT ? OFFSET ?
            """,
            (test_filter, limit, offset),
        ).fetchall()
        # The summary count is deliberately grouped by product, matching the
        # row-level reconciliation report returned above.
        return {
            "data": [dict(row) for row in rows],
            "meta": {"total": int(total), "limit": limit, "offset": offset},
        }
    finally:
        conn.close()


@router.post("/products/{product_id}/batches/reconcile")
def reconcile_product_batch_balance(
    product_id: int,
    user: dict = Depends(require_permission("stock", "write")),
):
    """Set product-level on-hand to the sum of its batch balances."""
    conn = get_db()
    try:
        conn.execute("START TRANSACTION")
        cur = conn.cursor()
        product = cur.execute(
            "SELECT id, sku, name, quantity, batch_tracking_enabled_at, is_forecast_test "
            "FROM products WHERE id=? AND deleted=0 FOR UPDATE",
            (product_id,),
        ).fetchone()
        if product is None or product["is_forecast_test"]:
            raise HTTPException(status_code=404, detail="Operational product not found")
        if not product["batch_tracking_enabled_at"]:
            raise HTTPException(status_code=409, detail="Product is not batch tracked")

        product_quantity = _decimal(product["quantity"])
        batch_quantity = _batch_remaining_total(cur, product_id)
        adjustment = batch_quantity - product_quantity
        if adjustment:
            cur.execute(
                "UPDATE products SET quantity=?, updated_at=UTC_TIMESTAMP() WHERE id=?",
                (batch_quantity, product_id),
            )
            action_type = "STOCK_IN" if adjustment > 0 else "STOCK_OUT"
            cur.execute(
                "INSERT INTO movements (product_id, action_type, delta, reason, source) "
                "VALUES (?, ?, ?, ?, 'batch-reconciliation')",
                (
                    product_id,
                    action_type,
                    adjustment,
                    "Aligned product stock with remaining batch balances",
                ),
            )
            log_audit(
                cur,
                user,
                "RECONCILE",
                "stock",
                "product",
                product_id,
                f"Reconciled {product['sku']} to {batch_quantity} units in batch balances",
            )
        conn.commit()
        return {
            "product_id": product_id,
            "sku": product["sku"],
            "previous_product_quantity": product_quantity,
            "batch_remaining_total": batch_quantity,
            "adjustment": adjustment,
            "reconciled": True,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.get("/products/{product_id}/batches")
def list_product_batches(
    product_id: int,
    include_forecast_test: bool = False,
    status: Optional[Literal["available", "blocked", "expired", "depleted"]] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_permission("stock", "read")),
):
    conn = get_db()
    try:
        product = conn.execute(
            "SELECT id, sku, name, quantity, is_forecast_test, batch_tracking_enabled_at "
            "FROM products WHERE id=? AND deleted=0",
            (product_id,),
        ).fetchone()
        if product is None or bool(product["is_forecast_test"]) != include_forecast_test:
            raise HTTPException(status_code=404, detail="Product not found")
        conditions = ["b.product_id=?"]
        params = [product_id]
        if status == "expired":
            conditions.append(
                "(b.status='expired' OR b.expiry_date<UTC_DATE())"
            )
        elif status:
            conditions.append("b.status=?")
            params.append(status)
            if status == "available":
                conditions.extend(
                    (
                        "b.remaining_quantity>0",
                        "(b.expiry_date IS NULL OR b.expiry_date>=UTC_DATE())",
                        "EXISTS (SELECT 1 FROM warehouses wb WHERE wb.id=b.warehouse_id AND wb.active=1)",
                    )
                )
        where = "WHERE " + " AND ".join(conditions)
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM inventory_batches b " + where,
            params,
        ).fetchone()["n"]
        rows = conn.execute(
            _batch_select_sql(where)
            + " ORDER BY (b.expiry_date IS NULL), b.expiry_date, b.received_date, b.id "
            + "LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        batch_total = _batch_remaining_total(conn.cursor(), product_id)
        product_total = _decimal(product["quantity"])
        return {
            "product": dict(product),
            "reconciliation": {
                "product_quantity": product_total,
                "batch_remaining_total": batch_total,
                "difference": product_total - batch_total,
                "balanced": product_total == batch_total,
            },
            "data": [_public_batch(row) for row in rows],
            "meta": {"total": int(total), "limit": limit, "offset": offset},
        }
    finally:
        conn.close()


@router.get("/batches/{batch_id}")
def get_batch(
    batch_id: int,
    include_forecast_test: bool = False,
    user: dict = Depends(require_permission("stock", "read")),
):
    conn = get_db()
    try:
        row = conn.cursor()
        return _load_batch(row, batch_id, include_forecast_test)
    finally:
        conn.close()


@router.post("/batches", status_code=201)
def create_batch(
    request: InventoryBatchCreate,
    response: Response,
    user: dict = Depends(require_permission("stock", "write")),
):
    conn = get_db()
    try:
        conn.execute("START TRANSACTION")
        cur = conn.cursor()
        product = cur.execute(
            "SELECT id, name, sku, quantity, is_forecast_test, batch_tracking_enabled_at "
            "FROM products WHERE id=? AND deleted=0 AND archived=0 FOR UPDATE",
            (request.product_id,),
        ).fetchone()
        if product is None or product["is_forecast_test"]:
            raise HTTPException(status_code=404, detail="Operational product not found")
        warehouse = cur.execute(
            "SELECT id, warehouse_code FROM warehouses "
            "WHERE id=? AND active=1 AND is_forecast_test=0",
            (request.warehouse_id,),
        ).fetchone()
        if warehouse is None:
            raise HTTPException(status_code=404, detail="Warehouse not found or inactive")
        supplier = None
        if request.supplier_id is not None:
            supplier = cur.execute(
                "SELECT id, name FROM suppliers WHERE id=? AND deleted=0",
                (request.supplier_id,),
            ).fetchone()
            if supplier is None:
                raise HTTPException(status_code=404, detail="Supplier not found")

        product_quantity = _decimal(product["quantity"])
        previous_total = _batch_remaining_total(cur, request.product_id)
        tracked = bool(product["batch_tracking_enabled_at"])
        if tracked and previous_total != product_quantity:
            raise HTTPException(
                status_code=409,
                detail="Reconcile existing batch balances before receiving another batch.",
            )
        if tracked and request.opening_balance:
            raise HTTPException(
                status_code=409,
                detail="opening_balance can only be used to enable tracking on the first batch.",
            )

        remaining = _decimal(
            request.received_quantity
            if request.remaining_quantity is None
            else request.remaining_quantity
        )
        received = _decimal(request.received_quantity)
        opening = not tracked and product_quantity > 0
        if opening and not request.opening_balance:
            raise HTTPException(
                status_code=409,
                detail=(
                    "This product already has untracked stock. To convert it to batch "
                    "tracking, create an opening batch with opening_balance=true and "
                    "quantities matching the current product quantity."
                ),
            )
        if request.opening_balance and not opening:
            raise HTTPException(
                status_code=409,
                detail="opening_balance is only valid for existing untracked stock.",
            )
        if opening and (received != product_quantity or remaining != product_quantity):
            raise HTTPException(
                status_code=422,
                detail="Opening batch received_quantity and remaining_quantity must equal current product quantity.",
            )

        expiry = request.expiry_date
        manufacturing = request.manufacturing_date
        if expiry and manufacturing and expiry < manufacturing:
            raise HTTPException(
                status_code=422,
                detail="expiry_date cannot be earlier than manufacturing_date",
            )
        status = request.status
        if remaining == 0:
            status = "depleted"
        elif expiry is not None and expiry < datetime.now(timezone.utc).date():
            status = "expired"
        received_date = _utc_naive_datetime(
            request.received_date or datetime.now(timezone.utc)
        )
        if received_date > datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0):
            raise HTTPException(status_code=422, detail="received_date cannot be in the future")
        if manufacturing and manufacturing > received_date.date():
            raise HTTPException(
                status_code=422,
                detail="manufacturing_date cannot be after received_date",
            )
        try:
            cur.execute(
                """
                INSERT INTO inventory_batches
                    (batch_number, product_id, warehouse_id, supplier_id,
                     received_quantity, remaining_quantity, manufacturing_date,
                     expiry_date, received_date, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.batch_number.strip(),
                    request.product_id,
                    request.warehouse_id,
                    request.supplier_id,
                    received,
                    remaining,
                    manufacturing,
                    expiry,
                    received_date,
                    status,
                ),
            )
        except IntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="Batch number already exists for this product.",
            ) from exc
        batch_id = int(cur.lastrowid)
        increment = Decimal("0.00") if opening else remaining
        if not tracked:
            cur.execute(
                "UPDATE products SET batch_tracking_enabled_at=UTC_TIMESTAMP(), "
                "quantity=quantity+?, updated_at=UTC_TIMESTAMP() WHERE id=?",
                (increment, request.product_id),
            )
        elif increment:
            cur.execute(
                "UPDATE products SET quantity=quantity+?, updated_at=UTC_TIMESTAMP() "
                "WHERE id=?",
                (increment, request.product_id),
            )
        new_product_quantity = cur.execute(
            "SELECT quantity FROM products WHERE id=?",
            (request.product_id,),
        ).fetchone()["quantity"]
        if increment:
            cur.execute(
                """
                INSERT INTO movements
                    (product_id, action_type, delta, reason, source, batch_id, warehouse_id)
                VALUES (?, 'STOCK_IN', ?, ?, 'batch-receipt', ?, ?)
                """,
                (
                    request.product_id,
                    increment,
                    f"Received batch {request.batch_number.strip()}",
                    batch_id,
                    request.warehouse_id,
                ),
            )
        _ensure_reconciled(cur, request.product_id, new_product_quantity)
        log_audit(
            cur,
            user,
            "STOCK_IN" if increment else "BATCH_TRACKING_ENABLED",
            "stock",
            "inventory_batch",
            batch_id,
            (
                f"Received {increment} units into batch {request.batch_number.strip()}"
                if increment
                else f"Enabled batch tracking for existing stock in {request.batch_number.strip()}"
            ),
        )
        conn.commit()
        response.headers["Location"] = f"/api/batches/{batch_id}"
        return _load_batch(cur, batch_id, include_forecast_test=False)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.put("/batches/{batch_id}")
def update_batch(
    batch_id: int,
    request: InventoryBatchUpdate,
    user: dict = Depends(require_permission("stock", "write")),
):
    fields = request.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=422, detail="At least one batch field must be provided")
    for field_name in (
        "batch_number",
        "warehouse_id",
        "received_quantity",
        "remaining_quantity",
        "received_date",
        "status",
    ):
        if field_name in fields and fields[field_name] is None:
            raise HTTPException(status_code=422, detail=f"{field_name} cannot be null")
    conn = get_db()
    try:
        cur = conn.cursor()
        # Resolve the product before START TRANSACTION. Under REPEATABLE READ a
        # transaction's snapshot comes from its first plain read; taking it
        # here, before the product lock, would hide allocations committed while
        # this request waited for that lock. START TRANSACTION discards it.
        identity = cur.execute(
            "SELECT product_id FROM inventory_batches WHERE id=?",
            (batch_id,),
        ).fetchone()
        if identity is None:
            raise HTTPException(status_code=404, detail="Batch not found")
        conn.execute("START TRANSACTION")
        product = cur.execute(
            "SELECT id, quantity, is_forecast_test, batch_tracking_enabled_at "
            "FROM products WHERE id=? FOR UPDATE",
            (identity["product_id"],),
        ).fetchone()
        if product is None or product["is_forecast_test"]:
            raise HTTPException(status_code=404, detail="Batch not found")
        batch = cur.execute(
            "SELECT * FROM inventory_batches WHERE id=? FOR UPDATE",
            (batch_id,),
        ).fetchone()
        allocation_totals = cur.execute(
            "SELECT COALESCE(SUM(quantity), 0) AS allocated_quantity "
            "FROM outbound_batch_allocations WHERE batch_id=?",
            (batch_id,),
        ).fetchone()
        allocated_quantity = _decimal(allocation_totals["allocated_quantity"])
        if allocated_quantity > 0:
            locked_fields = {
                "batch_number": batch["batch_number"],
                "warehouse_id": batch["warehouse_id"],
                "supplier_id": batch["supplier_id"],
                "manufacturing_date": _date_value(batch["manufacturing_date"]),
                "received_date": _utc_naive_datetime(batch["received_date"]),
            }
            for field_name, current_value in locked_fields.items():
                if field_name not in fields:
                    continue
                requested_value = fields[field_name]
                if field_name == "received_date" and requested_value is not None:
                    requested_value = _utc_naive_datetime(requested_value)
                elif field_name == "manufacturing_date" and requested_value is not None:
                    requested_value = _date_value(requested_value)
                if requested_value != current_value:
                    raise HTTPException(
                        status_code=409,
                        detail=f"{field_name} is locked after this batch has been allocated.",
                    )

        if "warehouse_id" in fields and fields["warehouse_id"] is not None:
            warehouse = cur.execute(
                "SELECT id FROM warehouses WHERE id=? AND active=1 AND is_forecast_test=0",
                (fields["warehouse_id"],),
            ).fetchone()
            if warehouse is None:
                raise HTTPException(status_code=404, detail="Warehouse not found or inactive")
        if "supplier_id" in fields and fields["supplier_id"] is not None:
            supplier = cur.execute(
                "SELECT id FROM suppliers WHERE id=? AND deleted=0",
                (fields["supplier_id"],),
            ).fetchone()
            if supplier is None:
                raise HTTPException(status_code=404, detail="Supplier not found")
        if fields.get("received_date") is None and "received_date" in fields:
            raise HTTPException(status_code=422, detail="received_date cannot be null")

        received_date = _utc_naive_datetime(
            fields.get("received_date", batch["received_date"])
        )
        if received_date > datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0):
            raise HTTPException(status_code=422, detail="received_date cannot be in the future")

        new_received = _decimal(fields.get("received_quantity", batch["received_quantity"]))
        new_remaining = _decimal(fields.get("remaining_quantity", batch["remaining_quantity"]))
        if new_remaining > new_received:
            raise HTTPException(
                status_code=422,
                detail="remaining_quantity cannot exceed received_quantity",
            )
        if new_remaining + allocated_quantity > new_received:
            raise HTTPException(
                status_code=422,
                detail="received_quantity cannot be lower than allocated plus remaining quantity.",
            )
        manufacturing = _date_value(
            fields.get("manufacturing_date", batch["manufacturing_date"])
        )
        expiry = _date_value(fields.get("expiry_date", batch["expiry_date"]))
        if manufacturing and expiry and expiry < manufacturing:
            raise HTTPException(
                status_code=422,
                detail="expiry_date cannot be earlier than manufacturing_date",
            )
        if manufacturing and manufacturing > received_date.date():
            raise HTTPException(
                status_code=422,
                detail="manufacturing_date cannot be after received_date",
            )
        status = fields.get("status", batch["status"])
        if new_remaining == 0:
            status = "depleted"
        elif expiry and expiry < datetime.now(timezone.utc).date():
            status = "expired"
        elif batch["status"] == "depleted" and "status" not in fields:
            status = "available"
        if status == "depleted" and new_remaining > 0:
            raise HTTPException(
                status_code=422,
                detail="A depleted batch must have zero remaining_quantity",
            )
        warehouse_id = fields.get("warehouse_id", batch["warehouse_id"])
        if status == "available" and warehouse_id is None:
            raise HTTPException(
                status_code=422,
                detail="An available batch must have a warehouse_id",
            )
        if status == "available":
            warehouse = cur.execute(
                "SELECT id FROM warehouses WHERE id=? AND active=1 AND is_forecast_test=0",
                (warehouse_id,),
            ).fetchone()
            if warehouse is None:
                raise HTTPException(
                    status_code=409,
                    detail="An available batch must belong to an active warehouse.",
                )

        update_fields = {
            "batch_number": fields.get("batch_number", batch["batch_number"]),
            "warehouse_id": warehouse_id,
            "supplier_id": fields.get("supplier_id", batch["supplier_id"]),
            "received_quantity": new_received,
            "remaining_quantity": new_remaining,
            "manufacturing_date": manufacturing,
            "expiry_date": expiry,
            "received_date": received_date,
            "status": status,
        }
        try:
            cur.execute(
                """
                UPDATE inventory_batches
                SET batch_number=?, warehouse_id=?, supplier_id=?, received_quantity=?,
                    remaining_quantity=?, manufacturing_date=?, expiry_date=?,
                    received_date=?, status=?
                WHERE id=?
                """,
                (
                    update_fields["batch_number"].strip(),
                    update_fields["warehouse_id"],
                    update_fields["supplier_id"],
                    update_fields["received_quantity"],
                    update_fields["remaining_quantity"],
                    update_fields["manufacturing_date"],
                    update_fields["expiry_date"],
                    update_fields["received_date"],
                    update_fields["status"],
                    batch_id,
                ),
            )
        except IntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="Batch number already exists for this product.",
            ) from exc

        delta = new_remaining - _decimal(batch["remaining_quantity"])
        if delta:
            cur.execute(
                "UPDATE products SET quantity=quantity+?, updated_at=UTC_TIMESTAMP() "
                "WHERE id=? AND quantity+?>=0",
                (delta, identity["product_id"], delta),
            )
            if cur.rowcount != 1:
                raise HTTPException(status_code=409, detail="Product stock changed; retry the batch update.")
            movement_action = "STOCK_IN" if delta > 0 else "STOCK_OUT"
            cur.execute(
                """
                INSERT INTO movements
                    (product_id, action_type, delta, reason, source, batch_id, warehouse_id)
                VALUES (?, ?, ?, ?, 'batch-adjustment', ?, ?)
                """,
                (
                    identity["product_id"],
                    movement_action,
                    delta,
                    f"Adjusted batch {update_fields['batch_number'].strip()} remaining quantity",
                    batch_id,
                    update_fields["warehouse_id"],
                ),
            )
        new_product_quantity = cur.execute(
            "SELECT quantity FROM products WHERE id=?",
            (identity["product_id"],),
        ).fetchone()["quantity"]
        _ensure_reconciled(cur, identity["product_id"], new_product_quantity)
        log_audit(
            cur,
            user,
            "UPDATE",
            "stock",
            "inventory_batch",
            batch_id,
            f"Updated batch {update_fields['batch_number'].strip()}",
        )
        conn.commit()
        return _load_batch(cur, batch_id, include_forecast_test=False)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.post("/outbound/{outbound_id}/allocate")
def allocate_outbound(
    outbound_id: int,
    request: BatchAllocationRequest = BatchAllocationRequest(),
    user: dict = Depends(require_permission("outbound", "write")),
):
    conn = get_db()
    try:
        conn.execute("START TRANSACTION")
        cur = conn.cursor()
        result = allocate_outbound_shipment(cur, outbound_id, request.method)
        if result["method"] != "already_allocated":
            log_audit(
                cur,
                user,
                "ALLOCATE",
                "outbound",
                "outbound_shipment",
                outbound_id,
                f"Allocated outbound #{outbound_id} using {result['method']}",
            )
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.get("/outbound/{outbound_id}/allocations")
def list_outbound_allocations(
    outbound_id: int,
    user: dict = Depends(require_permission("outbound", "read")),
):
    conn = get_db()
    try:
        outbound = conn.execute(
            "SELECT ob.id, ob.product_id, ob.warehouse_id, ob.quantity, p.sku, p.name "
            "FROM outbound_shipments ob JOIN products p ON p.id=ob.product_id "
            "WHERE ob.id=? AND p.is_forecast_test=0",
            (outbound_id,),
        ).fetchone()
        if outbound is None:
            raise HTTPException(status_code=404, detail="Outbound shipment not found")
        rows = _allocation_rows(conn.cursor(), outbound_id)
        total = sum((_decimal(row["quantity"]) for row in rows), Decimal("0"))
        return {
            "outbound": dict(outbound),
            "allocated_quantity": total,
            "remaining_to_allocate": _decimal(outbound["quantity"]) - total,
            "data": [dict(row) for row in rows],
        }
    finally:
        conn.close()
