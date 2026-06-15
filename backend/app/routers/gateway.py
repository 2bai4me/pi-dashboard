"""Gateway: Service-Status (Ollama, PI, Dashboard) + Restart."""
from __future__ import annotations

import os
import subprocess
import time

from fastapi import APIRouter, Depends

from ..auth import require_auth
from ..config import settings

router = APIRouter(prefix="/api/gateway", tags=["gateway"])


def _check_ollama() -> dict:
    """Prueft ob Ollama laeuft und listet Modelle."""
    is_win = os.name == "nt"
    start = time.time()
    try:
        cmd = "ollama list" if is_win else ["ollama", "list"]
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=5,
            shell=is_win,
        )
        elapsed = round((time.time() - start) * 1000)
        if out.returncode == 0:
            lines = out.stdout.strip().split("\n")
            models = [l.split()[0] for l in lines[1:] if l.strip()] if len(lines) > 1 else []
            return {
                "running": True,
                "models": models,
                "model_count": len(models),
                "latency_ms": elapsed,
            }
        return {"running": False, "models": [], "error": out.stderr[:200], "latency_ms": elapsed}
    except FileNotFoundError:
        return {"running": False, "models": [], "error": "ollama binary not found"}
    except subprocess.TimeoutExpired:
        return {"running": False, "models": [], "error": "timeout"}
    except Exception as e:
        return {"running": False, "models": [], "error": str(e)[:200]}


def _check_pi() -> dict:
    """Prueft ob pi binary verfuegbar ist."""
    start = time.time()
    try:
        is_win = os.name == "nt"
        cmd = f"{settings.PI_BIN} --version" if is_win else [settings.PI_BIN, "--version"]
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=5, shell=is_win,
        )
        elapsed = round((time.time() - start) * 1000)
        if out.returncode == 0:
            return {"running": True, "version": out.stdout.strip(), "latency_ms": elapsed}
        return {"running": False, "error": out.stderr[:200], "latency_ms": elapsed}
    except FileNotFoundError:
        return {"running": False, "error": "pi binary not found"}
    except subprocess.TimeoutExpired:
        return {"running": False, "error": "timeout"}


@router.get("/status")
async def gateway_status(_user: str = Depends(require_auth)) -> dict:
    """Status aller Gateway-Dienste."""
    ollama = _check_ollama()
    pi = _check_pi()
    all_ok = ollama.get("running", False) and pi.get("running", False)
    return {
        "dashboard": {
            "running": True,
            "version": "0.1.0",
            "port": settings.PORT,
            "agent_dir": str(settings.PI_AGENT_DIR),
        },
        "ollama": ollama,
        "pi": pi,
        "all_running": all_ok,
        "timestamp": time.time(),
    }


@router.post("/restart/ollama")
async def restart_ollama(_user: str = Depends(require_auth)) -> dict:
    """Startet Ollama neu (Windows: taskkill + start)."""
    try:
        is_win = os.name == "nt"
        if is_win:
            subprocess.run("taskkill /F /IM ollama.exe >nul 2>&1", shell=True, timeout=5)
            subprocess.run("start /B ollama serve", shell=True, timeout=5)
        else:
            subprocess.run(["killall", "ollama"], capture_output=True, timeout=5)
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "action": "restarting ollama"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
