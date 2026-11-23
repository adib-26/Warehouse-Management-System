from fastapi import APIRouter, Depends, HTTPException, Query, Response
from database import get_db
from schemas import MovementCreate
from security import require_permission, log_audit
from typing import Optional

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

    where = "WHERE 1=1"
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
        SELECT m.id, m.product_id, m.action_type, m.delta, m.reason, m.created_at,
               p.name, p.sku, p.tags
        FROM movements m
        JOIN products p ON p.id = m.product_id
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
    cur = conn.cursor()

    product = cur.execute(
        "SELECT id, quantity, name FROM products WHERE sku=? AND deleted=0 AND archived=0",
        (m.sku,),
    ).fetchone()

    if not product:
        conn.close()
        raise HTTPException(status_code=404, detail="Product not found")

    new_qty = product["quantity"] + m.delta
    if new_qty < 0:
        conn.close()
        raise HTTPException(status_code=400, detail="Insufficient stock")

    action_type = "STOCK_IN" if m.delta > 0 else "STOCK_OUT"

    cur.execute("UPDATE products SET quantity=?, updated_at=datetime('now') WHERE id=?", (new_qty, product["id"]))

    cur.execute(
        "INSERT INTO movements (product_id, action_type, delta, reason) VALUES (?, ?, ?, ?)",
        (product["id"], action_type, m.delta, m.reason),
    )
    movement_id = cur.lastrowid

    log_audit(cur, user, action_type, "stock", "product", product["id"], f"Adjusted '{product['name']}' by {m.delta:+d} ({m.reason or 'no reason'})")
    conn.commit()

    row = cur.execute("SELECT * FROM movements WHERE id=?", (movement_id,)).fetchone()
    conn.close()

    resource = dict(row)
    resource["product_name"] = product["name"]
    resource["sku"] = m.sku
    resource["quantity_after"] = new_qty
    resource["low_stock_warning"] = new_qty <= 0

    response.headers["Location"] = f"/v1/movements/{movement_id}"
    return resource


@router.delete("/{movement_id}", status_code=204)
def delete_movement(movement_id: int, user: dict = Depends(require_permission("stock", "write"))):
    conn = get_db()
    cur = conn.cursor()

    movement = cur.execute(
        "SELECT id, product_id, delta FROM movements WHERE id=?", (movement_id,)
    ).fetchone()

    if not movement:
        conn.close()
        raise HTTPException(status_code=404, detail="Movement not found")

    product = cur.execute(
        "SELECT quantity FROM products WHERE id=?", (movement["product_id"],)
    ).fetchone()
    if product and product["quantity"] - movement["delta"] < 0:
        conn.close()
        raise HTTPException(status_code=409, detail="Reversing this movement would make stock negative")

    cur.execute(
        "UPDATE products SET quantity = quantity - ?, updated_at=datetime('now') WHERE id=?",
        (movement["delta"], movement["product_id"]),
    )

    cur.execute("DELETE FROM movements WHERE id=?", (movement_id,))

    log_audit(cur, user, "UNDO", "stock", "movement", movement_id, f"Reversed movement {movement_id} (delta {movement['delta']:+d})")
    conn.commit()
    conn.close()
    return Response(status_code=204)


stats_router = APIRouter()


@stats_router.get("")
def get_stats(user: dict = Depends(require_permission("reports", "read"))):
    conn = get_db()
    cur = conn.cursor()

    total_products = cur.execute(
        "SELECT COUNT(*) FROM products WHERE deleted=0 AND archived=0"
    ).fetchone()[0]

    total_stock = cur.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM products WHERE deleted=0 AND archived=0"
    ).fetchone()[0]

    low_stock_count = cur.execute(
        "SELECT COUNT(*) FROM products WHERE deleted=0 AND archived=0 AND quantity <= low_stock"
    ).fetchone()[0]

    recent_activity = cur.execute(
        "SELECT COUNT(*) FROM movements WHERE created_at >= datetime('now', '-7 days')"
    ).fetchone()[0]

    conn.close()

    return {
        "total_products": total_products,
        "total_stock": total_stock,
        "low_stock_count": low_stock_count,
        "recent_activity": recent_activity,
    }
