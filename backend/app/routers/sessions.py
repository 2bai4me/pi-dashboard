"""Sessions: Liste, Detail, Suche, Löschen."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth import require_auth
from ..config import settings

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionInfo(BaseModel):
    id: str
    path: str
    name: str | None
    created_at: str | None
    modified_at: str | None
    size_bytes: int
    message_count: int
    model: str | None
    cwd: str | None
    first_user_message: str | None


class SessionMessage(BaseModel):
    role: str
    content: str
    timestamp: str | None
    type: str | None = None
    name: str | None = None


def _parse_session(path: Path) -> SessionInfo:
    """Liest Header und ein paar Metadaten aus einer Session-Datei."""
    sid = path.stem
    info = SessionInfo(
        id=sid, path=str(path), name=None, created_at=None, modified_at=None,
        size_bytes=path.stat().st_size, message_count=0, model=None, cwd=None,
        first_user_message=None,
    )
    mtime = path.stat().st_mtime
    info.modified_at = datetime.fromtimestamp(mtime).isoformat()

    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = entry.get("type", "message")
                if etype == "session" and "header" in entry:
                    hdr = entry["header"]
                    info.cwd = hdr.get("cwd")
                    info.created_at = hdr.get("timestamp")
                elif etype == "message":
                    info.message_count += 1
                    msg = entry.get("message", {})
                    if info.model is None and isinstance(msg, dict):
                        info.model = msg.get("model")
                    if info.first_user_message is None and msg.get("role") == "user":
                        c = msg.get("content")
                        if isinstance(c, str):
                            info.first_user_message = c[:200]
                        elif isinstance(c, list):
                            for blk in c:
                                if isinstance(blk, dict) and blk.get("type") == "text":
                                    info.first_user_message = blk.get("text", "")[:200]
                                    break
                elif etype == "session_name":
                    info.name = entry.get("name")
                # nur erste 200 Zeilen für die Übersicht scannen
                if i > 200:
                    break
    except OSError:
        pass
    return info


@router.get("", response_model=list[SessionInfo])
async def list_sessions(
    _user: str = Depends(require_auth),
    limit: int = Query(50, ge=1, le=500),
    sort: str = Query("modified", pattern="^(modified|created|name)$"),
) -> list[SessionInfo]:
    sessions_dir = settings.sessions_dir
    if not sessions_dir.exists():
        return []

    infos: list[SessionInfo] = []
    for f in sessions_dir.iterdir():
        if f.suffix == ".jsonl" and f.is_file():
            try:
                infos.append(_parse_session(f))
            except Exception:
                continue

    if sort == "modified":
        infos.sort(key=lambda s: s.modified_at or "", reverse=True)
    elif sort == "created":
        infos.sort(key=lambda s: s.created_at or "", reverse=True)
    elif sort == "name":
        infos.sort(key=lambda s: s.name or s.id)

    return infos[:limit]


@router.get("/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str, _user: str = Depends(require_auth)) -> SessionInfo:
    path = settings.sessions_dir / f"{session_id}.jsonl"
    if not path.exists():
        raise HTTPException(404, "Session not found")
    return _parse_session(path)


@router.get("/{session_id}/messages", response_model=list[SessionMessage])
async def get_session_messages(
    session_id: str,
    _user: str = Depends(require_auth),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
) -> list[SessionMessage]:
    path = settings.sessions_dir / f"{session_id}.jsonl"
    if not path.exists():
        raise HTTPException(404, "Session not found")

    out: list[SessionMessage] = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") != "message":
                continue
            msg = entry.get("message", {})
            content = msg.get("content")
            if isinstance(content, list):
                texts = [
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                content_str = "\n".join(t for t in texts if t)
            else:
                content_str = str(content or "")
            out.append(SessionMessage(
                role=msg.get("role", "unknown"),
                content=content_str[:5000],  # truncate für UI
                timestamp=entry.get("timestamp"),
            ))
    return out[offset:offset + limit]


@router.get("/search/query")
async def search_sessions(
    q: str = Query(..., min_length=1),
    _user: str = Depends(require_auth),
    limit: int = Query(20, ge=1, le=100),
) -> list[SessionInfo]:
    """Einfache Volltextsuche."""
    needle = q.lower()
    sessions = await list_sessions(_user=_user, limit=500, sort="modified")
    out: list[SessionInfo] = []
    for s in sessions:
        path = Path(s.path)
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if needle in content.lower():
                out.append(s)
                if len(out) >= limit:
                    break
        except OSError:
            continue
    return out


@router.delete("/{session_id}")
async def delete_session(session_id: str, _user: str = Depends(require_auth)) -> dict:
    path = settings.sessions_dir / f"{session_id}.jsonl"
    if not path.exists():
        raise HTTPException(404, "Session not found")
    path.unlink()
    return {"ok": True, "deleted": session_id}


@router.get("/stats/summary")
async def session_stats(_user: str = Depends(require_auth)) -> dict:
    sessions = await list_sessions(_user=_user, limit=10000, sort="modified")
    models: dict[str, int] = {}
    total_size = 0
    for s in sessions:
        total_size += s.size_bytes
        if s.model:
            models[s.model] = models.get(s.model, 0) + 1
    return {
        "total": len(sessions),
        "total_size_bytes": total_size,
        "by_model": models,
    }
