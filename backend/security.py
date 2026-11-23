from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import SECRET_KEY
from database import get_db

ALGORITHM = "HS256"
TOKEN_TTL_HOURS = 12

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_token(user: dict) -> str:
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    conn = get_db()
    row = conn.execute(
        "SELECT id, username, full_name, role, active FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    conn.close()

    if not row or not row["active"]:
        raise HTTPException(status_code=401, detail="User not found or deactivated")
    return dict(row)


def get_role_permissions(role: str) -> dict:
    conn = get_db()
    rows = conn.execute(
        "SELECT module, can_read, can_write, can_delete FROM permissions WHERE role=?",
        (role,),
    ).fetchall()
    conn.close()
    return {
        r["module"]: {
            "read": bool(r["can_read"]),
            "write": bool(r["can_write"]),
            "delete": bool(r["can_delete"]),
        }
        for r in rows
    }


def has_permission(user: dict, module: str, action: str) -> bool:
    # Admins always keep access to the admin module so they can't lock themselves out.
    if user["role"] == "admin" and module == "admin":
        return True

    conn = get_db()
    row = conn.execute(
        f"SELECT can_{action} AS allowed FROM permissions WHERE role=? AND module=?",
        (user["role"], module),
    ).fetchone()
    conn.close()
    return bool(row and row["allowed"])


def check_permission(user: dict, module: str, action: str):
    if not has_permission(user, module, action):
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied: requires {action} access to {module}",
        )


def require_permission(module: str, action: str):
    def dependency(user: dict = Depends(get_current_user)) -> dict:
        check_permission(user, module, action)
        return user

    return dependency


def log_audit(cur, user, action, module, entity_type="", entity_id=None, details=""):
    cur.execute(
        """
        INSERT INTO audit_logs (user_id, username, action, module, entity_type, entity_id, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user["id"] if user else None,
            user["username"] if user else "",
            action,
            module,
            entity_type,
            entity_id,
            details,
        ),
    )
