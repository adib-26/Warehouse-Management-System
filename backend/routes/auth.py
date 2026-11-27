from functools import lru_cache
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import get_db
from security import (
    create_token,
    get_current_user,
    get_role_permissions,
    hash_password,
    log_audit,
    verify_password,
)

router = APIRouter()


@lru_cache(maxsize=1)
def _unknown_user_password_hash() -> str:
    """A bcrypt hash that no submitted password will match."""
    return hash_password(secrets.token_urlsafe(24))


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(req: LoginRequest):
    conn = get_db()
    try:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT * FROM users WHERE username=?", (req.username,)
        ).fetchone()

        # Run bcrypt even for unknown usernames. Otherwise those requests return
        # much faster, which reveals which usernames exist.
        password_ok = verify_password(
            req.password,
            row["password_hash"] if row else _unknown_user_password_hash(),
        )
        if not row or not row["active"] or not password_ok:
            log_audit(
                cur,
                {"id": row["id"], "username": row["username"]} if row else None,
                "LOGIN_FAILED",
                "auth",
                "user",
                row["id"] if row else None,
                f"Failed sign-in for username '{req.username[:64]}'",
            )
            conn.commit()
            raise HTTPException(status_code=401, detail="Invalid username or password")

        user = dict(row)
        log_audit(cur, user, "LOGIN", "auth", "user", user["id"], f"{user['username']} logged in")
        conn.commit()
    finally:
        conn.close()

    return {
        "token": create_token(user),
        "user": {
            "id": user["id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"],
        },
        "permissions": get_role_permissions(user["role"]),
    }


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return {
        "user": {
            "id": user["id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"],
        },
        "permissions": get_role_permissions(user["role"]),
    }
