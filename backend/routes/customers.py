from fastapi import APIRouter, Depends, HTTPException, Query, Response
from database import get_db
from schemas import CustomerCreate, CustomerUpdate
from security import require_permission, log_audit
from typing import Optional

router = APIRouter()


@router.get("")
def list_customers(
    q: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_permission("customers", "read")),
):
    conn = get_db()
    cur = conn.cursor()

    where = "WHERE deleted=0"
    params = []

    if q:
        where += " AND (LOWER(name) LIKE ? OR LOWER(contact_person) LIKE ? OR LOWER(email) LIKE ?)"
        like = f"%{q.lower()}%"
        params.extend([like, like, like])

    total = cur.execute(f"SELECT COUNT(*) FROM customers {where}", params).fetchone()[0]
    rows = cur.execute(
        f"SELECT * FROM customers {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    conn.close()

    return {
        "data": [dict(r) for r in rows],
        "meta": {"total": total, "limit": limit, "offset": offset},
    }


@router.get("/{customer_id}")
def get_customer(customer_id: int, user: dict = Depends(require_permission("customers", "read"))):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM customers WHERE id=? AND deleted=0", (customer_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Customer not found")
    return dict(row)


@router.post("", status_code=201)
def create_customer(
    c: CustomerCreate,
    response: Response,
    user: dict = Depends(require_permission("customers", "write")),
):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO customers (name, contact_person, email, phone, address, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (c.name, c.contact_person, c.email, c.phone, c.address, c.notes),
    )
    customer_id = cur.lastrowid
    log_audit(cur, user, "CREATE", "customers", "customer", customer_id, f"Created customer '{c.name}'")
    conn.commit()

    row = cur.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    conn.close()

    response.headers["Location"] = f"/v1/customers/{customer_id}"
    return dict(row)


@router.patch("/{customer_id}")
def update_customer(customer_id: int, c: CustomerUpdate, user: dict = Depends(require_permission("customers", "write"))):
    conn = get_db()
    cur = conn.cursor()

    existing = cur.execute(
        "SELECT * FROM customers WHERE id=? AND deleted=0", (customer_id,)
    ).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Customer not found")

    fields = {k: v for k, v in c.model_dump(exclude_unset=True).items() if v is not None}

    if not fields:
        conn.close()
        return dict(existing)

    set_clause = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values())

    cur.execute(
        f"UPDATE customers SET {set_clause}, updated_at=datetime('now') WHERE id=?",
        values + [customer_id],
    )
    log_audit(cur, user, "UPDATE", "customers", "customer", customer_id, f"Updated fields: {', '.join(fields)}")
    conn.commit()

    row = cur.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    conn.close()
    return dict(row)


@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: int, user: dict = Depends(require_permission("customers", "delete"))):
    conn = get_db()
    cur = conn.cursor()

    existing = cur.execute(
        "SELECT * FROM customers WHERE id=? AND deleted=0", (customer_id,)
    ).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Customer not found")

    cur.execute(
        "UPDATE customers SET deleted=1, updated_at=datetime('now') WHERE id=?",
        (customer_id,),
    )
    log_audit(cur, user, "DELETE", "customers", "customer", customer_id, f"Deleted customer '{existing['name']}'")
    conn.commit()
    conn.close()
    return Response(status_code=204)
