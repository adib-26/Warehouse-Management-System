from fastapi import APIRouter, Depends, HTTPException, Query, Response
from database import get_db
from schemas import SupplierCreate, SupplierUpdate
from security import require_permission, log_audit
from typing import Optional

router = APIRouter()


@router.get("")
def list_suppliers(
    q: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_permission("suppliers", "read")),
):
    conn = get_db()
    cur = conn.cursor()

    where = "WHERE deleted=0"
    params = []

    if q:
        where += " AND (LOWER(name) LIKE ? OR LOWER(contact_person) LIKE ? OR LOWER(email) LIKE ?)"
        like = f"%{q.lower()}%"
        params.extend([like, like, like])

    total = cur.execute(f"SELECT COUNT(*) FROM suppliers {where}", params).fetchone()[0]
    rows = cur.execute(
        f"SELECT * FROM suppliers {where} ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    conn.close()

    return {
        "data": [dict(r) for r in rows],
        "meta": {"total": total, "limit": limit, "offset": offset},
    }


@router.get("/{supplier_id}")
def get_supplier(supplier_id: int, user: dict = Depends(require_permission("suppliers", "read"))):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM suppliers WHERE id=? AND deleted=0", (supplier_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return dict(row)


@router.post("", status_code=201)
def create_supplier(
    s: SupplierCreate,
    response: Response,
    user: dict = Depends(require_permission("suppliers", "write")),
):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO suppliers (name, contact_person, email, phone, address, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (s.name, s.contact_person, s.email, s.phone, s.address, s.notes),
        )
        supplier_id = cur.lastrowid
        log_audit(cur, user, "CREATE", "suppliers", "supplier", supplier_id, f"Created supplier '{s.name}'")
        conn.commit()

        row = cur.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    response.headers["Location"] = f"/v1/suppliers/{supplier_id}"
    return dict(row)


@router.patch("/{supplier_id}")
def update_supplier(supplier_id: int, s: SupplierUpdate, user: dict = Depends(require_permission("suppliers", "write"))):
    conn = get_db()
    try:
        cur = conn.cursor()
        existing = cur.execute(
            "SELECT * FROM suppliers WHERE id=? AND deleted=0", (supplier_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Supplier not found")

        fields = {k: v for k, v in s.model_dump(exclude_unset=True).items() if v is not None}

        if not fields:
            return dict(existing)

        set_clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values())

        cur.execute(
            f"UPDATE suppliers SET {set_clause}, updated_at=datetime('now') WHERE id=?",
            values + [supplier_id],
        )
        log_audit(cur, user, "UPDATE", "suppliers", "supplier", supplier_id, f"Updated fields: {', '.join(fields)}")
        conn.commit()

        row = cur.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return dict(row)


@router.delete("/{supplier_id}", status_code=204)
def delete_supplier(supplier_id: int, user: dict = Depends(require_permission("suppliers", "delete"))):
    conn = get_db()
    try:
        cur = conn.cursor()
        existing = cur.execute(
            "SELECT * FROM suppliers WHERE id=? AND deleted=0", (supplier_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Supplier not found")

        cur.execute(
            "UPDATE suppliers SET deleted=1, updated_at=datetime('now') WHERE id=?",
            (supplier_id,),
        )
        log_audit(cur, user, "DELETE", "suppliers", "supplier", supplier_id, f"Deleted supplier '{existing['name']}'")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return Response(status_code=204)
