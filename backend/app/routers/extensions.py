"""PI-Extensions-Status und Detail-Infos.

Liest die 5 bekannten Extensions (swarm-spawner, context-workflow, cost-tracker,
openbrain-bridge, git-checkpoint) und zeigt Sub-Agent-Status, Logs, etc.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_auth
from ..config import settings
from .overview import KNOWN_EXTENSIONS

router = APIRouter(prefix="/api/extensions", tags=["extensions"])


class ExtensionDetail(BaseModel):
    name: str
    description: str
    path: str
    has_skill: bool
    has_index: bool
    skill_excerpt: str | None = None
    files: list[str]
    size_bytes: int
    modified_at: str | None


@router.get("")
async def list_extensions_summary(_user: str = Depends(require_auth)) -> list[dict]:
    """Kompakte Liste mit Sub-Agent-Status für swarm-spawner."""
    out: list[dict] = []
    for name, desc in KNOWN_EXTENSIONS.items():
        ext_dir = settings.extensions_dir / name
        installed = ext_dir.exists()
        entry = {
            "name": name,
            "installed": installed,
            "description": desc,
            "path": str(ext_dir) if installed else None,
        }
        # Sub-Agent-Status für swarm-spawner
        if name == "swarm-spawner" and installed:
            entry["sub_agents"] = _swarm_status()
            entry["sub_agent_model"] = {
                "provider": "ollama",
                "model": "gemma4:12b",
                "rationale": "Lokal, 0 Token-Kosten, 262k context. Schützt MiniMax-M3-Budget der Hauptinstanz.",
                "estimated_savings_per_workflow_usd": 0.45,
            }
        # Cost-Tracker: aktuelle Stats
        if name == "cost-tracker" and installed:
            entry["cost"] = _cost_status()
        # OpenBrain: Access-Key-Status
        if name == "openbrain-bridge" and installed:
            entry["openbrain"] = {
                "url_configured": bool(settings.OPENBRAIN_URL),
                "access_key_configured": bool(settings.OPENBRAIN_ACCESS_KEY),
            }
        out.append(entry)
    return out


@router.get("/{name}")
async def get_extension(name: str, _user: str = Depends(require_auth)) -> ExtensionDetail:
    if name not in KNOWN_EXTENSIONS:
        raise HTTPException(404, f"Unknown extension: {name}")
    ext_dir = settings.extensions_dir / name
    if not ext_dir.exists():
        raise HTTPException(404, f"Extension not installed: {name}")

    files = sorted([str(p.relative_to(ext_dir)) for p in ext_dir.rglob("*") if p.is_file()])
    total = sum((ext_dir / f).stat().st_size for f in files)
    skill = ext_dir / "SKILL.md"
    index = ext_dir / "index.ts"
    excerpt = None
    if skill.exists():
        text = skill.read_text(encoding="utf-8", errors="ignore")
        excerpt = text[:500] + ("…" if len(text) > 500 else "")

    mt = ext_dir.stat().st_mtime
    return ExtensionDetail(
        name=name,
        description=KNOWN_EXTENSIONS[name],
        path=str(ext_dir),
        has_skill=skill.exists(),
        has_index=index.exists(),
        skill_excerpt=excerpt,
        files=files,
        size_bytes=total,
        modified_at=datetime.fromtimestamp(mt).isoformat(),
    )


# ── swarm-spawner Sub-Agent-Status ────────────────────────────────────

def _swarm_status() -> dict:
    """Liest /tmp/pi-swarm/ für laufende und abgeschlossene Sub-PIs."""
    import os
    import tempfile
    tmp = Path(tempfile.gettempdir())
    patterns = [tmp / "pi-swarm-pi-coder-*", tmp / "pi-swarm-pi-tester-*",
                tmp / "pi-swarm-pi-reviewer-*", tmp / "pi-swarm-pi-fixer-*"]
    active: list[dict] = []
    completed: list[dict] = []
    for pat in patterns:
        for d in pat.parent.glob(pat.name):
            if not d.is_dir():
                continue
            result_file = d / "result.json"
            entry = {
                "session_dir": str(d),
                "name": d.name,
                "created_at": datetime.fromtimestamp(d.stat().st_mtime).isoformat(),
                "model": "ollama/gemma4:12b",  # Default seit 14.06.2026
            }
            if result_file.exists():
                try:
                    data = json.loads(result_file.read_text(encoding="utf-8"))
                    entry.update({
                        "completed": True,
                        "exitCode": data.get("exitCode"),
                        "durationMs": data.get("durationMs"),
                        "role": data.get("role"),
                    })
                    completed.append(entry)
                except (json.JSONDecodeError, OSError):
                    completed.append(entry)
            else:
                entry["completed"] = False
                active.append(entry)
    return {
        "active": sorted(active, key=lambda e: e["created_at"], reverse=True),
        "completed": sorted(completed, key=lambda e: e["created_at"], reverse=True)[:20],
        "active_count": len(active),
        "completed_count": len(completed),
    }


# ── cost-tracker Status ───────────────────────────────────────────────

def _cost_status() -> dict:
    """Liest cost-tracker Extension-Config + berechnet einfache Stats."""
    from ..utils import read_json
    cfg = read_json(settings.settings_json, {}) or {}
    # Cost-Tracker schreibt ggf. in eine eigene Datei
    cost_file = settings.PI_AGENT_DIR / "cost-tracker.json"
    cost_data = read_json(cost_file, None) if cost_file.exists() else None
    return {
        "file_exists": cost_file.exists(),
        "data": cost_data,
        "default_model": cfg.get("defaultModel"),
    }
