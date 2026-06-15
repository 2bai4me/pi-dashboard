"""Multi-User Auth: User-Management für das Dashboard."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import create_token, require_auth, verify_user
from ..config import settings
from ..utils import read_json, write_json

router = APIRouter(prefix="/api/users", tags=["users"])

USERS_FILE = settings.PI_AGENT_DIR / "dashboard_users.json"


def _load_users() -> list[dict]:
    return read_json(USERS_FILE, [])


def _save_users(users: list[dict]) -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_json(USERS_FILE, users)


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"  # admin | user | viewer


class UserInfo(BaseModel):
    username: str
    role: str
    created_at: str
    last_login: str | None = None
    enabled: bool = True


@router.get("", response_model=list[UserInfo])
async def list_users(_user: str = Depends(require_auth)) -> list[UserInfo]:
    users = _load_users()
    return [UserInfo(**u) for u in users]


@router.post("")
async def create_user(req: UserCreate, current: str = Depends(require_auth)) -> dict:
    # Nur Admin darf User anlegen
    if current != settings.ADMIN_USER:
        raise HTTPException(403, "Only admin can create users")
    users = _load_users()
    if any(u["username"] == req.username for u in users):
        raise HTTPException(409, "User already exists")
    import bcrypt
    users.append({
        "username": req.username,
        "password_hash": bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode(),
        "role": req.role,
        "created_at": datetime.now().isoformat(),
        "enabled": True,
    })
    _save_users(users)
    return {"ok": True, "username": req.username, "role": req.role}


@router.post("/{username}/toggle")
async def toggle_user(username: str, _user: str = Depends(require_auth)) -> dict:
    users = _load_users()
    for u in users:
        if u["username"] == username:
            u["enabled"] = not u.get("enabled", True)
            _save_users(users)
            return {"ok": True, "enabled": u["enabled"]}
    raise HTTPException(404, "User not found")


@router.delete("/{username}")
async def delete_user(username: str, current: str = Depends(require_auth)) -> dict:
    if current != settings.ADMIN_USER:
        raise HTTPException(403, "Only admin can delete users")
    users = _load_users()
    users = [u for u in users if u["username"] != username]
    _save_users(users)
    return {"ok": True, "deleted": username}


@router.post("/login-alt")
async def login_alt(req: dict) -> dict:
    """Alternativer Login fuer Multi-User."""
    username = req.get("username", "")
    password = req.get("password", "")

    # Admin aus .env
    if username == settings.ADMIN_USER:
        if verify_user(username, password):
            return {"token": create_token(username), "user": username, "role": "admin"}
        raise HTTPException(401, "Invalid credentials")

    # Users aus dashboard_users.json
    users = _load_users()
    import bcrypt
    for u in users:
        if u["username"] == username and u.get("enabled", True):
            if bcrypt.checkpw(password.encode(), u["password_hash"].encode()):
                u["last_login"] = datetime.now().isoformat()
                _save_users(users)
                return {"token": create_token(username), "user": username, "role": u.get("role", "user")}
    raise HTTPException(401, "Invalid credentials")
