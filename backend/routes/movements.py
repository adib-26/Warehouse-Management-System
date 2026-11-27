from fastapi import APIRouter, Depends, HTTPException, Query, Response
from database import get_db
from schemas import MovementCreate
from security import require_permission, log_audit
from typing import Optional
from decimal import Decimal

router = APIRouter()


@router.get("")
def list_movements(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    action_type: Optional[str] = None,
    product_id: Optional[int] = None,
    user: dict = Depends(require_permission("reports", "read")),
):
    conn = get_db()
    cur = conn.cursor()

    # Keep the M5 test catalog out of operational reports and controls.
    where = "WHERE p.is_forecast_test=0"
    params = []

    if action_type:
        where += " AND m.action_type = ?"
        params.append(action_type.upper())

    if product_id:
        where += " AND m.product_id = ?"
        params.append(product_id)

    total = cur.execute(
        f"SELECT COUNT(*) FROM movements m JOIN products p ON p.id = m.product_id {where}",
        params,
    ).fetchone()[0]

    rows = cur.execute(
        f"""
        SELECT m.id, m.product_id, m.action_type, m.delta, m.reason, m.source,
               m.batch_id, m.warehouse_id, w.warehouse_code, m.created_at,
               p.name, p.sku, p.tags
        FROM movements m
        JOIN products p ON p.id = m.product_id
        LEFT JOIN warehouses w ON w.id=m.warehouse_id
        {where}
        ORDER BY m.id DESC LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    ).fetchall()
    conn.close()

    return {
        "data": [dict(r) for r in rows],
        "meta": {"total": total, "limit": limit, "offset": offset},
    }


@router.post("", status_code=201)
def create_movement(
    m: MovementCreate,
    response: Response,
    user: dict = Depends(require_permission("stock", "write")),
):
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()

        product = cur.execute(
            "SELECT id, quantity, low_stock, name, batch_tracking_enabled_at FROM products "
            "WHERE sku=? AND deleted=0 AND archived=0 AND is_forecast_test=0 FOR UPDATE",
            (m.sku,),
        ).fetchone()

        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        if product["batch_tracking_enabled_at"]:
            raise HTTPException(
                status_code=409,
                detail="Batch-tracked stock can only be changed through inventory batches.",
            )

        new_qty = Decimal(str(product["quantity"])) + m.delta
        if new_qty < 0:
            raise HTTPException(status_code=400, detail="Insufficient stock")

        action_type = "STOCK_IN" if m.delta > 0 else "STOCK_OUT"

        cur.execute(
            "UPDATE products SET quantity=quantity + ?, updated_at=datetime('now') "
            "WHERE id=? AND is_forecast_test=0 AND quantity + ? >= 0",
            (m.delta, product["id"], m.delta),
        )
        if cur.rowcount != 1:
            raise HTTPException(status_code=400, detail="Insufficient stock")

        cur.execute(
            "INSERT INTO movements (product_id, action_type, delta, reason, source) VALUES (?, ?, ?, ?, 'manual')",
            (product["id"], action_type, m.delta, m.reason),
        )
        movement_id = cur.lastrowid

        log_audit(cur, user, action_type, "stock", "product", product["id"], f"Adjusted '{product['name']}' by {m.delta:+.2f} ({m.reason or 'no reason'})")
        conn.commit()

        row = cur.execute("SELECT * FROM movements WHERE id=?", (movement_id,)).fetchone()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    resource = dict(row)
    resource["product_name"] = product["name"]
    resource["sku"] = m.sku
    resource["quantity_after"] = int(new_qty) if new_qty == new_qty.to_integral_value() else float(new_qty)
    # Same rule as the low-stock filter and dashboard: at or below the threshold.
    resource["low_stock_warning"] = new_qty <= Decimal(str(product["low_stock"]))

    response.headers["Location"] = f"/v1/movements/{movement_id}"
    return resource


@router.delete("/{movement_id}", status_code=204)
def delete_movement(movement_id: int, user: dict = Depends(require_permission("stock", "write"))):
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()

        movement = cur.execute(
            "SELECT id, product_id, delta, source FROM movements WHERE id=? FOR UPDATE",
            (movement_id,),
        ).fetchone()

        if not movement:
            raise HTTPException(status_code=404, detail="Movement not found")

        if movement["source"] != "manual":
            raise HTTPException(
                status_code=409,
                detail="Only standalone manual stock adjustments can be undone",
            )

        # Match create_movement: deleted and archived products cannot change stock.
        product = cur.execute(
            "SELECT quantity, batch_tracking_enabled_at FROM products "
            "WHERE id=? AND deleted=0 AND archived=0 AND is_forecast_test=0 FOR UPDATE",
            (movement["product_id"],),
        ).fetchone()
        if not product:
            raise HTTPException(
                status_code=404,
                detail="The product for this movement no longer exists or is archived",
            )
        if product["batch_tracking_enabled_at"]:
            raise HTTPException(
                status_code=409,
                detail="Manual movements cannot be reversed after batch tracking is enabled.",
            )
        if Decimal(str(product["quantity"])) - Decimal(str(movement["delta"])) < 0:
            raise HTTPException(status_code=409, detail="Reversing this movement would make stock negative")

        cur.execute(
            "UPDATE products SET quantity = quantity - ?, updated_at=datetime('now') "
            "WHERE id=? AND is_forecast_test=0 AND quantity - ? >= 0",
            (movement["delta"], movement["product_id"], movement["delta"]),
        )
        if cur.rowcount != 1:
            raise HTTPException(status_code=409, detail="Stock changed; refresh and try again")

        cur.execute("DELETE FROM movements WHERE id=?", (movement_id,))

        log_audit(cur, user, "UNDO", "stock", "movement", movement_id, f"Reversed movement {movement_id} (delta {movement['delta']:+.2f})")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return Response(status_code=204)


stats_router = APIRouter()


@stats_router.get("")
def get_stats(user: dict = Depends(require_permission("reports", "read"))):
    conn = get_db()
    cur = conn.cursor()

    total_products = cur.execute(
        "SELECT COUNT(*) FROM products "
        "WHERE deleted=0 AND archived=0 AND is_forecast_test=0"
    ).fetchone()[0]

    total_stock = cur.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM products "
        "WHERE deleted=0 AND archived=0 AND is_forecast_test=0"
    ).fetchone()[0]

    low_stock_count = cur.execute(
        "SELECT COUNT(*) FROM products "
        "WHERE deleted=0 AND archived=0 AND is_forecast_test=0 AND quantity <= low_stock"
    ).fetchone()[0]

    recent_activity = cur.execute(
        "SELECT COUNT(*) FROM movements m JOIN products p ON p.id=m.product_id "
        "WHERE p.is_forecast_test=0 AND m.created_at >= datetime('now', '-7 days')"
    ).fetchone()[0]

    conn.close()

    return {
        "total_products": total_products,
        "total_stock": total_stock,
        "low_stock_count": low_stock_count,
        "recent_activity": recent_activity,
    }
