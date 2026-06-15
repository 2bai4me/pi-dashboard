"""Roles: Liest Rollen-Registry aus swarm-spawner Extension + SKILL.md."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import require_auth
from ..config import settings

router = APIRouter(prefix="/api/roles", tags=["roles"])

ROLES_SECTION_RE = re.compile(
    r'const\s+ROLES\s*:\s*Record<Role,\s*RoleConfig>\s*=\s*\{'
    r'(.*?)\n\};', re.DOTALL
)
ROLE_ENTRY_RE = re.compile(
    r'"(?P<name>pi-coder|pi-tester|pi-reviewer|pi-fixer)"\s*:\s*\{'
    r'(?P<body>.*?)\n  \},', re.DOTALL
)
FIELD_RE = re.compile(
    r'(?P<key>\w+)\s*:\s*'
    r'(?P<val>'
    r'"[^"]*"|'           # string
    r'SUB_AGENT_PROVIDER|'  # constant ref
    r'SUB_AGENT_MODEL|'     # constant ref
    r'\[[^\]]*\]|'        # array
    r'true|false|'         # bool
    r'\d+(?:\.\d+)?'       # number
    r')',
)

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class RoleDetail(BaseModel):
    name: str
    provider: str
    model: str
    systemPrompt: str
    toolWhitelist: list[str]
    timeoutSec: int
    freshContext: bool
    estimatedSavingsUsd: float = 0.0
    skillFile: str | None = None
    skillText: str | None = None


def _parse_role_value(val: str, constants: dict[str, str] | None = None) -> str | list[str] | bool | int | float:
    val = val.strip().rstrip(",")
    # Resolve constants like SUB_AGENT_PROVIDER
    if constants and val in constants:
        return constants[val]
    if val.startswith('"') and val.endswith('"'):
        return val[1:-1]
    if val.startswith("["):
        items = val.strip("[]").split(",")
        return [i.strip().strip('"').strip("'") for i in items if i.strip()]
    if val in ("true", "false"):
        return val == "true"
    try:
        return int(val)
    except ValueError:
        try:
            return float(val)
        except ValueError:
            return val


def _read_index_ts() -> str | None:
    ext_dir = settings.extensions_dir / "swarm-spawner"
    index = ext_dir / "index.ts"
    return index.read_text(encoding="utf-8", errors="ignore") if index.exists() else None


def _parse_constants(index: str) -> dict[str, str]:
    """Liest Konstanten wie SUB_AGENT_PROVIDER / SUB_AGENT_MODEL."""
    const_re = re.compile(r'const\s+(\w+)\s*=\s*"([^"]+)"\s*;?')
    return {m.group(1): m.group(2) for m in const_re.finditer(index)}


def _parse_roles(index: str) -> list[dict]:
    """Parsed die ROLES-Konstante aus der index.ts."""
    constants = _parse_constants(index)
    roles: list[dict] = []
    m = ROLES_SECTION_RE.search(index)
    if not m:
        return []
    body = m.group(1)
    for entry in ROLE_ENTRY_RE.finditer(body):
        name = entry.group("name")
        rbody = entry.group("body")
        role = {"name": name}
        for f in FIELD_RE.finditer(rbody):
            key = f.group("key")
            val = _parse_role_value(f.group("val"), constants)
            role[key] = val
        roles.append(role)
    return roles


@router.get("", response_model=list[RoleDetail])
async def list_roles(_user: str = Depends(require_auth)) -> list[RoleDetail]:
    """Liest die 4 Rollen aus swarm-spawner/index.ts."""
    index = _read_index_ts()
    skill = _read_skill_md()
    if not index:
        return []
    parsed = _parse_roles(index)
    out: list[RoleDetail] = []
    for r in parsed:
        out.append(RoleDetail(
            name=r.get("name", "?"),
            provider=r.get("provider", "?"),
            model=r.get("model", "?"),
            systemPrompt=r.get("systemPrompt", ""),
            toolWhitelist=r.get("toolWhitelist", []),
            timeoutSec=r.get("timeoutSec", 300),
            freshContext=r.get("freshContext", True),
            estimatedSavingsUsd=r.get("estimatedSavingsUsd", 0.0),
            skillFile=skill,
            skillText=_read_skill_text(),
        ))
    return out


def _read_skill_md() -> str | None:
    p = settings.extensions_dir / "swarm-spawner" / "SKILL.md"
    return str(p) if p.exists() else None


def _read_skill_text() -> str | None:
    p = settings.extensions_dir / "swarm-spawner" / "SKILL.md"
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8", errors="ignore")
    m = FRONTMATTER_RE.match(text)
    return text


@router.get("/files")
async def role_files(_user: str = Depends(require_auth)) -> list[dict]:
    """Listet alle Dateien, die die Rollen beschreiben."""
    ext_dir = settings.extensions_dir / "swarm-spawner"
    if not ext_dir.exists():
        return []
    out: list[dict] = []
    for f in ext_dir.rglob("*"):
        if f.is_file():
            text = f.read_text(encoding="utf-8", errors="ignore")
            out.append({
                "path": str(f.relative_to(ext_dir)),
                "full_path": str(f),
                "size_bytes": f.stat().st_size,
                "lines": len(text.splitlines()),
                "content": text[:10000],  # max 10k chars
            })
    return out


ORG_ROLES = [
    {
        "name": "CEO-digital", "emoji": "👑",
        "description": "Chief Executive Officer — strategische Entscheidungen, Vision, Budget-Steuerung",
        "provider": "minimax-direct", "model": "minimax-m3",
        "systemPrompt": "You are CEO-digital — the strategic decision-maker and owner of the PI Agent system.\n" +
          "- Define vision, priorities, and high-level strategy\n" +
          "- Review and approve architectural decisions\n" +
          "- Allocate token budgets and model resources\n" +
          "- Ultimate authority on all PI Agent operations\n" +
          "- Focus: business value, cost efficiency, strategic direction",
        "toolWhitelist": ["read", "bash", "grep"],
    },
    {
        "name": "CIO", "emoji": "🏗️",
        "description": "Chief Information Officer — technische Infrastruktur, Security, Architektur",
        "provider": "ollama", "model": "gemma4:12b",
        "systemPrompt": "You are CIO — responsible for technical infrastructure, security, and architecture.\n" +
          "- Evaluate technical feasibility and risks\n" +
          "- Define architecture standards and best practices\n" +
          "- Oversee security, compliance, and data governance\n" +
          "- Manage technology stack decisions\n" +
          "- Focus: system integrity, scalability, maintainability",
        "toolWhitelist": ["read", "write", "bash", "grep", "find", "ls"],
    },
    {
        "name": "CMO", "emoji": "📢",
        "description": "Chief Marketing Officer — Marketing, Branding, Kommunikation",
        "provider": "ollama", "model": "gemma4:12b",
        "systemPrompt": "You are CMO — responsible for marketing, communication, and brand strategy.\n" +
          "- Craft compelling messaging and positioning\n" +
          "- Analyze market trends and competitive landscape\n" +
          "- Generate content strategy and copy\n" +
          "- Evaluate brand impact and audience engagement\n" +
          "- Focus: clarity, persuasion, brand consistency",
        "toolWhitelist": ["read", "write", "bash", "grep"],
    },
    {
        "name": "CFO", "emoji": "💰",
        "description": "Chief Financial Officer — Kosten, Budget, ROI, Resource Optimization",
        "provider": "ollama", "model": "gemma4:12b",
        "systemPrompt": "You are CFO — responsible for financial planning, cost analysis, and resource optimization.\n" +
          "- Track and analyze token costs across providers\n" +
          "- Optimize resource allocation and model selection\n" +
          "- Calculate ROI of agent operations\n" +
          "- Forecast budget needs and cost trends\n" +
          "- Focus: cost efficiency, value optimization, financial transparency",
        "toolWhitelist": ["read", "bash", "grep"],
    },
]


@router.get("/org")
async def list_org_roles(_user: str = Depends(require_auth)) -> list[dict]:
    """Organisationale Rollen (CEO-digital, CIO, CMO, CFO)."""
    return ORG_ROLES


@router.get("/all")
async def list_all_roles(_user: str = Depends(require_auth)) -> dict:
    """Alle Rollen: Sub-Agenten + Organisational."""
    sub = await list_roles(_user)
    return {
        "sub_agents": [r.model_dump() for r in sub],
        "org_roles": ORG_ROLES,
        "total": len(sub) + len(ORG_ROLES),
    }
