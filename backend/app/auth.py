"""JWT-basierte Authentifizierung."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

# User-DB (im Speicher, ein User; erweiterbar)
_users_db: dict[str, str] = {}


def init_admin_user() -> None:
    """Erstellt den Admin-User aus .env (einmalig)."""
    if not _users_db:
        h = bcrypt.hashpw(settings.ADMIN_PASSWORD.encode(), bcrypt.gensalt())
        _users_db[settings.ADMIN_USER] = h.decode()


def verify_user(username: str, password: str) -> bool:
    init_admin_user()
    if username not in _users_db:
        return False
    return bcrypt.checkpw(password.encode(), _users_db[username].encode())


def create_token(username: str) -> str:
    init_admin_user()
    exp = datetime.now(tz=timezone.utc) + timedelta(hours=settings.JWT_TTL_HOURS)
    payload = {"sub": username, "exp": exp, "iat": datetime.now(tz=timezone.utc)}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# FastAPI Dependency
bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    # Wenn Auth deaktiviert ist, gib Default-User zurueck
    if not settings.AUTH_ENABLED:
        return settings.ADMIN_USER
    if not creds or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(creds.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload["sub"]
