"""Status, PI-Version, Extensions-Status, System-Metriken."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import psutil
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import require_auth
from ..config import settings
from ..utils import read_json

router = APIRouter(prefix="/api/overview", tags=["overview"])


class PiVersion(BaseModel):
    version: str | None
    package: str


class ExtensionStatus(BaseModel):
    name: str
    installed: bool
    has_skill: bool
    has_index: bool
    path: str | None
    size_bytes: int | None
    description: str | None = None


class SystemStats(BaseModel):
    os: str
    python: str
    cpu_count: int
    cpu_percent: float
    memory: dict
    disk: dict
    uptime_s: float
    vram: dict | None = None


KNOWN_EXTENSIONS = {
    "swarm-spawner": "Spawns sub-PI instances (pi-coder, pi-tester, pi-reviewer, pi-fixer)",
    "context-workflow": "Stage-transition workflow (write → test → review → fix → verify)",
    "cost-tracker": "Tracks token usage and costs across models and sub-agents",
    "openbrain-bridge": "Bridges PI session events to OpenBrain knowledge base",
    "git-checkpoint": "Creates git checkpoints before risky operations",
}


def _pi_version() -> str | None:
    import platform
    is_win = platform.system() == "Windows"
    cmd = f"{settings.PI_BIN} --version" if is_win else [settings.PI_BIN, "--version"]
    try:
        out = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=5,
            shell=is_win,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


@router.get("/version", response_model=PiVersion)
async def get_pi_version(_user: str = Depends(require_auth)) -> PiVersion:
    return PiVersion(version=_pi_version(), package=settings.PI_CODING_AGENT_PKG)


@router.get("/extensions", response_model=list[ExtensionStatus])
async def list_extensions(_user: str = Depends(require_auth)) -> list[ExtensionStatus]:
    """Status der bekannten PI-Extensions."""
    out: list[ExtensionStatus] = []
    for name, desc in KNOWN_EXTENSIONS.items():
        ext_dir = settings.extensions_dir / name
        index = ext_dir / "index.ts"
        skill = ext_dir / "SKILL.md"
        out.append(
            ExtensionStatus(
                name=name,
                installed=ext_dir.exists(),
                has_skill=skill.exists(),
                has_index=index.exists(),
                path=str(ext_dir) if ext_dir.exists() else None,
                size_bytes=sum(f.stat().st_size for f in ext_dir.rglob("*") if f.is_file()) or None
                if ext_dir.exists() else None,
                description=desc,
            )
        )
    return out


@router.get("/system", response_model=SystemStats)
async def get_system_stats(_user: str = Depends(require_auth)) -> SystemStats:
    import platform, time
    vm = psutil.virtual_memory()
    du = shutil.disk_usage(str(settings.PI_AGENT_DIR))
    
    # VRAM / GPU detection
    vram_info = _get_vram_info()
    
    # VRAM zum SystemStats-Ergebnis
    vram_data = _get_vram_info()
    
    return SystemStats(
        os=f"{platform.system()} {platform.release()}",
        python=platform.python_version(),
        cpu_count=psutil.cpu_count() or 1,
        cpu_percent=psutil.cpu_percent(interval=0.3),
        memory={
            "total": vm.total, "available": vm.available,
            "percent": vm.percent, "used": vm.used,
        },
        disk={
            "total": du.total, "used": du.used, "free": du.free,
            "percent": (du.used / du.total) * 100 if du.total else 0,
            "path": str(settings.PI_AGENT_DIR),
        },
        uptime_s=time.time() - psutil.boot_time(),
        vram=vram_data,
    )


@router.get("/vram")
async def get_vram(_user: str = Depends(require_auth)) -> dict:
    """VRAM / GPU-Auslastung abfragen."""
    return _get_vram_info()


def _get_vram_info() -> dict:
    """Ermittelt GPU/VRAM-Auslastung via nvidia-smi."""
    import subprocess, os
    is_win = os.name == "nt"
    cmd = "nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu --format=csv,noheader,nounits" if is_win else ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=5, shell=is_win)
        if out.returncode == 0:
            gpus = []
            for line in out.stdout.strip().split("\n"):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4:
                    gpus.append({
                        "index": int(parts[0]) if parts[0].isdigit() else parts[0],
                        "name": parts[1],
                        "memory_total_mb": int(float(parts[2])) if parts[2] else 0,
                        "memory_used_mb": int(float(parts[3])) if parts[3] else 0,
                        "memory_free_mb": int(float(parts[4])) if len(parts) > 4 and parts[4] else 0,
                        "utilization_pct": int(float(parts[5])) if len(parts) > 5 and parts[5] else 0,
                        "temperature_c": int(float(parts[6])) if len(parts) > 6 and parts[6] else 0,
                    })
            return {"available": True, "gpus": gpus, "count": len(gpus)}
        return {"available": False, "error": f"nvidia-smi returned code {out.returncode}: {out.stderr[:200]}"}
    except FileNotFoundError:
        return {"available": False, "error": "nvidia-smi not found (no NVIDIA GPU or drivers missing)"}
    except subprocess.TimeoutExpired:
        return {"available": False, "error": "nvidia-smi timeout"}
    except Exception as e:
        return {"available": False, "error": str(e)[:200]}
async def get_status(_user: str = Depends(require_auth)) -> dict:
    """Landing-Page Übersicht."""
    settings_data = read_json(settings.settings_json, {}) or {}
    sessions_dir = settings.sessions_dir
    session_count = 0
    if sessions_dir.exists():
        session_count = sum(1 for f in sessions_dir.iterdir() if f.suffix == ".jsonl")

    # Cost der letzten 7 Tage (schneller Sub-Query)
    from .cost import cost_summary
    cost_7d = await cost_summary(_user=_user, days=7)
    savings = cost_7d.get("savings", {})
    by_provider = cost_7d.get("by_provider", {})

    # Erweiterte System-Infos
    import platform, time, psutil
    vm = psutil.virtual_memory()
    import shutil
    du = shutil.disk_usage(str(settings.PI_AGENT_DIR))

    return {
        "pi_version": _pi_version(),
        "pi_package": settings.PI_CODING_AGENT_PKG,
        "agent_dir": str(settings.PI_AGENT_DIR),
        "default_model": settings_data.get("defaultModel"),
        "default_provider": settings_data.get("defaultProvider"),
        "enabled_models": settings_data.get("enabledModels", []),
        "default_thinking_level": settings_data.get("defaultThinkingLevel"),
        "session_count": session_count,
        "installed_extensions": [
            e.name for e in (await list_extensions(_user)) if e.installed
        ],
        # Token-Budget-Schutz-Übersicht
        "model_strategy": {
            "main_instance": settings_data.get("defaultModel", "minimax-direct/minimax-m3"),
            "sub_agents": "ollama/gemma4:12b",
            "policy": "MiniMax-M3 nur fuer UI/Orchestrierung der Hauptinstanz. Sub-Agenten (swarm-spawner) laufen lokal mit Ollama.",
        },
        "savings_7d": {
            "ollama_calls": savings.get("ollama_calls", 0),
            "minimax_calls": savings.get("minimax_calls", 0),
            "estimated_savings_usd": savings.get("estimated_savings_usd", 0.0),
        },
        "cost_by_provider_7d": by_provider,
        # Erweiterte System-Infos
        "system": {
            "os": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
            "cpu_count": psutil.cpu_count() or 1,
            "cpu_percent": psutil.cpu_percent(interval=0.2),
            "memory": {
                "total": vm.total, "available": vm.available,
                "percent": vm.percent, "used": vm.used,
            },
            "disk": {
                "total": du.total, "used": du.used, "free": du.free,
                "percent": (du.used / du.total) * 100 if du.total else 0,
                "path": str(settings.PI_AGENT_DIR),
            },
            "uptime_s": time.time() - psutil.boot_time(),
            "pi_agent_dir_size": sum(f.stat().st_size for f in settings.PI_AGENT_DIR.rglob("*") if f.is_file()) if settings.PI_AGENT_DIR.exists() else 0,
            "session_files": session_count,
            "extensions_count": len([e.name for e in (await list_extensions(_user)) if e.installed]),
            "ollama_models": _ollama_models(),
        },
    }


def _ollama_models() -> list[str]:
    """Liste der verfuegbaren Ollama-Modelle."""
    import subprocess
    try:
        out = subprocess.run(
            "ollama list" if os.name == "nt" else ["ollama", "list"],
            capture_output=True, text=True, timeout=10,
            shell=os.name == "nt",
        )
        if out.returncode == 0:
            lines = out.stdout.strip().split("\n")
            return [l.split()[0] for l in lines[1:] if l.strip()] if len(lines) > 1 else []
    except:
        pass
    return []
