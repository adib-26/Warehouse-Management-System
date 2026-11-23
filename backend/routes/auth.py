from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import get_db
from security import (
    create_token,
    get_current_user,
    get_role_permissions,
    log_audit,
    verify_password,
)

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(req: LoginRequest):
    conn = get_db()
    cur = conn.cursor()
    row = cur.execute(
        "SELECT * FROM users WHERE username=?", (req.username,)
    ).fetchone()

    if not row or not row["active"] or not verify_password(req.password, row["password_hash"]):
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid username or password")

    user = dict(row)
    log_audit(cur, user, "LOGIN", "auth", "user", user["id"], f"{user['username']} logged in")
    conn.commit()
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
