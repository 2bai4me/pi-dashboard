"""Konfig via .env."""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# .env im Backend-Root laden
BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_ROOT / ".env")


def _bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "y", "on")


def _list(val: str | None, default: list[str] | None = None) -> list[str]:
    if not val:
        return default or []
    return [v.strip() for v in val.split(",") if v.strip()]


class Settings:
    # Server
    HOST: str = os.getenv("PI_DASHBOARD_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PI_DASHBOARD_PORT", "9219"))

    # PI-Agent
    PI_AGENT_DIR: Path = Path(os.getenv("PI_AGENT_DIR", str(Path.home() / ".pi" / "agent")))
    PI_BIN: str = os.getenv("PI_BIN", "pi")
    PI_CODING_AGENT_PKG: str = os.getenv(
        "PI_CODING_AGENT_PKG", "@earendil-works/pi-coding-agent"
    )

    # Auth
    AUTH_ENABLED: bool = _bool(os.getenv("PI_DASHBOARD_AUTH_ENABLED"), False)
    JWT_SECRET: str = os.getenv("PI_DASHBOARD_JWT_SECRET", "change-me")
    JWT_TTL_HOURS: int = int(os.getenv("PI_DASHBOARD_JWT_TTL_HOURS", "24"))
    ADMIN_USER: str = os.getenv("PI_DASHBOARD_ADMIN_USER", "admin")
    ADMIN_PASSWORD: str = os.getenv("PI_DASHBOARD_ADMIN_PASSWORD", "admin")

    # OpenBrain
    OPENBRAIN_URL: str = os.getenv("OPENBRAIN_URL", "")
    OPENBRAIN_ACCESS_KEY: str = os.getenv("OPENBRAIN_ACCESS_KEY", "")

    # CORS
    CORS_ORIGINS: list[str] = _list(
        os.getenv("PI_DASHBOARD_CORS_ORIGINS"),
        ["http://localhost:5173", "http://127.0.0.1:5173"],
    )

    # Abgeleitete Pfade
    @property
    def settings_json(self) -> Path:
        return self.PI_AGENT_DIR / "settings.json"

    @property
    def models_json(self) -> Path:
        return self.PI_AGENT_DIR / "models.json"

    @property
    def auth_json(self) -> Path:
        return self.PI_AGENT_DIR / "auth.json"

    @property
    def trust_json(self) -> Path:
        return self.PI_AGENT_DIR / "trust.json"

    @property
    def sessions_dir(self) -> Path:
        return self.PI_AGENT_DIR / "sessions"

    @property
    def extensions_dir(self) -> Path:
        return self.PI_AGENT_DIR / "extensions"

    @property
    def skills_dir(self) -> Path:
        return self.PI_AGENT_DIR / "skills"

    @property
    def bin_dir(self) -> Path:
        return self.PI_AGENT_DIR / "bin"

    @property
    def npm_dir(self) -> Path:
        return self.PI_AGENT_DIR / "npm"


settings = Settings()
