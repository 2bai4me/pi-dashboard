"""API Keys / Environment Variables: Verwaltung der .env und auth.json."""
from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_auth
from ..config import settings

router = APIRouter(prefix="/api/env", tags=["env"])

ENV_FILE = settings.PI_AGENT_DIR / ".env.override"
ENV_KEYS = [
    # Provider Keys
    {"key": "MINIMAX_API_KEY", "category": "LLM Provider", "description": "MiniMax API Key (MiniMax-Direct)"},
    {"key": "OPENROUTER_API_KEY", "category": "LLM Provider", "description": "OpenRouter API Key"},
    {"key": "ANTHROPIC_API_KEY", "category": "LLM Provider", "description": "Anthropic API Key"},
    {"key": "OPENAI_API_KEY", "category": "LLM Provider", "description": "OpenAI API Key"},
    {"key": "DEEPSEEK_API_KEY", "category": "LLM Provider", "description": "DeepSeek API Key"},

    # Agent
    {"key": "PI_OFFLINE", "category": "Agent", "description": "Disable network operations"},
    {"key": "PI_SKIP_VERSION_CHECK", "category": "Agent", "description": "Skip version check at startup"},
    {"key": "PI_CACHE_RETENTION", "category": "Agent", "description": "Prompt cache TTL: long or short"},
    {"key": "PI_EXPERIMENTAL", "category": "Agent", "description": "Enable experimental features"},

    # OpenBrain
    {"key": "OPENBRAIN_URL", "category": "OpenBrain", "description": "OpenBrain server URL"},
    {"key": "OPENBRAIN_ACCESS_KEY", "category": "OpenBrain", "description": "OpenBrain access key"},

    # Ollama
    {"key": "OLLAMA_HOST", "category": "Ollama", "description": "Ollama server URL (default: 127.0.0.1:11434)"},
]


def _read_env_overrides() -> dict[str, str]:
    """Liest .env.override (user-set values)."""
    if not ENV_FILE.exists():
        return {}
    overrides = {}
    try:
        for line in ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            overrides[k.strip()] = v.strip().strip("\"'")
    except OSError:
        pass
    return overrides


def _write_env_overrides(overrides: dict[str, str]) -> None:
    """Schreibt .env.override."""
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for key in [e["key"] for e in ENV_KEYS]:
        if key in overrides:
            lines.append(f"{key}={overrides[key]}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _get_env_value(key: str) -> tuple[bool, str | None]:
    """Prueft ob ein Env-Var gesetzt ist und gibt den Wert (maskiert) zurueck."""
    # 1. Check override file
    overrides = _read_env_overrides()
    if key in overrides:
        val = overrides[key]
        return (True, val[:6] + "…" + val[-4:] if len(val) > 20 else val)

    # 2. Check process env
    val = os.environ.get(key)
    if val:
        return (True, val[:6] + "…" + val[-4:] if len(val) > 20 else "***set***")

    # 3. Check backend .env
    backend_env = Path(__file__).resolve().parent.parent.parent / ".env"
    if backend_env.exists():
        try:
            for line in backend_env.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith(f"{key}="):
                    v = line.split("=", 1)[1].strip().strip("\"'")
                    if v:
                        return (True, v[:6] + "…" + v[-4:] if len(v) > 20 else "***set***")
        except OSError:
            pass

    return (False, None)


class SetEnvRequest(BaseModel):
    key: str
    value: str


@router.get("/vars")
async def list_env_vars(_user: str = Depends(require_auth)) -> list[dict]:
    """Listet alle bekannten Environment-Variablen mit aktuellem Status."""
    result = []
    for entry in ENV_KEYS:
        is_set, masked = _get_env_value(entry["key"])
        result.append({
            "key": entry["key"],
            "category": entry["category"],
            "description": entry["description"],
            "set": is_set,
            "masked_value": masked,
        })
    return result


@router.put("/vars")
async def set_env_var(req: SetEnvRequest, _user: str = Depends(require_auth)) -> dict:
    """Setzt eine Environment-Variable im .env.override."""
    if req.key not in [e["key"] for e in ENV_KEYS]:
        raise HTTPException(400, f"Unknown env var: {req.key}")
    overrides = _read_env_overrides()
    overrides[req.key] = req.value
    _write_env_overrides(overrides)
    return {"ok": True, "key": req.key, "set": bool(req.value)}


@router.delete("/vars/{key}")
async def delete_env_var(key: str, _user: str = Depends(require_auth)) -> dict:
    """Loescht eine Environment-Variable aus dem .env.override."""
    overrides = _read_env_overrides()
    if key in overrides:
        del overrides[key]
        _write_env_overrides(overrides)
    return {"ok": True, "deleted": key}


@router.get("/sensitive")
async def sensitive_data_check(_user: str = Depends(require_auth)) -> dict:
    """Prueft ob Secrets in env oder config leaken."""
    suspects = []
    for key, val in os.environ.items():
        if re.search(r"(?i)(key|token|secret|password)", key) and val:
            suspects.append(key)
    return {
        "env_secrets_found": len(suspects),
        "secrets": suspects,
        "warnings": [f"FOUND: {k}" for k in suspects[:10]] if suspects else [],
    }
