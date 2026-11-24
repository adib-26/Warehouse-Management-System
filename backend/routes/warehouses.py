from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from database import IntegrityError, get_db
from schemas import WarehouseCreate, WarehouseUpdate
from security import log_audit, require_permission


router = APIRouter()


def _required_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail=f"{field_name} cannot be blank")
    return normalized


@router.get("")
def list_warehouses(
    q: Optional[str] = None,
    include_inactive: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_permission("outbound", "read")),
):
    """List real WMS warehouses; M5 sandbox warehouses remain internal."""
    conn = get_db()
    try:
        where = "WHERE is_forecast_test=0"
        params = []
        if not include_inactive:
            where += " AND active=1"
        if q:
            where += " AND (LOWER(warehouse_code) LIKE ? OR LOWER(name) LIKE ?)"
            term = f"%{q.lower()}%"
            params.extend((term, term))
        total = conn.execute(
            f"SELECT COUNT(*) FROM warehouses {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT id, warehouse_code, name, address, active, created_at, updated_at
            FROM warehouses
            {where}
            ORDER BY active DESC, name, warehouse_code
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


@router.post("", status_code=201)
def create_warehouse(
    warehouse: WarehouseCreate,
    response: Response,
    user: dict = Depends(require_permission("admin", "write")),
):
    code = _required_text(warehouse.warehouse_code, "warehouse_code")
    name = _required_text(warehouse.name, "name")
    conn = get_db()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO warehouses
                    (warehouse_code, name, address, active, is_forecast_test)
                VALUES (?, ?, ?, ?, 0)
                """,
                (code, name, warehouse.address.strip(), int(warehouse.active)),
            )
        except IntegrityError as exc:
            conn.rollback()
            raise HTTPException(status_code=409, detail="Warehouse code already exists") from exc
        warehouse_id = cur.lastrowid
        log_audit(
            cur,
            user,
            "CREATE",
            "warehouses",
            "warehouse",
            warehouse_id,
            f"Created warehouse '{name}' ({code})",
        )
        conn.commit()
        row = cur.execute(
            "SELECT id, warehouse_code, name, address, active, created_at, updated_at "
            "FROM warehouses WHERE id=?",
            (warehouse_id,),
        ).fetchone()
    except HTTPException:
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    response.headers["Location"] = f"/v1/warehouses/{warehouse_id}"
    return dict(row)


@router.patch("/{warehouse_id}")
def update_warehouse(
    warehouse_id: int,
    warehouse: WarehouseUpdate,
    user: dict = Depends(require_permission("admin", "write")),
):
    conn = get_db()
    try:
        cur = conn.cursor()
        existing = cur.execute(
            "SELECT * FROM warehouses WHERE id=? AND is_forecast_test=0",
            (warehouse_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Warehouse not found")

        fields = {
            key: value
            for key, value in warehouse.model_dump(exclude_unset=True).items()
            if value is not None
        }
        if "warehouse_code" in fields:
            fields["warehouse_code"] = _required_text(
                fields["warehouse_code"], "warehouse_code"
            )
        if "name" in fields:
            fields["name"] = _required_text(fields["name"], "name")
        if "address" in fields:
            fields["address"] = fields["address"].strip()
        if "active" in fields:
            fields["active"] = int(fields["active"])
        if not fields:
            return {
                key: existing[key]
                for key in ("id", "warehouse_code", "name", "address", "active", "created_at", "updated_at")
            }

        set_clause = ", ".join(f"{key}=?" for key in fields)
        try:
            cur.execute(
                f"UPDATE warehouses SET {set_clause} "
                "WHERE id=? AND is_forecast_test=0",
                list(fields.values()) + [warehouse_id],
            )
        except IntegrityError as exc:
            conn.rollback()
            raise HTTPException(status_code=409, detail="Warehouse code already exists") from exc
        log_audit(
            cur,
            user,
            "UPDATE",
            "warehouses",
            "warehouse",
            warehouse_id,
            f"Updated fields: {', '.join(fields)}",
        )
        conn.commit()
        row = cur.execute(
            "SELECT id, warehouse_code, name, address, active, created_at, updated_at "
            "FROM warehouses WHERE id=?",
            (warehouse_id,),
        ).fetchone()
        return dict(row)
    except HTTPException:
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
