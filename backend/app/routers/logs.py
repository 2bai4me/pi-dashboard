"""Logs: Live-Stream (SSE) aus den letzten Session-Entries + Extension-Logs."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from ..auth import require_auth
from ..config import settings

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/recent")
async def recent_logs(
    _user: str = Depends(require_auth),
    limit: int = Query(100, ge=1, le=500),
    source: str = Query("sessions", pattern="^(sessions|extensions|all)$"),
) -> list[dict]:
    """Letzte Log-Zeilen (statisch, ohne Live-Stream)."""
    out: list[dict] = []

    if source in ("sessions", "all"):
        sessions_dir = settings.sessions_dir
        if sessions_dir.exists():
            # neueste Session zuerst
            files = sorted(sessions_dir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
            for f in files[:5]:
                if f.suffix != ".jsonl":
                    continue
                try:
                    lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
                except OSError:
                    continue
                for line in lines[-limit:]:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        out.append({
                            "source": "session",
                            "session": f.stem,
                            "raw": line[:500],
                            "ts": time.time(),
                        })
                        continue
                    out.append(_format_entry(entry, f.stem, "session"))

    if source in ("extensions", "all"):
        ext_dir = settings.extensions_dir
        if ext_dir.exists():
            for ext in ext_dir.iterdir():
                log = ext / "log.txt"
                if not log.exists():
                    log = ext / "debug.log"
                if not log.exists():
                    continue
                try:
                    lines = log.read_text(encoding="utf-8", errors="ignore").splitlines()
                except OSError:
                    continue
                for line in lines[-limit:]:
                    out.append({
                        "source": "extension",
                        "extension": ext.name,
                        "raw": line[:500],
                        "ts": log.stat().st_mtime,
                    })

    out.sort(key=lambda e: e.get("ts", 0), reverse=True)
    return out[:limit]


def _format_entry(entry: dict, session_id: str, source: str) -> dict:
    etype = entry.get("type", "?")
    msg = entry.get("message", {})
    role = msg.get("role") if isinstance(msg, dict) else None
    text = ""
    if isinstance(msg, dict):
        c = msg.get("content")
        if isinstance(c, str):
            text = c[:200]
        elif isinstance(c, list):
            for blk in c:
                if isinstance(blk, dict) and blk.get("type") == "text":
                    text = blk.get("text", "")[:200]
                    break
    return {
        "source": source,
        "session": session_id,
        "type": etype,
        "role": role,
        "text": text,
        "ts": entry.get("timestamp", ""),
        "model": msg.get("model") if isinstance(msg, dict) else None,
    }


@router.get("/stream")
async def stream_logs(
    _user: str = Depends(require_auth),
    interval: float = Query(2.0, ge=0.5, le=10.0),
    source: str = Query("sessions", pattern="^(sessions|extensions|all)$"),
):
    """SSE-Stream mit neuen Log-Events."""
    last_state: dict[str, float] = {}

    async def gen():
        while True:
            entries = await recent_logs(_user=_user, limit=20, source=source)
            for e in entries:
                key = f"{e.get('source')}-{e.get('session') or e.get('extension')}-{e.get('raw', '')}"
                ts = e.get("ts", 0)
                if isinstance(ts, str):
                    # try parse
                    try:
                        from datetime import datetime
                        ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                    except Exception:
                        ts = 0
                if last_state.get(key) == ts:
                    continue
                last_state[key] = ts
                yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
            await asyncio.sleep(interval)

    return StreamingResponse(gen(), media_type="text/event-stream")
