"""SOP (Standard Operating Procedure) Engine — backend."""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_auth
from ..config import settings

router = APIRouter(prefix="/api/sop", tags=["sop"])

SOP_DIR = settings.PI_AGENT_DIR / "sops"


# ─── Models ─────────────────────────────────────────────────────────

class SopStep(BaseModel):
    id: str
    name: str
    description: str
    order: int
    role: str = "pi-coder"  # wer: CEO-digital, CIO, pi-coder, pi-tester, etc.
    tool: str = "auto"       # welche Tools: read, write, bash, auto, mcp
    expected_output: str = ""
    constraints: list[str] = []
    approval_required: bool = False
    timeout_minutes: int = 10
    status: str = "planned"  # planned | running | completed | failed | paused
    started_at: str | None = None
    completed_at: str | None = None
    output: str | None = None
    error: str | None = None
    evidence: list[str] = []
    # Prozess-Icons & RACI
    icon: str = "⚙️"
    raci_r: str = ""  # Responsible (macht)
    raci_a: str = ""  # Accountable (genehmigt)
    raci_c: list[str] = []  # Consulted
    raci_i: list[str] = []  # Informed
    input_docs: list[str] = []
    output_docs: list[str] = []
    tools_detail: list[str] = []
    risks: list[str] = []
    quality_criteria: list[str] = []
    # If-Then Regeln
    condition: str | None = None
    then_step: str | None = None
    else_step: str | None = None
    branch_type: str = "sequential"  # sequential | condition | parallel | join
    duration_estimate_min: int = 0


class SopProcess(BaseModel):
    id: str
    name: str
    description: str
    version: str = "1.0.0"
    status: str = "planned"  # planned | approved | running | paused | completed | failed
    steps: list[SopStep] = []
    created_by: str = "CEO-digital"
    created_at: str = ""
    updated_at: str = ""
    approved_at: str | None = None
    tags: list[str] = []
    current_step_index: int = -1
    start_count: int = 0
    avg_duration_minutes: float = 0.0
    quality_score: float = 100.0
    monitor: dict = {}  # Live-Monitoring-Daten


class SopCreate(BaseModel):
    name: str
    description: str
    tags: list[str] = []


# ─── File I/O ───────────────────────────────────────────────────────

def _sop_path(sop_id: str = "") -> Path:
    SOP_DIR.mkdir(parents=True, exist_ok=True)
    if sop_id:
        return SOP_DIR / f"{sop_id}.json"
    return SOP_DIR


def _load_all() -> list[dict]:
    if not SOP_DIR.exists():
        return []
    sops = []
    for f in sorted(SOP_DIR.iterdir()):
        if f.suffix == ".json":
            try:
                sops.append(json.loads(f.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass
    return sops


def _load(sop_id: str) -> dict:
    path = _sop_path(sop_id)
    if not path.exists():
        raise HTTPException(404, f"SOP not found: {sop_id}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(500, "Corrupted SOP file")


def _save(sop_id: str, data: dict) -> None:
    path = _sop_path(sop_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _now() -> str:
    return datetime.now().isoformat()


def _make_id() -> str:
    return uuid.uuid4().hex[:12]


# ─── CEO-digital elaborates SOP ─────────────────────────────────────

async def _ceo_elaborate(sop: SopProcess) -> SopProcess:
    """CEO-digital arbeitet den Prozess aus: Schritte mit RACI, Regeln, Icons."""
    steps = [
        SopStep(id="init", name="Projekt initiieren",
            description=f"Projekt '{sop.name}' initiieren: Ziele definieren, Team zusammenstellen, Zeitplan erstellen",
            order=1, icon="🚀", role="CEO-digital", tool="read",
            expected_output="Projektauftrag (Projekt charter)",
            constraints=["MUSS vom Auftraggeber genehmigt werden", "SOLL klare Ziele definieren"],
            approval_required=True, timeout_minutes=30,
            raci_r="CEO-digital", raci_a="Auftraggeber", raci_c=["CIO"], raci_i=["CMO", "CFO"],
            input_docs=["Anforderungsdokument"], output_docs=["Projektauftrag.md"],
            tools_detail=["read", "write"], risks=["Unklare Ziele"], quality_criteria=["Vollständigkeit", "Messbarkeit"],
            branch_type="sequential", duration_estimate_min=30),
        SopStep(id="analyze", name="Anforderungen analysieren",
            description="Detaillierte Analyse der Anforderungen und Machbarkeitsprüfung",
            order=2, icon="🔍", role="CIO", tool="read",
            expected_output="Anforderungsspezifikation",
            constraints=["MUSS alle Stakeholder einbeziehen", "SOLL technische Machbarkeit prüfen"],
            raci_r="CIO", raci_a="CEO-digital", raci_c=["pi-coder", "pi-tester"], raci_i=["CMO"],
            input_docs=["Projektauftrag.md"], output_docs=["Lastenheft.md", "Machbarkeitsstudie.md"],
            tools_detail=["read", "write", "bash"], risks=["Fehlende Informationen"], quality_criteria=["Vollständigkeit", "Konsistenz"],
            branch_type="sequential", duration_estimate_min=45),
        SopStep(id="design", name="Lösung entwerfen",
            description="Technischen Entwurf und Architektur erstellen",
            order=3, icon="🏗️", role="CIO", tool="write",
            expected_output="Architektur- und Entwurfsdokument",
            constraints=["MUSS SOA-Prinzipien folgen", "SOLL Microservices-Ansatz verwenden"],
            raci_r="CIO", raci_a="CEO-digital", raci_c=["pi-coder"], raci_i=["CMO"],
            input_docs=["Lastenheft.md"], output_docs=["Architektur.md", "Schnittstellendefinition.md"],
            tools_detail=["write", "read"], risks=["Architekturkonflikte"], quality_criteria=["SOA-Konformität", "Skalierbarkeit"],
            condition="WENN Komplexität > mittel DANN Parallel-Entwicklung", then_step="implement-a", else_step="implement-b",
            branch_type="condition", duration_estimate_min=60),
        SopStep(id="implement-a", name="Implementieren (Hauptfunktionen)",
            description="Hauptfunktionen implementieren (paralleler Zweig)",
            order=4, icon="💻", role="pi-coder", tool="auto",
            expected_output="Implementierter Code",
            constraints=["MUSS Coding-Standards einhalten", "MUSS von Ollama Gemma4 12b umsetzbar sein"],
            raci_r="pi-coder", raci_a="CIO", raci_c=["pi-tester"], raci_i=["CEO-digital"],
            input_docs=["Architektur.md"], output_docs=["Quellcode"],
            tools_detail=["write", "edit", "bash"], risks=["Technische Schulden"], quality_criteria=["Code-Qualität", "Testabdeckung >80%"],
            branch_type="parallel", duration_estimate_min=120),
        SopStep(id="implement-b", name="Implementieren (Nebenfunktionen)",
            description="Nebenfunktionen und Tests implementieren (paralleler Zweig)",
            order=4, icon="🧪", role="pi-tester", tool="bash",
            expected_output="Testcode und -ergebnisse",
            constraints=["MUSS parallel zu Hauptfunktionen laufen", "SOLL Testautomatisierung verwenden"],
            raci_r="pi-tester", raci_a="CIO", raci_c=["pi-coder"], raci_i=["CEO-digital"],
            input_docs=["Architektur.md"], output_docs=["Testfälle", "Testergebnisse"],
            tools_detail=["bash", "write"], risks=["Testlücken"], quality_criteria=["Testabdeckung", "Fehlerrate"],
            branch_type="parallel", duration_estimate_min=90),
        SopStep(id="review", name="Review & Qualitätssicherung",
            description="Code-Review, Qualitätsprüfung und SOA-Compliance-Check",
            order=5, icon="👁️", role="pi-reviewer", tool="read",
            expected_output="Review-Bericht mit Freigabe oder Änderungsbedarf",
            constraints=["MUSS von pi-reviewer mit minimax-m3 durchgeführt werden", "MUSS auf SOA-Konformität prüfen"],
            approval_required=True, timeout_minutes=30,
            raci_r="pi-reviewer", raci_a="CIO", raci_c=["CEO-digital"], raci_i=["CMO"],
            input_docs=["Quellcode", "Testfälle"], output_docs=["Review-Bericht.md"],
            tools_detail=["read", "grep"], risks=["Übersehene Fehler"], quality_criteria=["SOA-Compliance", "Code-Qualität"],
            branch_type="sequential", duration_estimate_min=30),
        SopStep(id="deliver", name="Ausliefern & Dokumentieren",
            description="Finale Auslieferung, Dokumentation und Projektabschluss",
            order=6, icon="📦", role="CEO-digital", tool="write",
            expected_output="Lieferpaket mit vollständiger Dokumentation",
            constraints=["MUSS alle Output-Dokumente enthalten", "MUSS vom Auftraggeber abgenommen werden"],
            approval_required=True, timeout_minutes=20,
            raci_r="CEO-digital", raci_a="Auftraggeber", raci_c=["CIO", "CMO"], raci_i=["CFO"],
            input_docs=["Review-Bericht.md", "Quellcode"], output_docs=["Lieferpaket", "Projektdokumentation.pdf"],
            tools_detail=["write", "read"], risks=["Unvollständige Dokumentation"], quality_criteria=["Vollständigkeit", "Qualität"],
            branch_type="join", duration_estimate_min=20),
    ]
    sop.steps = steps
    sop.created_at = _now()
    sop.updated_at = _now()
    return sop


# ─── API Endpoints ──────────────────────────────────────────────────

@router.post("/create", response_model=SopProcess)
async def create_sop(req: SopCreate, _user: str = Depends(require_auth)) -> SopProcess:
    """CEO-digital erstellt und arbeitet einen neuen Prozess aus."""
    sop = SopProcess(
        id=_make_id(),
        name=req.name,
        description=req.description,
        tags=req.tags,
        created_at=_now(),
        updated_at=_now(),
        status="planned",
        monitor={
            "started": None, "progress_pct": 0, "current_step": None,
            "durations": [], "bottlenecks": [], "improvements": [],
        },
    )
    sop = await _ceo_elaborate(sop)
    _save(sop.id, sop.model_dump())
    return sop


@router.get("/list", response_model=list[SopProcess])
async def list_sops(_user: str = Depends(require_auth)) -> list[SopProcess]:
    return [SopProcess(**s) for s in _load_all()]


@router.get("/{sop_id}", response_model=SopProcess)
async def get_sop(sop_id: str, _user: str = Depends(require_auth)) -> SopProcess:
    return SopProcess(**_load(sop_id))


@router.post("/{sop_id}/approve")
async def approve_sop(sop_id: str, _user: str = Depends(require_auth)) -> dict:
    data = _load(sop_id)
    data["status"] = "approved"
    data["approved_at"] = _now()
    data["updated_at"] = _now()
    _save(sop_id, data)
    return {"ok": True, "status": "approved", "sop_id": sop_id}


@router.post("/{sop_id}/pause")
async def pause_sop(sop_id: str, _user: str = Depends(require_auth)) -> dict:
    data = _load(sop_id)
    data["status"] = "paused"
    data["updated_at"] = _now()
    if data.get("monitor"):
        data["monitor"]["paused_at"] = _now()
    _save(sop_id, data)
    return {"ok": True, "status": "paused", "sop_id": sop_id}


@router.post("/{sop_id}/start")
async def start_sop(sop_id: str, _user: str = Depends(require_auth)) -> dict:
    data = _load(sop_id)
    if data.get("status") not in ("approved", "planned", "paused"):
        raise HTTPException(400, f"Cannot start SOP in status: {data['status']}")
    data["status"] = "running"
    data["current_step_index"] = 0
    data["start_count"] = data.get("start_count", 0) + 1

    monitor = data.get("monitor", {})
    monitor["started_at"] = _now()
    monitor["step_times"] = []
    monitor["progress_pct"] = 0
    monitor["current_step"] = data["steps"][0]["name"] if data.get("steps") else None
    data["monitor"] = monitor

    if data.get("steps"):
        data["steps"][0]["status"] = "running"
        data["steps"][0]["started_at"] = _now()
    data["updated_at"] = _now()
    _save(sop_id, data)
    return {"ok": True, "status": "running", "sop_id": sop_id}


@router.post("/{sop_id}/step/{step_id}/complete")
async def complete_step(sop_id: str, step_id: str, req: dict, _user: str = Depends(require_auth)) -> dict:
    data = _load(sop_id)
    steps = data.get("steps", [])
    step = next((s for s in steps if s["id"] == step_id), None)
    if not step:
        raise HTTPException(404, f"Step not found: {step_id}")

    step["status"] = "completed"
    step["completed_at"] = _now()
    step["output"] = str(req.get("output", ""))
    step["evidence"] = req.get("evidence", [])

    # Nächster Schritt
    idx = next((i for i, s in enumerate(steps) if s["id"] == step_id), -1)
    next_idx = idx + 1
    if next_idx < len(steps):
        steps[next_idx]["status"] = "running"
        steps[next_idx]["started_at"] = _now()
        data["current_step_index"] = next_idx
    else:
        data["status"] = "completed"
        data["completed_at"] = _now()
        data["current_step_index"] = -1

    data["updated_at"] = _now()

    # Monitor-Updates
    monitor = data.get("monitor", {})
    monitor["current_step"] = steps[next_idx]["name"] if next_idx < len(steps) else None
    completed = sum(1 for s in steps if s["status"] == "completed")
    monitor["progress_pct"] = round((completed / len(steps)) * 100) if steps else 0
    monitor["step_times"] = monitor.get("step_times", [])
    if step.get("started_at") and step.get("completed_at"):
        try:
            start = datetime.fromisoformat(step["started_at"])
            end = datetime.fromisoformat(step["completed_at"])
            duration = (end - start).total_seconds() / 60
            monitor["step_times"].append({"step": step["name"], "duration_min": round(duration, 1), "tools": step.get("tool", "auto")})
        except:
            pass
    monitor["improvements"] = _generate_improvements(steps, monitor)
    data["monitor"] = monitor

    _save(sop_id, data)
    return {"ok": True, "step_id": step_id, "next_step": steps[next_idx]["name"] if next_idx < len(steps) else None, "progress": monitor["progress_pct"]}


@router.post("/{sop_id}/step/{step_id}/fail")
async def fail_step(sop_id: str, step_id: str, req: dict, _user: str = Depends(require_auth)) -> dict:
    data = _load(sop_id)
    step = next((s for s in data.get("steps", []) if s["id"] == step_id), None)
    if not step:
        raise HTTPException(404, f"Step not found: {step_id}")
    step["status"] = "failed"
    step["error"] = str(req.get("error", "Unknown error"))
    data["status"] = "failed"
    data["updated_at"] = _now()
    _save(sop_id, data)
    return {"ok": False, "error": step["error"]}


@router.delete("/{sop_id}")
async def delete_sop(sop_id: str, _user: str = Depends(require_auth)) -> dict:
    path = _sop_path(sop_id)
    if path.exists():
        path.unlink()
    return {"ok": True, "deleted": sop_id}


@router.get("/{sop_id}/monitor")
async def get_monitor(sop_id: str, _user: str = Depends(require_auth)) -> dict:
    data = _load(sop_id)
    monitor = data.get("monitor", {})
    steps = data.get("steps", [])
    return {
        "sop_id": sop_id,
        "sop_name": data.get("name", ""),
        "status": data.get("status", ""),
        "progress_pct": monitor.get("progress_pct", 0),
        "current_step": monitor.get("current_step"),
        "step_times": monitor.get("step_times", []),
        "bottlenecks": monitor.get("bottlenecks", []),
        "improvements": monitor.get("improvements", []),
        "started_at": monitor.get("started_at"),
        "steps": [
            {"id": s["id"], "name": s["name"], "status": s["status"], "role": s.get("role", "?"), "tool": s.get("tool", "?"), "order": s.get("order", 0)}
            for s in steps
        ],
        "total_steps": len(steps),
        "completed_steps": sum(1 for s in steps if s["status"] == "completed"),
    }


# ─── Monitor: Improvement-Generierung ─────────────────────────────

def _generate_improvements(steps: list[dict], monitor: dict) -> list[str]:
    imps = []
    step_times = monitor.get("step_times", [])
    if step_times:
        avg = sum(s.get("duration_min", 0) for s in step_times) / len(step_times)
        for s in step_times:
            if s.get("duration_min", 0) > avg * 1.5:
                imps.append(f"Step '{s['name']}' took {s['duration_min']}min (avg {avg:.1f}min) — consider parallelization or better tooling ({s.get('tools', '?')})")
    failed = [s for s in steps if s.get("status") == "failed"]
    if failed:
        imps.append(f"Step '{failed[0]['name']}' failed — review constraints and role assignment")
    repeated = [s for s in steps if s.get("status") in ("running", "planned") and s.get("started_at") and (datetime.now() - datetime.fromisoformat(s["started_at"])).total_seconds() > s.get("timeout_minutes", 10) * 60]
    if repeated:
        imps.append(f"Step '{repeated[0]['name']}' exceeding timeout — consider splitting into sub-steps")
    if len(steps) > 8:
        imps.append(f"Process has {len(steps)} steps (>8) — consider modularization into sub-processes")
    return imps[:5]


@router.get("/stats/summary")
async def sop_stats(_user: str = Depends(require_auth)) -> dict:
    sops = _load_all()
    by_status = {}
    total_duration = 0.0
    completed_count = 0
    for s in sops:
        st = s.get("status", "planned")
        by_status[st] = by_status.get(st, 0) + 1
        m = s.get("monitor", {})
        times = m.get("step_times", [])
        if times:
            total_duration += sum(t.get("duration_min", 0) for t in times)
            completed_count += 1
    return {
        "total": len(sops),
        "by_status": by_status,
        "avg_duration_min": round(total_duration / completed_count, 1) if completed_count else 0,
        "total_improvements": sum(len(s.get("monitor", {}).get("improvements", [])) for s in sops),
    }
