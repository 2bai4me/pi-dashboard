"""Skills: Liste, Inhalt, Toggle (über packages in settings)."""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_auth
from ..config import settings
from ..utils import read_json, write_json

router = APIRouter(prefix="/api/skills", tags=["skills"])

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


class SkillInfo(BaseModel):
    name: str
    description: str | None
    path: str
    scope: str  # "user" | "project"
    size_bytes: int
    has_frontmatter: bool
    enabled: bool | None = None


def _parse_skill(path: Path, scope: str) -> SkillInfo | None:
    """Liest SKILL.md Frontmatter."""
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    name = path.parent.name
    description = None
    has_fm = False
    m = FRONTMATTER_RE.match(content)
    if m:
        has_fm = True
        try:
            fm = yaml.safe_load(m.group(1)) or {}
            if isinstance(fm, dict):
                name = fm.get("name", name)
                description = fm.get("description")
        except yaml.YAMLError:
            pass
    return SkillInfo(
        name=name,
        description=description,
        path=str(path),
        scope=scope,
        size_bytes=path.stat().st_size,
        has_frontmatter=has_fm,
    )


@router.get("", response_model=list[SkillInfo])
async def list_skills(_user: str = Depends(require_auth)) -> list[SkillInfo]:
    """User-Skills aus ~/.pi/agent/skills/."""
    out: list[SkillInfo] = []
    skills_dir = settings.skills_dir
    if skills_dir.exists():
        for skill_md in skills_dir.rglob("SKILL.md"):
            info = _parse_skill(skill_md, "user")
            if info:
                out.append(info)
    return out


@router.get("/{name:path}")
async def get_skill(name: str, _user: str = Depends(require_auth)) -> dict:
    """Skill-Detail inkl. Inhalt."""
    # name kann mit oder ohne /SKILL.md sein
    for base in [settings.skills_dir]:
        if not base.exists():
            continue
        for skill_md in base.rglob("SKILL.md"):
            if skill_md.parent.name == name or str(skill_md).endswith(f"/{name}/SKILL.md"):
                content = skill_md.read_text(encoding="utf-8", errors="ignore")
                return {
                    "path": str(skill_md),
                    "name": skill_md.parent.name,
                    "content": content,
                    "size_bytes": skill_md.stat().st_size,
                }
    raise HTTPException(404, "Skill not found")
