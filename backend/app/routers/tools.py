"""Tools: Liste, Toggle, builtin-Info.

Hinweis: pi-coding-agent hat 7 builtin tools. Toggle erfolgt über die
`enabledModels`-Liste und Extensions-Config. Hier listen wir die bekannten
built-ins und versuchen Status zu erkennen.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import require_auth
from ..config import settings
from ..utils import read_json

router = APIRouter(prefix="/api/tools", tags=["tools"])

BUILTIN_TOOLS = [
    {"name": "read", "description": "Read files (with offset/limit)"},
    {"name": "write", "description": "Create or overwrite files"},
    {"name": "edit", "description": "Multi-edit files (edits[] array)"},
    {"name": "bash", "description": "Execute shell commands"},
    {"name": "grep", "description": "ripgrep-based content search"},
    {"name": "find", "description": "fd-based file finder"},
    {"name": "ls", "description": "List directory contents"},
]


class ToolInfo(BaseModel):
    name: str
    description: str
    builtin: bool


@router.get("", response_model=list[ToolInfo])
async def list_tools(_user: str = Depends(require_auth)) -> list[ToolInfo]:
    """Built-in tools listen. Custom tools aus Extensions werden in /extensions angezeigt."""
    return [ToolInfo(**t, builtin=True) for t in BUILTIN_TOOLS]


@router.get("/summary")
async def tools_summary(_user: str = Depends(require_auth)) -> dict:
    """Übersicht fürs Dashboard."""
    return {
        "builtin_count": len(BUILTIN_TOOLS),
        "builtin_tools": [t["name"] for t in BUILTIN_TOOLS],
        # Custom tools aus extensions/ werden separat geladen
        "extensions_dir": str(settings.extensions_dir),
    }
