"""Hilfsfunktionen: pi-Pfade, JSON-Laden, Secret-Masking, Subprozesse."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .config import settings


# ── Pfade ──────────────────────────────────────────────────────────────

def pi_agent_path(*parts: str) -> Path:
    """Gibt einen Pfad innerhalb des PI-Agent-Verzeichnisses zurück."""
    return settings.PI_AGENT_DIR.joinpath(*parts)


def read_json(path: Path, default: Any = None) -> Any:
    """Liest eine JSON-Datei, gibt default zurück wenn nicht existent."""
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, data: Any, indent: int = 2) -> None:
    """Schreibt atomar als JSON (temp + replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
    tmp.replace(path)


# ── Secret-Masking ────────────────────────────────────────────────────

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),                # sk-... API keys
    re.compile(r"sk-or-v1-[A-Za-z0-9_\-]{16,}"),         # OpenRouter
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),            # Anthropic
    re.compile(r"sk-cp-[A-Za-z0-9_\-]{16,}"),            # MiniMax style
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{16,}"),   # Bearer tokens
    re.compile(r"(?i)(api[_-]?key|token|password|secret)[\"':=\s]+[\"']?([^\"',\s}]+)"),
]


def mask_secrets(text: str) -> str:
    """Maskiert bekannte Secret-Patterns in einem String."""
    if not text:
        return text
    out = text
    for pat in _SECRET_PATTERNS[:4]:
        out = pat.sub(lambda m: m.group(0)[:6] + "…" + m.group(0)[-4:], out)
    for pat in _SECRET_PATTERNS[4:]:
        out = pat.sub(lambda m: m.group(1) + "=***", out)
    return out


def mask_config(config: dict | list) -> dict | list:
    """Rekursiv Secrets in einer Config-Dict maskieren."""
    sensitive_keys = {"apiKey", "api_key", "token", "password", "secret", "key"}

    def _walk(obj):
        if isinstance(obj, dict):
            return {k: ("***MASKED***" if k in sensitive_keys else _walk(v)) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_walk(x) for x in obj]
        if isinstance(obj, str) and len(obj) > 20:
            return mask_secrets(obj)
        return obj

    return _walk(config)


# ── Subprozesse ───────────────────────────────────────────────────────

def run_pi(args: list[str], timeout: int = 30, cwd: Path | None = None) -> dict:
    """Fuehrt `pi` mit den gegebenen Args aus. Windows-kompatibel (.cmd / .bat)."""
    is_win = os.name == "nt"
    if is_win:
        full = f"{settings.PI_BIN} {' '.join(args)}"
        use_shell = True
    else:
        full = [settings.PI_BIN, *args]
        use_shell = False
    try:
        proc = subprocess.run(
            full,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            env={**os.environ, "PI_OFFLINE": "1", "NO_COLOR": "0"},
            shell=use_shell,
        )
        return {
            "ok": proc.returncode == 0,
            "exitCode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "exitCode": -1,
            "stdout": "",
            "stderr": f"pi binary not found: {settings.PI_BIN}",
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "exitCode": -2,
            "stdout": "",
            "stderr": f"Timeout after {timeout}s",
        }


def which(bin_name: str) -> str | None:
    """Pfad zu einem ausführbaren Binary."""
    return shutil.which(bin_name)
