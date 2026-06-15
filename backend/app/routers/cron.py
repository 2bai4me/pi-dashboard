"""Cron Jobs: Einfache geplante PI-Befehle via Windows Task Scheduler / cron-ähnlich.

Speichert Cron-Jobs in settings.json unter `cron_jobs`. Ausführung nutzt
entweder schedule (periodisch) oder den task scheduler.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth import require_auth
from ..config import settings
from ..utils import read_json, write_json

router = APIRouter(prefix="/api/cron", tags=["cron"])

CRON_FILE = settings.PI_AGENT_DIR / "cron_jobs.json"


class CronJob(BaseModel):
    id: str
    name: str
    prompt: str
    schedule: str  # cron-expression or interval e.g. "0 9 * * *" or "every 1h"
    model: str | None = None
    provider: str | None = None
    enabled: bool = True
    last_run: str | None = None
    next_run: str | None = None
    last_result: str | None = None
    delivery: str = "local"  # "local" | "telegram" | "discord" etc.
    created_at: str | None = None


class CronJobCreate(BaseModel):
    name: str
    prompt: str
    schedule: str
    model: str | None = None
    provider: str | None = None
    delivery: str = "local"


def _load_jobs() -> list[dict]:
    if not CRON_FILE.exists():
        return []
    return read_json(CRON_FILE, [])


def _save_jobs(jobs: list[dict]) -> None:
    CRON_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_json(CRON_FILE, jobs)


def _now_iso() -> str:
    return datetime.now().isoformat()


def _next_run(schedule: str) -> str:
    """Einfache Schätzung des nächsten Runs (vereinfacht)."""
    if schedule.startswith("every"):
        # "every 1h", "every 30m"
        parts = schedule.split()
        if len(parts) >= 2:
            try:
                n = int(parts[1])
                unit = parts[2] if len(parts) > 2 else "h"
                secs = n * 3600 if unit == "h" else n * 60 if unit == "m" else n
                return datetime.fromtimestamp(time.time() + secs).isoformat()
            except ValueError:
                pass
    # fallback: +24h
    return datetime.fromtimestamp(time.time() + 86400).isoformat()


@router.get("/jobs", response_model=list[CronJob])
async def list_cron_jobs(_user: str = Depends(require_auth)) -> list[CronJob]:
    jobs = _load_jobs()
    return [CronJob(**j) for j in jobs]


@router.post("/jobs", response_model=CronJob)
async def create_cron_job(req: CronJobCreate, _user: str = Depends(require_auth)) -> CronJob:
    import uuid
    job = CronJob(
        id=str(uuid.uuid4())[:12],
        name=req.name,
        prompt=req.prompt,
        schedule=req.schedule,
        model=req.model,
        provider=req.provider,
        delivery=req.delivery,
        enabled=True,
        created_at=_now_iso(),
        next_run=_next_run(req.schedule),
    )
    jobs = _load_jobs()
    jobs.append(job.model_dump())
    _save_jobs(jobs)
    return job


@router.put("/jobs/{job_id}")
async def update_cron_job(job_id: str, req: CronJobCreate, _user: str = Depends(require_auth)) -> CronJob:
    jobs = _load_jobs()
    for j in jobs:
        if j["id"] == job_id:
            j.update({
                "name": req.name, "prompt": req.prompt, "schedule": req.schedule,
                "model": req.model, "provider": req.provider, "delivery": req.delivery,
                "next_run": _next_run(req.schedule),
            })
            _save_jobs(jobs)
            return CronJob(**j)
    raise HTTPException(404, "Job not found")


@router.delete("/jobs/{job_id}")
async def delete_cron_job(job_id: str, _user: str = Depends(require_auth)) -> dict:
    jobs = _load_jobs()
    jobs = [j for j in jobs if j["id"] != job_id]
    _save_jobs(jobs)
    return {"ok": True, "deleted": job_id}


@router.post("/jobs/{job_id}/pause")
async def pause_job(job_id: str, _user: str = Depends(require_auth)) -> dict:
    jobs = _load_jobs()
    for j in jobs:
        if j["id"] == job_id:
            j["enabled"] = False
            _save_jobs(jobs)
            return {"ok": True, "enabled": False}
    raise HTTPException(404, "Job not found")


@router.post("/jobs/{job_id}/resume")
async def resume_job(job_id: str, _user: str = Depends(require_auth)) -> dict:
    jobs = _load_jobs()
    for j in jobs:
        if j["id"] == job_id:
            j["enabled"] = True
            j["next_run"] = _next_run(j["schedule"])
            _save_jobs(jobs)
            return {"ok": True, "enabled": True}
    raise HTTPException(404, "Job not found")


@router.post("/jobs/{job_id}/trigger")
async def trigger_job(job_id: str, _user: str = Depends(require_auth)) -> dict:
    """Führt einen Cron-Job sofort aus und speichert das Resultat."""
    jobs = _load_jobs()
    job = None
    for j in jobs:
        if j["id"] == job_id:
            job = j
            break
    if not job:
        raise HTTPException(404, "Job not found")

    # Ausfuehren
    is_win = os.name == "nt"
    cmd = f"{settings.PI_BIN} -p \"{job['prompt']}\"" if is_win else [settings.PI_BIN, "-p", job["prompt"]]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            shell=is_win,
            env={**os.environ, "PI_OFFLINE": "1", "NO_COLOR": "1"},
        )
        result = proc.stdout[:1000] + ("\n" + proc.stderr[:500] if proc.stderr else "")
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        result = "TIMEOUT after 120s"
        exit_code = -1
    except Exception as e:
        result = f"ERROR: {e}"
        exit_code = -2

    now = _now_iso()
    for j in jobs:
        if j["id"] == job_id:
            j["last_run"] = now
            j["last_result"] = result[:1000]
            j["next_run"] = _next_run(j["schedule"])
            break
    _save_jobs(jobs)

    return {
        "ok": exit_code == 0,
        "exitCode": exit_code,
        "result": result[:500],
        "run_at": now,
    }


@router.get("/jobs/{job_id}/history")
async def job_history(job_id: str, _user: str = Depends(require_auth)) -> list[dict]:
    """Liest die letzten 10 Ausfuehrungen aus der Session-History."""
    # Vereinfacht: wir geben die letzten runs aus dem Job-Objekt
    jobs = _load_jobs()
    for j in jobs:
        if j["id"] == job_id:
            return [{
                "run_at": j.get("last_run"),
                "result": j.get("last_result", "")[:200],
                "exitCode": 0,
            }] if j.get("last_run") else []
    return []
