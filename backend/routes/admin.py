from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator

from database import IntegrityError, get_db, MODULES, ROLES
from security import has_permission, hash_password, log_audit, require_permission

router = APIRouter()

ACTIONS = ("read", "write", "delete")
USER_FIELDS = ("id", "username", "full_name", "role", "active", "created_at", "updated_at")
USER_COLUMNS = ", ".join(USER_FIELDS)


class UserCreate(BaseModel):
    # Limits match users.username VARCHAR(64) and users.full_name VARCHAR(255).
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=12)
    full_name: str = Field(default="", max_length=255)
    role: str = "operator"

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be no more than 72 UTF-8 bytes")
        return value


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=255)
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


def _role_permissions(cur, role: str) -> dict:
    rows = cur.execute(
        "SELECT module, can_read, can_write, can_delete FROM permissions WHERE role=?",
        (role,),
    ).fetchall()
    return {
        row["module"]: (bool(row["can_read"]), bool(row["can_write"]), bool(row["can_delete"]))
        for row in rows
    }


def _role_exceeds_caller(cur, caller: dict, role: str) -> bool:
    """Whether ``role`` has access that the (non-admin) caller lacks.

    Administrators may manage every account. Admin write access can also be
    delegated to other roles through the permission matrix; those users may
    only manage accounts, and assign roles, that are no more powerful than
    their own. Otherwise they could promote themselves or take over a more
    privileged account by resetting its password. The admin role always counts
    as more powerful, because it keeps user and permission management.
    """
    if caller["role"] == "admin":
        return False
    if role == "admin":
        return True
    held = _role_permissions(cur, caller["role"])
    return any(
        granted and not had
        for module, flags in _role_permissions(cur, role).items()
        for granted, had in zip(flags, held.get(module, (False, False, False)))
    )


def _flags_text(flags) -> str:
    return "".join(letter if allowed else "-" for letter, allowed in zip("rwd", flags))


@router.get("/users")
def list_users(user: dict = Depends(require_permission("admin", "read"))):
    conn = get_db()
    try:
        rows = conn.execute(
            f"SELECT {USER_COLUMNS} FROM users ORDER BY username"
        ).fetchall()
    finally:
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
        if _role_exceeds_caller(cur, user, u.role):
            raise HTTPException(
                status_code=403,
                detail=f"You cannot create {u.role} accounts because that role has access you do not have",
            )
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
            f"SELECT {USER_COLUMNS} FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    response.headers["Location"] = f"/v1/admin/users/{user_id}"
    return dict(row)


@router.patch("/users/{user_id}")
def update_user(user_id: int, u: UserUpdate, user: dict = Depends(require_permission("admin", "write"))):
    if u.role is not None and u.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(ROLES)}")

    conn = get_db()
    try:
        conn.execute("START TRANSACTION")
        cur = conn.cursor()
        if u.active is False or u.role is not None:
            # Lock every active administrator in id order before reading the
            # target. Concurrent demotions then run one after the other, so two
            # requests cannot each count the other admin as the one who remains.
            cur.execute(
                "SELECT id FROM users WHERE role='admin' AND active=1 ORDER BY id FOR UPDATE"
            )
        existing = cur.execute(
            "SELECT * FROM users WHERE id=? FOR UPDATE", (user_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="User not found")

        if u.active is False and user_id == user["id"]:
            raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

        role_changes = u.role is not None and u.role != existing["role"]
        if user["role"] != "admin":
            if role_changes and user_id == user["id"]:
                raise HTTPException(status_code=403, detail="You cannot change your own role")
            if _role_exceeds_caller(cur, user, existing["role"]):
                raise HTTPException(
                    status_code=403,
                    detail=f"You cannot change {existing['role']} accounts because that role has access you do not have",
                )
            if role_changes and _role_exceeds_caller(cur, user, u.role):
                raise HTTPException(
                    status_code=403,
                    detail=f"You cannot assign the {u.role} role because it has access you do not have",
                )

        removes_active_admin = (
            existing["role"] == "admin"
            and bool(existing["active"])
            and (u.active is False or role_changes)
        )
        if removes_active_admin:
            remaining_admins = cur.execute(
                "SELECT COUNT(*) FROM users WHERE role='admin' AND active=1 AND id!=?",
                (user_id,),
            ).fetchone()[0]
            if remaining_admins == 0:
                raise HTTPException(
                    status_code=400,
                    detail="At least one active administrator must remain",
                )

        changes = []
        if u.full_name is not None:
            cur.execute("UPDATE users SET full_name=? WHERE id=?", (u.full_name, user_id))
            changes.append("full_name")
        if role_changes:
            cur.execute("UPDATE users SET role=? WHERE id=?", (u.role, user_id))
            changes.append(f"role {existing['role']} -> {u.role}")
        if u.active is not None:
            cur.execute("UPDATE users SET active=? WHERE id=?", (1 if u.active else 0, user_id))
            changes.append("activated" if u.active else "deactivated")
        if u.password is not None:
            cur.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(u.password), user_id))
            changes.append("password reset")

        if not changes:
            conn.rollback()
            return {key: existing[key] for key in USER_FIELDS}

        cur.execute("UPDATE users SET updated_at=UTC_TIMESTAMP() WHERE id=?", (user_id,))
        log_audit(cur, user, "UPDATE", "admin", "user", user_id, f"Updated user '{existing['username']}': {', '.join(changes)}")
        conn.commit()

        row = cur.execute(
            f"SELECT {USER_COLUMNS} FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return dict(row)


@router.get("/permissions")
def get_permissions(user: dict = Depends(require_permission("admin", "read"))):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT role, module, can_read, can_write, can_delete FROM permissions ORDER BY role, module"
        ).fetchall()
    finally:
        conn.close()
    return {"roles": ROLES, "modules": MODULES, "entries": [dict(r) for r in rows]}


@router.put("/permissions")
def update_permissions(update: PermissionMatrixUpdate, user: dict = Depends(require_permission("admin", "write"))):
    for e in update.entries:
        if e.role not in ROLES or e.module not in MODULES:
            raise HTTPException(status_code=400, detail=f"Unknown role or module: {e.role}/{e.module}")

    conn = get_db()
    try:
        cur = conn.cursor()
        current = {
            (row["role"], row["module"]): (
                bool(row["can_read"]), bool(row["can_write"]), bool(row["can_delete"])
            )
            for row in cur.execute(
                "SELECT role, module, can_read, can_write, can_delete FROM permissions"
            ).fetchall()
        }
        # Delegated (non-admin) editors may not change their own role or the
        # admin role, and may not grant access they do not hold themselves.
        held = None if user["role"] == "admin" else _role_permissions(cur, user["role"])
        changes = []

        for e in update.entries:
            # Admin access to the admin module is immutable to prevent lockout.
            if e.role == "admin" and e.module == "admin":
                continue
            old = current.get((e.role, e.module), (False, False, False))
            new = (e.can_read, e.can_write, e.can_delete)
            if new == old:
                continue
            if held is not None:
                if e.role in ("admin", user["role"]):
                    raise HTTPException(
                        status_code=403,
                        detail=f"Only administrators can change permissions for the {e.role} role",
                    )
                held_flags = held.get(e.module, (False, False, False))
                for action, was_allowed, now_allowed, caller_has in zip(ACTIONS, old, new, held_flags):
                    if now_allowed and not was_allowed and not caller_has:
                        raise HTTPException(
                            status_code=403,
                            detail=f"You cannot grant {action} access to {e.module} because you do not have it",
                        )
            cur.execute(
                """
                INSERT INTO permissions (role, module, can_read, can_write, can_delete)
                VALUES (?, ?, ?, ?, ?) AS new_permission
                ON DUPLICATE KEY UPDATE can_read=new_permission.can_read,
                    can_write=new_permission.can_write, can_delete=new_permission.can_delete
                """,
                (e.role, e.module, int(e.can_read), int(e.can_write), int(e.can_delete)),
            )
            current[(e.role, e.module)] = new
            changes.append(f"{e.role}/{e.module} {_flags_text(old)} -> {_flags_text(new)}")

        details = (
            f"Updated permission matrix: {'; '.join(changes)}"
            if changes
            else "Saved permission matrix with no changes"
        )
        log_audit(cur, user, "UPDATE", "admin", "permissions", None, details)
        conn.commit()

        rows = conn.execute(
            "SELECT role, module, can_read, can_write, can_delete FROM permissions ORDER BY role, module"
        ).fetchall()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"roles": ROLES, "modules": MODULES, "entries": [dict(r) for r in rows]}


def _query_audit(username, module, action, limit, offset, hidden_modules=()):
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
    if hidden_modules:
        where += f" AND module NOT IN ({', '.join('?' for _ in hidden_modules)})"
        params.extend(hidden_modules)

    conn = get_db()
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM audit_logs {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM audit_logs {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    finally:
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
    # Sign-in history and user or permission changes stay with users who can
    # read the administration module; everyone else sees operational activity.
    hidden_modules = () if has_permission(user, "admin", "read") else ("admin", "auth")
    return _query_audit(username, module, action, limit, offset, hidden_modules)
