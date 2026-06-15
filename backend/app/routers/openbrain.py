"""OpenBrain-Bridge: Proxy + Stats.

Wenn OPENBRAIN_URL und OPENBRAIN_ACCESS_KEY gesetzt sind, leiten wir
semantische Suche und Capture weiter. Sonst nur Stub.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_auth
from ..config import settings

router = APIRouter(prefix="/api/openbrain", tags=["openbrain"])


@router.get("/thoughts")
async def list_thoughts(_user: str = Depends(require_auth)) -> list[dict]:
    """Listet alle Gedanken aus dem OpenBrain (oder Stub-Daten)."""
    if not settings.OPENBRAIN_URL or not settings.OPENBRAIN_ACCESS_KEY:
        return _stub_thoughts()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{settings.OPENBRAIN_URL.rstrip('/')}/list",
                headers={"Authorization": f"Bearer {settings.OPENBRAIN_ACCESS_KEY}"},
            )
        if r.status_code == 200:
            data = r.json()
            items = data.get("thoughts", data.get("results", data.get("data", [])))
            if isinstance(items, list):
                return items
        return _stub_thoughts()
    except Exception:
        return _stub_thoughts()


def _stub_thoughts() -> list[dict]:
    """Demo-Gedanken fuer Graph-Darstellung wenn kein OpenBrain konfiguriert."""
    import uuid
    thoughts = [
        {"id": "1", "content": "[Projekt] Pi Dashboard Architektur", "tags": ["Projekt", "Architektur"], "type": "architecture", "ts": "2026-06-14T08:00:00"},
        {"id": "2", "content": "[Decision] Sub-Agenten auf Ollama umgestellt", "tags": ["Decision", "Infrastruktur"], "type": "decision", "ts": "2026-06-14T08:10:00"},
        {"id": "3", "content": "[Code] swarm-spawner ROLES-Registry aktualisiert", "tags": ["Code", "swarm-spawner"], "type": "code", "ts": "2026-06-14T08:15:00"},
        {"id": "4", "content": "[Bug] MiniMax-M3 Token-Verbrauch zu hoch", "tags": ["Bug", "Cost"], "type": "bug", "ts": "2026-06-14T07:00:00"},
        {"id": "5", "content": "[Health] Ollama Gemma4 12b laeuft stabil", "tags": ["Health", "Infrastruktur"], "type": "observation", "ts": "2026-06-14T09:00:00"},
        {"id": "6", "content": "[Projekt] OpenBrain Integration", "tags": ["Projekt", "OpenBrain"], "type": "feature", "ts": "2026-06-14T06:00:00"},
        {"id": "7", "content": "[Idea] Automatische Cost-Savings Reports", "tags": ["Idea", "Cost"], "type": "idea", "ts": "2026-06-13T22:00:00"},
        {"id": "8", "content": "[Infrastruktur] Ollama Server Config", "tags": ["Infrastruktur"], "type": "reference", "ts": "2026-06-13T20:00:00"},
        {"id": "9", "content": "[Code] context-workflow Stage-Machine", "tags": ["Code", "context-workflow"], "type": "code", "ts": "2026-06-13T18:00:00"},
        {"id": "10", "content": "[Decision] Single-User Auth fuer Pi Dashboard", "tags": ["Decision", "Pi-Dashboard"], "type": "decision", "ts": "2026-06-14T10:00:00"},
    ]
    return thoughts


@router.get("/graph")
async def graph_data(_user: str = Depends(require_auth)) -> dict:
    """Liefert Nodes + Edges fuer eine Graph-Visualisierung der Thoughts."""
    thoughts = await list_thoughts(_user)
    nodes = []
    edges = []
    type_colors = {
        "project": "#2ea043", "architecture": "#58a6ff", "decision": "#d29922",
        "code": "#a371f7", "bug": "#f85149", "observation": "#8b949e",
        "feature": "#2ea043", "idea": "#d29922", "reference": "#58a6ff",
    }
    for t in thoughts:
        tid = t.get("id", str(hash(t.get("content", ""))))
        ttype = (t.get("type") or t.get("thought_type") or "thought").lower()
        nodes.append({
            "id": tid,
            "label": (t.get("content") or "")[:40],
            "fullText": t.get("content", ""),
            "type": ttype,
            "tags": t.get("tags", []),
            "color": type_colors.get(ttype, "#8b949e"),
        })
        # Edges ueber gemeinsame Tags
        for other in thoughts:
            oid = other.get("id", "")
            if oid <= tid:
                continue
            shared = set(t.get("tags", [])) & set(other.get("tags", []))
            for tag in shared:
                edges.append({
                    "source": tid,
                    "target": oid,
                    "label": tag,
                })
    return {"nodes": nodes, "edges": edges}


@router.get("/status")
async def status(_user: str = Depends(require_auth)) -> dict:
    return {
        "configured": bool(settings.OPENBRAIN_URL) and bool(settings.OPENBRAIN_ACCESS_KEY),
        "url": settings.OPENBRAIN_URL or None,
        "has_key": bool(settings.OPENBRAIN_ACCESS_KEY),
    }


class SearchRequest(BaseModel):
    query: str
    limit: int = 5
    threshold: float = 0.3


@router.post("/search")
async def search(req: SearchRequest, _user: str = Depends(require_auth)) -> dict:
    """Semantische Suche im OpenBrain."""
    if not settings.OPENBRAIN_URL or not settings.OPENBRAIN_ACCESS_KEY:
        raise HTTPException(503, "OpenBrain nicht konfiguriert (OPENBRAIN_URL / OPENBRAIN_ACCESS_KEY)")
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"{settings.OPENBRAIN_URL.rstrip('/')}/search",
            headers={"Authorization": f"Bearer {settings.OPENBRAIN_ACCESS_KEY}"},
            json={"query": req.query, "limit": req.limit, "threshold": req.threshold},
        )
    if r.status_code != 200:
        raise HTTPException(r.status_code, f"OpenBrain error: {r.text[:300]}")
    return r.json()


@router.get("/stats")
async def stats(_user: str = Depends(require_auth)) -> dict:
    if not settings.OPENBRAIN_URL or not settings.OPENBRAIN_ACCESS_KEY:
        return {"configured": False}
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            f"{settings.OPENBRAIN_URL.rstrip('/')}/stats",
            headers={"Authorization": f"Bearer {settings.OPENBRAIN_ACCESS_KEY}"},
        )
    if r.status_code != 200:
        return {"configured": True, "error": r.text[:300]}
    return {"configured": True, "stats": r.json()}
