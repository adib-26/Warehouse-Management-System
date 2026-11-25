from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator

from database import IntegrityError, get_db, MODULES, ROLES
from security import hash_password, log_audit, require_permission

router = APIRouter()


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12)
    full_name: str = ""
    role: str = "operator"

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be no more than 72 UTF-8 bytes")
        return value


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=12)

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be no more than 72 UTF-8 bytes")
        return value


class PermissionEntry(BaseModel):
    role: str
    module: str
    can_read: bool
    can_write: bool
    can_delete: bool


class PermissionMatrixUpdate(BaseModel):
    entries: List[PermissionEntry]


@router.get("/users")
def list_users(user: dict = Depends(require_permission("admin", "read"))):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, username, full_name, role, active, created_at, updated_at FROM users ORDER BY username"
    ).fetchall()
    conn.close()
    data = [dict(r) for r in rows]
    return {"data": data, "meta": {"total": len(data)}}


@router.post("/users", status_code=201)
def create_user(u: UserCreate, response: Response, user: dict = Depends(require_permission("admin", "write"))):
    if u.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(ROLES)}")
    username = u.username.strip()
    if not username or len(u.password) < 12:
        raise HTTPException(status_code=400, detail="Username required and password must be at least 12 characters")

    conn = get_db()
    try:
        cur = conn.cursor()
        existing = cur.execute(
            "SELECT id FROM users WHERE username=?", (username,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Username already exists")

        try:
            cur.execute(
                "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                (username, hash_password(u.password), u.full_name, u.role),
            )
        except IntegrityError as exc:
            # The preflight check provides a clear response in the normal case;
            # this branch handles two requests that race for the same username.
            conn.rollback()
            raise HTTPException(status_code=409, detail="Username already exists") from exc
        user_id = cur.lastrowid
        log_audit(
            cur,
            user,
            "CREATE",
            "admin",
            "user",
            user_id,
            f"Created user '{username}' with role {u.role}",
        )
        conn.commit()

        row = cur.execute(
            "SELECT id, username, full_name, role, active, created_at, updated_at FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    response.headers["Location"] = f"/v1/admin/users/{user_id}"
    return dict(row)


@router.patch("/users/{user_id}")
def update_user(user_id: int, u: UserUpdate, user: dict = Depends(require_permission("admin", "write"))):
    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    cur = conn.cursor()
    existing = cur.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    if u.active is False and user_id == user["id"]:
        conn.close()
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    removes_active_admin = (
        existing["role"] == "admin"
        and bool(existing["active"])
        and (
            u.active is False
            or (u.role is not None and u.role != "admin")
        )
    )
    if removes_active_admin:
        remaining_admins = cur.execute(
            "SELECT COUNT(*) FROM users WHERE role='admin' AND active=1 AND id!=?",
            (user_id,),
        ).fetchone()[0]
        if remaining_admins == 0:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail="At least one active administrator must remain",
            )

    changes = []
    if u.full_name is not None:
        cur.execute("UPDATE users SET full_name=? WHERE id=?", (u.full_name, user_id))
        changes.append("full_name")
    if u.role is not None:
        if u.role not in ROLES:
            conn.close()
            raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(ROLES)}")
        cur.execute("UPDATE users SET role=? WHERE id=?", (u.role, user_id))
        changes.append(f"role={u.role}")
    if u.active is not None:
        cur.execute("UPDATE users SET active=? WHERE id=?", (1 if u.active else 0, user_id))
        changes.append("activated" if u.active else "deactivated")
    if u.password is not None:
        if len(u.password) < 12:
            conn.close()
            raise HTTPException(status_code=400, detail="Password must be at least 12 characters")
        cur.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(u.password), user_id))
        changes.append("password reset")

    if not changes:
        conn.close()
        return {k: existing[k] for k in ("id", "username", "full_name", "role", "active", "created_at", "updated_at")}

    cur.execute("UPDATE users SET updated_at=datetime('now') WHERE id=?", (user_id,))
    log_audit(cur, user, "UPDATE", "admin", "user", user_id, f"Updated user '{existing['username']}': {', '.join(changes)}")
    conn.commit()

    row = cur.execute(
        "SELECT id, username, full_name, role, active, created_at, updated_at FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row)


@router.get("/permissions")
def get_permissions(user: dict = Depends(require_permission("admin", "read"))):
    conn = get_db()
    rows = conn.execute(
        "SELECT role, module, can_read, can_write, can_delete FROM permissions ORDER BY role, module"
    ).fetchall()
    conn.close()
    return {"roles": ROLES, "modules": MODULES, "entries": [dict(r) for r in rows]}


@router.put("/permissions")
def update_permissions(update: PermissionMatrixUpdate, user: dict = Depends(require_permission("admin", "write"))):
    conn = get_db()
    cur = conn.cursor()
    updated = 0

    for e in update.entries:
        if e.role not in ROLES or e.module not in MODULES:
            conn.close()
            raise HTTPException(status_code=400, detail=f"Unknown role or module: {e.role}/{e.module}")
        # Admin access to the admin module is immutable to prevent lockout.
        if e.role == "admin" and e.module == "admin":
            continue
        cur.execute(
            """
            INSERT INTO permissions (role, module, can_read, can_write, can_delete)
            VALUES (?, ?, ?, ?, ?) AS new_permission
            ON DUPLICATE KEY UPDATE can_read=new_permission.can_read,
                can_write=new_permission.can_write, can_delete=new_permission.can_delete
            """,
            (e.role, e.module, int(e.can_read), int(e.can_write), int(e.can_delete)),
        )
        updated += 1

    log_audit(cur, user, "UPDATE", "admin", "permissions", None, f"Updated permission matrix ({updated} entries)")
    conn.commit()

    rows = conn.execute(
        "SELECT role, module, can_read, can_write, can_delete FROM permissions ORDER BY role, module"
    ).fetchall()
    conn.close()
    return {"roles": ROLES, "modules": MODULES, "entries": [dict(r) for r in rows]}


def _query_audit(username, module, action, limit, offset):
    conn = get_db()
    where = "WHERE 1=1"
    params = []
    if username:
        where += " AND username = ?"
        params.append(username)
    if module:
        where += " AND module = ?"
        params.append(module)
    if action:
        where += " AND action = ?"
        params.append(action.upper())

    total = conn.execute(f"SELECT COUNT(*) FROM audit_logs {where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM audit_logs {where} ORDER BY id DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    conn.close()
    return {
        "data": [dict(r) for r in rows],
        "meta": {"total": total, "limit": limit, "offset": offset},
    }


@router.get("/audit-logs")
def admin_audit(
    username: Optional[str] = None,
    module: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_permission("admin", "read")),
):
    return _query_audit(username, module, action, limit, offset)


audit_router = APIRouter()


@audit_router.get("")
def audit_report(
    username: Optional[str] = None,
    module: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_permission("reports", "read")),
):
    return _query_audit(username, module, action, limit, offset)
