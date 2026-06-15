"""Kanban: Erweitert um Projekte, Brainstorming, Anforderungen, Tasks."""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..auth import require_auth
from ..config import settings
from ..nalabs_rules import check_requirement_quality as nalabs_check, check_requirements_batch as nalabs_batch
from ..utils import read_json, write_json

router = APIRouter(prefix="/api/kanban", tags=["kanban"])

# ─── Audit-Pflicht (Bug 3 Fix): Konstanten fuer Migration + Status-Setter ───
HAENGER_AGE_SECONDS = 600  # 10 Min (Schwelle fuer "haengt")
HAENGER_PRIO_ESCALATION = 10  # +10 Prio pro Eskalation
HAENGER_WORKER_SWITCH_AGE = 900  # 15 Min (Worker-Wechsel)
HAENGER_EMERGENCY_AGE = 1500  # 25 Min (Prio 100)

KANBAN_DIR = settings.PI_AGENT_DIR / "kanban"
REQUIREMENTS_DIR = settings.PI_AGENT_DIR / "requirements"

# Konversationaler Fragenkatalog: Immer EINE Frage pro AI-Antwort
# Wird im brainstorm()-Endpoint chronologisch durchgegangen
CONVERSATION_QUESTIONS = [
    "Wer ist die Zielgruppe beziehungsweise der Nutzer dieser Loesung?",
    "Welches konkrete Problem soll geloest werden?",
    "Welche zeitlichen oder budgetaeren Vorgaben gibt es?",
    "Wie messen Sie den Erfolg?",
    "Welche Abhaengigkeiten zu anderen Systemen gibt es?",
]

# CIO-Pruefungen: Wird nach JEDER User-Antwort geprueft, ob entsprechendes Thema
# bereits in den User-Inputs erwaehnt wurde. Falls nicht, wird die naechste
# fehlende Pruefung als Frage + Empfehlung ausgegeben.
# keywords: Heuristik, ob das Thema im User-Input schon vorkommt
CIO_CHECKS = [
    {
        "topic": "Architektur",
        "question": "Welche Architektur-Form bevorzugen Sie (Monolith, Microservices, Modular Monolith, Serverless)?",
        "recommendation": "Empfehlung des CIO: Starten Sie mit einem Modular Monolith, falls Team < 5 Entwickler. Skaliert besser als Microservices, ist aber bereits entkoppelt genug fuer spätere Aufteilung. Microservices lohnen sich erst bei dedizierten Teams pro Service.",
        "keywords": ["architektur", "architecture", "monolith", "microservice", "soa", "service-orient", "modular", "serverless", "lambda"],
    },
    {
        "topic": "Tech-Stack",
        "question": "Welcher Tech-Stack soll verwendet werden (Programmiersprache, Frontend-Framework, Backend)?",
        "recommendation": "Empfehlung des CIO: Python + FastAPI (Backend) + React + TypeScript (Frontend) ist eine moderne, gut dokumentierte Wahl mit grosser Community. Falls Echtzeit noetig: Python mit WebSockets. Falls Low-Code noetig: Node.js mit Express. Bleiben Sie bei dem Stack, den Ihr Team beherrscht.",
        "keywords": ["python", "javascript", "typescript", "react", "vue", "angular", "node", "java", "go", "golang", "rust", "php", "ruby", "framework", "fastapi", "django", "flask", "express", "spring", "next.js", "nuxt"],
    },
    {
        "topic": "Datenbank",
        "question": "Welche Datenbank-Anforderungen haben Sie (relational, NoSQL, Graph, In-Memory)?",
        "recommendation": "Empfehlung des CIO: Starten Sie mit PostgreSQL — robust, ACID-konform, gut dokumentiert. Wenn klare NoSQL-Anforderungen (z.B. flexibel Schema, grosse Dokumente): MongoDB. Fuer Caching: Redis. Vermeiden Sie Polyglot-Persistence zu Beginn, das vervielfacht die Komplexitaet.",
        "keywords": ["datenbank", "database", "sql", "postgres", "postgresql", "mysql", "mariadb", "mongo", "mongodb", "redis", "sqlite", "neo4j", "dynamo", "cassandra", "elasticsearch"],
    },
    {
        "topic": "Deployment & Hosting",
        "question": "Wo und wie soll die Anwendung deployt werden (Cloud-Provider, On-Premise, Docker, Kubernetes)?",
        "recommendation": "Empfehlung des CIO: Docker-Container + Reverse Proxy (Traefik oder nginx) ist der Standard. Cloud-Wahl haengt vom Datenschutz ab: EU-Daten -> Hetzner, IONOS oder AWS Frankfurt. On-Premise nur bei strikter Compliance. Vermeiden Sie Kubernetes zu Beginn — Docker-Compose reicht bis ~10 Services.",
        "keywords": ["deployment", "deploy", "hosting", "cloud", "aws", "azure", "gcp", "google cloud", "hetzner", "ionos", "on-premise", "self-hosted", "docker", "kubernetes", "k8s", "container", "vserver"],
    },
    {
        "topic": "Authentifizierung",
        "question": "Wie sollen sich Nutzer authentifizieren (E-Mail/Passwort, OAuth, SSO, Multi-Faktor)?",
        "recommendation": "Empfehlung des CIO: Verwenden Sie Authentik oder Keycloak (Self-Hosted) bzw. Auth0/Clerk (Cloud) statt eigenem Auth-Code. Multi-Faktor (TOTP) sollte Standard sein, mindestens fuer Admin-Accounts. OAuth2 (Google/GitHub) als Secondary-Login erhoeht UX. Niemals Passwoerter im Klartext speichern — nutzen Sie bcrypt/argon2.",
        "keywords": ["authentifizierung", "authentication", "auth", "login", "oauth", "sso", "saml", "openid", "mfa", "2fa", "totp", "jwt", "session", "authentik", "keycloak", "auth0", "clerk"],
    },
    {
        "topic": "Sicherheit",
        "question": "Welche Sicherheits-Anforderungen gibt es (DSGVO, Verschlüsselung, Penetrationstest, Audit-Log)?",
        "recommendation": "Empfehlung des CIO: Mindestens: HTTPS ueberall (Let's Encrypt), verschluesselte Passwoerter (argon2id), Audit-Log fuer schreibende Aktionen, Rate-Limiting (z.B. nginx limit_req), regelmaessige Updates der Dependencies (Dependabot/Renovate). DSGVO: Datenhaltung in EU, Auftragsverarbeitungsvertrag mit Cloud-Provider, Datenschutzerklaerung. Penetrationstest erst vor Go-Live, nicht waehrend Entwicklung.",
        "keywords": ["sicherheit", "security", "dsgvo", "gdpr", "verschl", "encrypt", "tls", "ssl", "https", "audit", "penetration", "pentest", "cve", "owasp", "rate-limit"],
    },
    {
        "topic": "Skalierung & Last",
        "question": "Wie viele Nutzer und gleichzeitige Anfragen erwarten Sie?",
        "recommendation": "Empfehlung des CIO: < 1000 User: Single-Server reicht. 1000-10000: 2-3 Server mit Load-Balancer. > 10000: Microservices + Kubernetes + Caching-Layer (Redis). Wichtiger als Skalierung ist Performance-Profiling (z.B. mit py-spy oder clinic.js) — 80% der Bottlenecks sind in 20% des Codes. Vermeiden Sie Premature Optimization.",
        "keywords": ["skalier", "scale", "scaling", "last", "concurrent", "gleichzeitig", "user", "nutzer", "million", "tausend", "anfragen", "qps", "rps", "durchsatz", "performance", "load"],
    },
    {
        "topic": "Testing & Qualitaet",
        "question": "Welche Test-Anforderungen gibt es (Unit, Integration, E2E, Test-Coverage)?",
        "recommendation": "Empfehlung des CIO: Mindestens 70% Test-Coverage, davon 90% bei Geschaeftslogik. Pyramide: viele Unit-Tests (schnell, isoliert), weniger Integration-Tests, wenige E2E-Tests (langsam, teuer). CI/CD mit GitHub Actions oder GitLab CI, automatisierte Tests bei jedem Commit. Test-Daten nicht produktiv — eigene Test-DB oder Mocks.",
        "keywords": ["test", "testing", "pytest", "unittest", "jest", "ci/cd", "pipeline", "coverage", "e2e", "end-to-end", "integration", "unit-test", "qualitaet", "qa"],
    },
    {
        "topic": "Backup & Recovery",
        "question": "Welche Backup- und Recovery-Strategie ist vorgesehen?",
        "recommendation": "Empfehlung des CIO: 3-2-1-Regel: 3 Kopien, 2 verschiedene Medien, 1 off-site. Automatisiert taeglich (Cron oder cloud-native Snapshots), vor jedem Major-Release manuelles Backup. Recovery regelmaessig testen (Disaster-Recovery-Drill mindestens quartalsweise) — ein nicht getestetes Backup ist kein Backup. RPO < 24h, RTO < 4h als realistische Ziele.",
        "keywords": ["backup", "recovery", "snapshot", "disaster", "restore", "rpo", "rto", "dr", "archiv", "wiederherstell"],
    },
]


# ─── Models ─────────────────────────────────────────────────────────

class Project(BaseModel):
    id: str
    name: str
    description: str = ""
    status: str = "active"  # active | archived | completed
    created_at: str = ""
    updated_at: str = ""
    requirements_file: str | None = None
    brainstorm_log: list[dict] = []


class BrainstormTurn(BaseModel):
    role: str  # user | assistant
    text: str
    phase: str = "input"  # input | clarifying | structuring | complete


class RequirementDocument(BaseModel):
    id: str
    project_id: str
    title: str
    content: str
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


class Task(BaseModel):
    id: str
    project_id: str
    title: str
    description: str = ""
    status: str = "triage"  # triage | todo | in_progress | review | block | done
    priority: int = 50  # 0..100 (default 50 = medium)
    assigned_role: str = "pi-coder"
    success_criteria: list[str] = []
    parent_id: str | None = None
    child_ids: list[str] = []
    references: list[str] = []  # Referenzen auf andere Tasks
    requirement_ref: str | None = None  # Referenz auf Anforderung
    tags: list[str] = []
    created_at: str = ""
    updated_at: str = ""
    order: int = 0
    iteration_count: int = 0  # Wie oft wurde dieser Task iteriert
    # Bug 3 Fix (Task d63824618a8c): Audit-Pflicht — optionales Feld fuer Frontend-Badge
    # Wird gesetzt, wenn Task keine History hatte (Legacy-Migration) und rekonstruiert wurde.
    # Pydantic v2 unterstuetzt keine Felder mit fuehrendem Underscore, daher `audit_warning`.
    audit_warning: str | None = None
    history: list[dict] = []  # History-Liste, im Pydantic-Modell optional mit Default
    # UI-Redesign (Task d3dabcba252c): Phase-Tracking — wann ist der Task in den aktuellen Status gewechselt?
    # Wird bei jedem Status-Wechsel via _set_task_status() aktualisiert. Bestehende Tasks
    # bekommen das Feld per list_tasks-Migration auf created_at gesetzt.
    phase_started_at: str | None = None


class KpiMetric(BaseModel):
    id: str
    project_id: str
    name: str
    value: float
    target: float
    unit: str = "%"
    category: str = "efficiency"  # efficiency | quality | speed | cost
    timestamp: str = ""


# ─── OpenBrain-Validierung & QS ──────────────────────────────────────────────

# Suche in OpenBrain nach Vorgaben (MCP-JSON-RPC)
async def _openbrain_search(brain_url: str, brain_key: str, query: str, limit: int = 5, threshold: float = 0.15) -> list[dict]:
    """Sucht in einem OpenBrain-Container via MCP/JSON-RPC und gibt Treffer zurueck."""
    import httpx
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "openbrain_search",
            "arguments": {"query": query, "limit": limit, "threshold": threshold},
        },
    }
    headers = {"Content-Type": "application/json", "x-brain-key": brain_key}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(brain_url, json=payload, headers=headers)
        if r.status_code != 200:
            return []
        data = r.json()
        content = data.get("result", {}).get("content", [])
        if not content:
            return []
        text = content[0].get("text", "")
        # Parse die formatierte Suche-Antwort: "[1] [type] [topic] content... (sim:0.4, tags:..., ts:...)"
        results = []
        for line in text.split("\n"):
            line = line.strip()
            if not line or not line.startswith("["):
                continue
            # Extrahiere type, topic, content, sim, tags, ts
            m = re.match(r"\[\d+\]\s+\[([^\]]+)\]\s+(?:\[([^\]]+)\]\s+)?(.+?)\s*\(sim:([\d.]+),\s*tags:([^)]+),\s*([^)]+)\)", line)
            if m:
                results.append({
                    "thought_type": m.group(1),
                    "topic": m.group(2) or "",
                    "content": m.group(3).strip(),
                    "similarity": float(m.group(4)),
                    "tags": [t.strip() for t in m.group(5).split(",") if t.strip()],
                    "timestamp": m.group(6).strip(),
                })
        return results
    except Exception:
        return []


@router.post("/validation/{project_id}/start")
async def start_validation(project_id: str, _user: str = Depends(require_auth)) -> dict:
    """Startet die OpenBrain-Validierung: prueft Brainstorming gegen bB + DEV."""
    _ensure_dir()
    projects = _load_json(KANBAN_DIR / "projects.json")
    proj = next((p for p in projects if p["id"] == project_id), None)
    if not proj:
        raise HTTPException(404, "Project not found")
    brain_log = proj.get("brainstorm_log", [])
    user_inputs = [t["text"] for t in brain_log if t["role"] == "user"]
    if not user_inputs:
        raise HTTPException(400, "Kein Brainstorming vorhanden")

    # OpenBrain-Konfiguration
    bb_url = "http://127.0.0.1:9302/"
    bb_key = "ob-bb-key-2026"
    dev_url = "http://127.0.0.1:9303/"
    dev_key = "ob-dev-key-2026"

    # Sammle zu pruefende Themen aus dem Brainstorming
    vision = user_inputs[0] if user_inputs else ""
    all_text = (proj.get("description", "") + " " + " ".join(user_inputs)).lower()

    # Queries basierend auf Brainstorming-Inhalten
    queries = []
    # Generische Policy-Queries
    queries.extend([
        ("bB", bb_url, bb_key, "Policy Standard Compliance Vorgabe"),
        ("bB", bb_url, bb_key, "Lizenz AGPL Open-Source"),
        ("bB", bb_url, bb_key, "DSGVO Datenschutz Compliance"),
        ("bB", bb_url, bb_key, "Sicherheit Security Vorgabe"),
    ])
    # Tech-Stack-spezifische Queries
    if any(kw in all_text for kw in ["python", "fastapi"]):
        queries.append(("DEV", dev_url, dev_key, "Python FastAPI Best Practice"))
    if any(kw in all_text for kw in ["react", "vue", "frontend"]):
        queries.append(("DEV", dev_url, dev_key, "React Frontend Architektur"))
    if any(kw in all_text for kw in ["docker", "kubernetes", "deployment"]):
        queries.append(("DEV", dev_url, dev_key, "Docker Deployment Container"))
    if any(kw in all_text for kw in ["postgres", "mysql", "datenbank"]):
        queries.append(("DEV", dev_url, dev_key, "PostgreSQL Datenbank"))
    if any(kw in all_text for kw in ["oauth", "authentifizierung", "auth"]):
        queries.append(("DEV", dev_url, dev_key, "OAuth Authentifizierung Security"))
    # Generische DEV-Queries
    queries.extend([
        ("DEV", dev_url, dev_key, "Architektur Standard"),
        ("DEV", dev_url, dev_key, "Test CI Pipeline"),
        ("DEV", dev_url, dev_key, "Coding Standard Style"),
    ])

    # Sammle alle Treffer
    found_vorgaben = []
    for brain_name, url, key, query in queries:
        results = await _openbrain_search(url, key, query, limit=3, threshold=0.15)
        for r in results:
            r["brain"] = brain_name
            r["query"] = query
            found_vorgaben.append(r)

    # Deduplizieren nach Content-Anfang
    seen = set()
    unique_vorgaben = []
    for v in found_vorgaben:
        key = v["content"][:60]
        if key in seen:
            continue
        seen.add(key)
        unique_vorgaben.append(v)

    # Generiere Klärungsfragen: Vergleich Brainstorming vs. Vorgaben
    clarifications = []
    # Wenn Lizenz/AGPL gefunden: Frage klären
    has_agpl = any("agpl" in v["content"].lower() or "lizenz" in v["content"].lower() for v in unique_vorgaben)
    if has_agpl and "agpl" not in all_text and "lizenz" not in all_text:
        clarifications.append({
            "id": "license",
            "category": "Lizenz",
            "question": "Welche Lizenz soll fuer das Projekt verwendet werden?",
            "context": "In den OpenBrain-Vorgaben (bB) sind Lizenz-Empfehlungen abgelegt. Fuer interne/proprietaere Nutzung kommen MIT, Apache 2.0 oder AGPL-3.0 in Frage. Bitte entscheiden.",
            "openbrain_refs": [v for v in unique_vorgaben if "agpl" in v["content"].lower() or "lizenz" in v["content"].lower()][:2],
        })
    # DSGVO/Compliance
    has_dsgvo = any("dsgvo" in v["content"].lower() or "datenschutz" in v["content"].lower() for v in unique_vorgaben)
    if has_dsgvo and "dsgvo" not in all_text:
        clarifications.append({
            "id": "dsgvo",
            "category": "Compliance",
            "question": "Werden personenbezogene Daten verarbeitet? Wenn ja, ist DSGVO-Konformitaet erforderlich?",
            "context": "In den OpenBrain-Vorgaben (bB) ist DSGVO als Standard fuer personenbezogene Daten abgelegt. Bitte klaeren, ob dieses Projekt DSGVO-relevant ist.",
            "openbrain_refs": [v for v in unique_vorgaben if "dsgvo" in v["content"].lower() or "datenschutz" in v["content"].lower()][:2],
        })
    # Security-Vorgabe
    has_security = any("security" in v["content"].lower() or "sicherheit" in v["content"].lower() for v in unique_vorgaben)
    if has_security and "security" not in all_text and "sicherheit" not in all_text:
        clarifications.append({
            "id": "security",
            "category": "Security",
            "question": "Welche Security-Vorgaben (z.B. OAuth, MFA, Verschluesselung) sollen umgesetzt werden?",
            "context": "In den OpenBrain-Vorgaben (DEV) sind Security-Standards abgelegt. Bitte bestaetigen, dass die genannten Security-Massnahmen ausreichend sind oder ergaenzen.",
            "openbrain_refs": [v for v in unique_vorgaben if "security" in v["content"].lower() or "sicherheit" in v["content"].lower()][:2],
        })
    # Architektur-Vorgabe
    has_arch = any("architektur" in v["content"].lower() for v in unique_vorgaben)
    if has_arch and "architektur" not in all_text and "microservice" not in all_text and "monolith" not in all_text:
        clarifications.append({
            "id": "architektur",
            "category": "Architektur",
            "question": "Welche Architektur-Form (Monolith, Microservices, Modular Monolith) ist geplant?",
            "context": "In den OpenBrain-Vorgaben (DEV) sind Architektur-Empfehlungen abgelegt. Bitte bestaetigen, dass die gewaehlte Architektur konform ist.",
            "openbrain_refs": [v for v in unique_vorgaben if "architektur" in v["content"].lower()][:2],
        })
    # Test/CI-Vorgabe
    has_test = any("test" in v["content"].lower() or "ci" in v["content"].lower() for v in unique_vorgaben)
    if has_test and "test" not in all_text and "ci/cd" not in all_text and "pipeline" not in all_text:
        clarifications.append({
            "id": "test",
            "category": "Testing",
            "question": "Welche Test-Strategie und CI/CD-Pipeline ist geplant?",
            "context": "In den OpenBrain-Vorgaben (DEV) sind Test-Standards abgelegt. Bitte bestaetigen, dass eine CI/CD-Pipeline mit automatisierten Tests vorgesehen ist.",
            "openbrain_refs": [v for v in unique_vorgaben if "test" in v["content"].lower() or "ci" in v["content"].lower()][:2],
        })

    # Speichern
    validation_record = {
        "project_id": project_id,
        "started_at": _now(),
        "status": "in_progress" if clarifications else "completed",
        "found_vorgaben": unique_vorgaben,
        "openbrain_queries": [q[3] for q in queries],
        "clarifications": clarifications,
        "answers": {c["id"]: None for c in clarifications},
    }
    # In validations.json speichern
    validations = _load_json(KANBAN_DIR / "validations.json", default={})
    validations[project_id] = validation_record
    _save_json(KANBAN_DIR / "validations.json", validations)

    return {
        "ok": True,
        "status": validation_record["status"],
        "vorgaben_count": len(unique_vorgaben),
        "clarifications": clarifications,
        "openbrain_queries": [q[3] for q in queries],
    }


@router.get("/validation/{project_id}")
async def get_validation(project_id: str, _user: str = Depends(require_auth)) -> dict:
    """Holt den aktuellen Validierungs-Status."""
    validations = _load_json(KANBAN_DIR / "validations.json", default={})
    rec = validations.get(project_id)
    if not rec:
        raise HTTPException(404, "Keine Validierung gefunden — bitte zuerst starten")
    return rec


@router.post("/validation/{project_id}/answer")
async def answer_clarification(project_id: str, req: dict, _user: str = Depends(require_auth)) -> dict:
    """User beantwortet eine Klaerungsfrage."""
    validations = _load_json(KANBAN_DIR / "validations.json", default={})
    rec = validations.get(project_id)
    if not rec:
        raise HTTPException(404, "Keine Validierung gefunden")
    clarification_id = req.get("clarification_id", "")
    answer = req.get("answer", "")
    if clarification_id not in rec["answers"]:
        raise HTTPException(404, f"Unbekannte Klaerungsfrage: {clarification_id}")
    rec["answers"][clarification_id] = {
        "text": answer,
        "answered_at": _now(),
    }
    # Status aktualisieren: completed wenn alle beantwortet
    all_answered = all(v is not None for v in rec["answers"].values())
    if all_answered:
        rec["status"] = "completed"
        rec["completed_at"] = _now()
    validations[project_id] = rec
    _save_json(KANBAN_DIR / "validations.json", validations)
    return {"ok": True, "status": rec["status"], "all_answered": all_answered}


@router.post("/requirements/review/{project_id}")
async def review_requirements_doc(project_id: str, req: dict, _user: str = Depends(require_auth)) -> dict:
    """Prueft das Brainstorming-MD auf Rechtschreibung, Zeichensetzung, Widersprueche und Vollstaendigkeit."""
    md_content = req.get("md_content", "")
    if not md_content:
        raise HTTPException(400, "md_content fehlt")

    issues: list[dict] = []

    # === 1. VOLLSTÄNDIGKEIT ===
    questions_total = len(re.findall(r"###\s+[✅⏳]\s+Frage\s+\d+", md_content))
    questions_answered = len(re.findall(r"###\s+✅\s+Frage\s+\d+", md_content))
    questions_open = questions_total - questions_answered
    if questions_total == 0:
        issues.append({
            "severity": "medium",
            "category": "completeness",
            "location": "Fragenkatalog",
            "message": "Keine Verständnisfragen erkannt - Brainstorming evtl. unvollständig?",
        })
    elif questions_open > 0:
        issues.append({
            "severity": "high" if questions_open > 2 else "medium",
            "category": "completeness",
            "location": "Fragenkatalog",
            "message": f"{questions_open} von {questions_total} Verständnisfragen noch offen. Vollständigkeit: {int(questions_answered / questions_total * 100)}%",
        })

    # === 2. ZEICHENSETZUNG ===
    if "\n\n\n" in md_content:
        issues.append({
            "severity": "low",
            "category": "punctuation",
            "location": "Dokument",
            "message": f"{md_content.count(chr(10) + chr(10) + chr(10))}x dreifache Zeilenumbrüche gefunden (sollten max. doppelt sein)",
        })
    if re.search(r"  +", md_content):
        count = len(re.findall(r"  +", md_content))
        issues.append({
            "severity": "low",
            "category": "punctuation",
            "location": "Dokument",
            "message": f"{count} Stellen mit mehrfachen Leerzeichen",
        })
    # Fehlende Satzzeichen am Zeilenende (Bullet-Items ohne Punkt)
    bullet_lines = re.findall(r"^[-*]\s+(.+)$", md_content, re.MULTILINE)
    for bl in bullet_lines:
        if bl and not bl.endswith((".", "!", "?", ":", "`")) and len(bl) > 20:
            issues.append({
                "severity": "low",
                "category": "punctuation",
                "location": f"Liste: \"{bl[:50]}...\"",
                "message": "Bullet-Punkt endet nicht mit Satzzeichen",
            })
            break  # nur einen melden, nicht spammen

    # === 3. RECHTSCHREIBUNG (einfache Heuristik) ===
    # Typische deutsche Tippfehler
    typo_patterns = [
        (r"\bdass\s+ist\b", "dass vs. das - Kontextpruefung noetig"),
        (r"\bwidersprüchlich\w*\b", "Doppel-s-Schreibung prüfen: 'widersprüchlich' (richtig) vs. 'widersprüchlich'"),
        (r"\bwiederspruch\w*\b", "Möglich: 'Widerspruch' (richtig) statt 'Wiederspruch'"),
        (r"\bvollständigkeit\w*\b", "Schreibweise prüfen"),
        (r"\brequirement\w*\b", "Mischsprache: 'Anforderung' wäre konsistenter"),
        (r"\bRequierment\w*\b", "Tippfehler: 'Requirement' oder 'Anforderung'"),
    ]
    for pattern, msg in typo_patterns:
        matches = re.findall(pattern, md_content, re.IGNORECASE)
        if matches:
            issues.append({
                "severity": "low",
                "category": "spelling",
                "location": f"Gefunden: '{matches[0]}'",
                "message": msg,
            })

    # === 4. WIDERSPRÜCHE (einfache Heuristik) ===
    # Suche nach Zahlenpaaren mit gleicher Einheit
    numbers = re.findall(r"(\d+)\s*(Minuten|Stunden|Tage|Wochen|Monate|%|Euro|€|ms|s)\b", md_content)
    seen = {}
    for num, unit in numbers:
        key = unit.lower()
        if key in seen and seen[key] != num:
            issues.append({
                "severity": "medium",
                "category": "contradiction",
                "location": f"Zahlenwert mit Einheit '{unit}'",
                "message": f"Widerspruchliche Angaben gefunden: '{seen[key]} {unit}' vs. '{num} {unit}' - bitte pruefen",
            })
        seen[key] = num

    # === 5. REDUNDANZEN ===
    duplicate_h3 = re.findall(r"###\s+(.+)", md_content)
    if len(duplicate_h3) != len(set(duplicate_h3)):
        issues.append({
            "severity": "low",
            "category": "redundancy",
            "location": "Headings",
            "message": "Doppelte Überschriften gefunden",
        })

    # === 6. NALABS: Requirement Quality Check (akademisch fundiert) ===
    # Wende NALABS-Methode auf alle extrahierten User-Input-Zitate an
    quote_blocks = re.findall(r"^>\s+(.+?)$", md_content, re.MULTILINE)
    if not quote_blocks:
        # Fallback: pruefe den ganzen Text
        quote_blocks = [md_content[:2000]]
    nalabs_result = nalabs_batch(quote_blocks)
    # Merge NALABS-Issues
    for r in nalabs_result["results"]:
        for nalabs_issue in r["issues"]:
            issues.append({
                "severity": nalabs_issue["severity"],
                "category": f"nalabs_{nalabs_issue['category']}",
                "location": f"NALABS-Smell (Quote: \"{r['text'][:60]}...\")",
                "message": nalabs_issue["message"],
            })
    # Security-Hints (positiv): wenn Security-Keywords erkannt, aber kein NFR-Security
    has_security_nfr = "sicherheit" in md_content.lower() or "security" in md_content.lower() or "dsgvo" in md_content.lower()
    if nalabs_result["summary"]["security_related"] > 0 and not has_security_nfr:
        issues.append({
            "severity": "low",
            "category": "nalabs_security_hint",
            "location": "Security-Keywords erkannt",
            "message": f"Security-bezogene Begriffe in {nalabs_result['summary']['security_related']} Inputs erkannt. "
                       f"Bitte sicherstellen, dass ein NFR-XXX fuer Security vorhanden ist.",
        })

    # Stats
    total_chars = len(md_content)
    stats = {
        "total_chars": total_chars,
        "total_lines": md_content.count("\n") + 1,
        "questions_total": questions_total,
        "questions_answered": questions_answered,
        "completeness_pct": int(questions_answered / questions_total * 100) if questions_total > 0 else 0,
        "open_questions": questions_open,
        "nalabs_quote_blocks_checked": len(quote_blocks),
        "nalabs_avg_flesch": nalabs_result["summary"]["avg_flesch"],
        "nalabs_avg_words": nalabs_result["summary"]["avg_word_count"],
        "nalabs_security_hints": nalabs_result["summary"]["security_related"],
    }
    # Score
    high = sum(1 for i in issues if i["severity"] == "high")
    medium = sum(1 for i in issues if i["severity"] == "medium")
    low = sum(1 for i in issues if i["severity"] == "low")
    if high > 0:
        score = "block"
    elif medium > 0:
        score = "review"
    elif low > 0:
        score = "minor"
    else:
        score = "ok"

    # === Auto-Resolution: Welche Issues kann der Agent selbst loesen? ===
    # Heuristik: NALABS-Smells (Wortwahl/Subjektivitaet) sind automatisch erkannt,
    # aber NICHT automatisch behebbar -> immer Rueckfragen.
    # Heuristische Issues (Tippfehler, fehlende Schluesselwoerter) koennen
    # auto-korrigiert werden.
    auto_resolvable: list[dict] = []  # Issues, die der Agent auto-fix koennte
    needs_clarification: list[dict] = []  # Issues, die User-Eingabe brauchen
    for issue in issues:
        cat = issue.get("category", "")
        # NALABS-Kategorien: immer Rueckfrage
        if cat.startswith("nalabs_"):
            if cat == "nalabs_missing_keyword":
                needs_clarification.append({
                    "category": "keyword",
                    "question": f"Soll das Modalverb im Requirement ergaenzt werden? ({issue['message']})",
                    "context": issue.get("location", ""),
                    "issue_ref": cat,
                })
            elif cat == "nalabs_subjectivity":
                needs_clarification.append({
                    "category": "subjectivity",
                    "question": f"Bitte praezisieren Sie subjektive Begriffe: {issue['message']}",
                    "context": issue.get("location", ""),
                    "issue_ref": cat,
                })
            elif cat == "nalabs_vagueness":
                needs_clarification.append({
                    "category": "vagueness",
                    "question": f"Bitte konkretisieren Sie vage Begriffe: {issue['message']}",
                    "context": issue.get("location", ""),
                    "issue_ref": cat,
                })
            elif cat == "nalabs_optionality":
                needs_clarification.append({
                    "category": "optionality",
                    "question": f"Soll das Requirement optional oder verpflichtend sein? ({issue['message']})",
                    "context": issue.get("location", ""),
                    "issue_ref": cat,
                })
            elif cat == "nalabs_readability":
                # Readability ist messbar, aber Verbesserung braucht User-Input
                needs_clarification.append({
                    "category": "readability",
                    "question": f"Der Text ist schwer lesbar. Moechten Sie ihn umformulieren? ({issue['message']})",
                    "context": issue.get("location", ""),
                    "issue_ref": cat,
                })
            else:
                needs_clarification.append({
                    "category": cat.replace("nalabs_", ""),
                    "question": issue.get("message", cat),
                    "context": issue.get("location", ""),
                    "issue_ref": cat,
                })
        elif cat == "spelling":
            # Tippfehler koennen auto-korrigiert werden
            auto_resolvable.append({
                "issue": issue,
                "suggested_fix": "Tippfehler korrigieren (z.B. 'Requierment' -> 'Requirement')",
            })
        elif cat == "punctuation":
            # Zeichensetzung kann auto-korrigiert werden
            auto_resolvable.append({
                "issue": issue,
                "suggested_fix": "Mehrfache Leerzeichen / Zeilenumbrueche bereinigen",
            })
        elif cat == "redundancy":
            needs_clarification.append({
                "category": "redundancy",
                "question": f"Redundanz gefunden: {issue.get('message', 'Doppelte Headings')}. Welche Version soll behalten werden?",
                "context": issue.get("location", ""),
                "issue_ref": cat,
            })
        elif cat == "contradiction":
            # Widersprueche: brauchen immer User-Klaerung
            needs_clarification.append({
                "category": "contradiction",
                "question": f"Widerspruch gefunden: {issue.get('message', '')}. Welche Angabe ist korrekt?",
                "context": issue.get("location", ""),
                "issue_ref": cat,
            })
        elif cat == "completeness":
            # Vollstaendigkeit: offene Fragen -> User klaeren
            needs_clarification.append({
                "category": "completeness",
                "question": f"Vollstaendigkeits-Issue: {issue.get('message', '')}",
                "context": issue.get("location", ""),
                "issue_ref": cat,
            })

    return {
        "ok": True,
        "stats": stats,
        "issues": issues,
        "score": score,  # "ok" | "minor" | "review" | "block"
        "issue_counts": {"high": high, "medium": medium, "low": low},
        "auto_resolvable": auto_resolvable,
        "needs_clarification": needs_clarification,
        "phase": "quality_check",  # Marker: Schritt 2 (Qualitaetspruefung)
    }


# ─── 2-STUFIGER REVIEW-PROZESS ───────────────────────────────────

@router.post("/completeness-check/{project_id}")
async def completeness_check(project_id: str, _user: str = Depends(require_auth)) -> dict:
    """Schritt 1: Vollstaendigkeitspruefung.

    Reihenfolge:
    1. OpenBrain nach vorhandenen Informationen durchsuchen
    2. Wenn unvollstaendig: Klärungsfragen generieren
    """
    _ensure_dir()
    projects = _load_json(KANBAN_DIR / "projects.json")
    proj = next((p for p in projects if p["id"] == project_id), None)
    if not proj:
        raise HTTPException(404, "Project not found")
    brain_log = proj.get("brainstorm_log", [])
    user_inputs = [t["text"] for t in brain_log if t["role"] == "user"]
    if not user_inputs:
        raise HTTPException(400, "Kein Brainstorming vorhanden")

    # === TEIL 1: OpenBrain-Recherche ===
    bb_url = "http://127.0.0.1:9302/"
    bb_key = "ob-bb-key-2026"
    dev_url = "http://127.0.0.1:9303/"
    dev_key = "ob-dev-key-2026"

    # Sammle zu pruefende Themen
    vision = user_inputs[0] if user_inputs else ""
    proj_desc = proj.get("description", "")
    all_text_lower = (proj_desc + " " + " ".join(user_inputs)).lower()

    queries = [
        ("bB", bb_url, bb_key, "Policy Standard Compliance Vorgabe"),
        ("bB", bb_url, bb_key, "Lizenz AGPL Open-Source"),
        ("bB", bb_url, bb_key, "DSGVO Datenschutz Compliance"),
        ("bB", bb_url, bb_key, "Sicherheit Security Vorgabe"),
        ("bB", bb_url, bb_key, "Architektur Standard"),
        ("bB", bb_url, bb_key, "Projekt-Vorlage Template"),
        ("DEV", dev_url, dev_key, "Architektur Pattern"),
        ("DEV", dev_url, dev_key, "Coding Standard Style"),
    ]
    if any(kw in all_text_lower for kw in ["python", "fastapi"]):
        queries.append(("DEV", dev_url, dev_key, "Python FastAPI"))
    if any(kw in all_text_lower for kw in ["react", "frontend"]):
        queries.append(("DEV", dev_url, dev_key, "React Frontend"))
    if any(kw in all_text_lower for kw in ["docker", "kubernetes", "deployment"]):
        queries.append(("DEV", dev_url, dev_key, "Docker Deployment"))

    # OpenBrain durchsuchen
    found_vorgaben = []
    import httpx
    for brain_name, url, key, query in queries:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "openbrain_search",
                "arguments": {"query": query, "limit": 2, "threshold": 0.15},
            },
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.post(url, json=payload, headers={"Content-Type": "application/json", "x-brain-key": key})
            if r.status_code == 200:
                data = r.json()
                content = data.get("result", {}).get("content", [])
                if content:
                    text = content[0].get("text", "")
                    for line in text.split("\n"):
                        line = line.strip()
                        if not line or not line.startswith("["):
                            continue
                        m = re.match(r"\[\d+\]\s+\[([^\]]+)\]\s+(?:\[([^\]]+)\]\s+)?(.+?)\s*\(sim:([\d.]+)", line)
                        if m:
                            found_vorgaben.append({
                                "brain": brain_name,
                                "thought_type": m.group(1),
                                "topic": m.group(2) or "",
                                "content": m.group(3).strip(),
                                "similarity": float(m.group(4)),
                                "query": query,
                            })
        except Exception:
            pass

    # === TEIL 2: Vollstaendigkeitspruefung ===
    # Welche CIO-Themen sind offen?
    addressed_cio = []
    for check in CIO_CHECKS:
        for kw in check["keywords"]:
            if kw in all_text_lower:
                addressed_cio.append(check["topic"])
                break
    open_cio_topics = [c["topic"] for c in CIO_CHECKS if c["topic"] not in addressed_cio]
    # CEO-Antworten vorhanden?
    ceo_answered_count = min(len(user_inputs) - 1, len(CONVERSATION_QUESTIONS))
    cio_answered_count = max(0, len(user_inputs) - 1 - len(CONVERSATION_QUESTIONS))
    cio_open_count = max(0, len(open_cio_topics) - cio_answered_count)
    # Mindestens CEO + alle CIO adressiert?
    is_complete = (ceo_answered_count >= len(CONVERSATION_QUESTIONS)) and (cio_open_count == 0)

    # === Klärungsfragen generieren ===
    clarifications: list[dict] = []
    if not is_complete:
        # 1. Offene CEO-Fragen
        for i in range(ceo_answered_count, len(CONVERSATION_QUESTIONS)):
            clarifications.append({
                "id": f"ceo_{i+1}",
                "phase": "CEO",
                "category": "business",
                "question": CONVERSATION_QUESTIONS[i],
                "context": "Diese Geschaeftsfrage wurde im Brainstorming noch nicht beantwortet.",
                "openbrain_refs": [],
            })
        # 2. Offene CIO-Themen
        cio_idx = 0
        for topic in open_cio_topics:
            cio_idx += 1
            check = next((c for c in CIO_CHECKS if c["topic"] == topic), None)
            if check and cio_idx > cio_answered_count:
                clarifications.append({
                    "id": f"cio_{cio_idx}",
                    "phase": "CIO",
                    "category": "technical",
                    "question": check["question"],
                    "context": check["recommendation"],
                    "openbrain_refs": [v for v in found_vorgaben if topic.lower() in v.get("content", "").lower()][:2],
                })

    # === Persistenz: Klärungsantworten laden + Status prüfen ===
    completeness_data = _load_json(KANBAN_DIR / "completeness.json", default={})
    existing = completeness_data.get(project_id, {})
    saved_answers = existing.get("answers", {}) if isinstance(existing.get("answers"), dict) else {}
    saved_clarifications = existing.get("clarifications", [])

    # Wenn bereits Clarifications existieren UND die Liste im Wesentlichen gleich ist,
    # verwende die gespeicherten (mit Antworten), sonst aktualisiere mit neuen.
    def _same_set(a: list, b: list) -> bool:
        return {c.get("id") for c in a} == {c.get("id") for c in b}
    if saved_clarifications and _same_set(saved_clarifications, clarifications):
        clarifications = saved_clarifications
    else:
        # Neue Runde: speichere
        completeness_data[project_id] = {
            "clarifications": clarifications,
            "answers": {c["id"]: None for c in clarifications},
            "started_at": _now(),
            "is_complete": is_complete,
        }
        _save_json(KANBAN_DIR / "completeness.json", completeness_data)
        saved_answers = completeness_data[project_id]["answers"]

    # Mergen: gespeicherte Antworten in die clarifications einbauen
    def _has_answer(v):
        if v is None: return False
        if isinstance(v, dict): return bool((v.get("text") or "").strip())
        return bool(str(v).strip())
    for c in clarifications:
        c["user_answer"] = saved_answers.get(c["id"])
        c["answered"] = _has_answer(saved_answers.get(c["id"]))

    # Re-evaluate completeness mit aktuellen Antworten
    answered_count = sum(1 for c in clarifications if c.get("answered"))
    is_complete_answered = (answered_count == len(clarifications)) if clarifications else is_complete
    # Auch: alle CEO + alle CIO urspruenglich abgefragt?
    ceo_done = ceo_answered_count >= len(CONVERSATION_QUESTIONS)
    cio_done = cio_open_count == 0
    is_complete = (ceo_done and cio_done)

    open_count = len(clarifications) - answered_count

    return {
        "ok": True,
        "phase": "completeness_check",
        "is_complete": is_complete,
        "openbrain_vorgaben_count": len(found_vorgaben),
        "openbrain_vorgaben": found_vorgaben[:10],
        "ceo_progress": {"answered": ceo_answered_count, "total": len(CONVERSATION_QUESTIONS)},
        "cio_progress": {"open_topics": open_cio_topics, "answered": cio_answered_count},
        "clarifications": clarifications,
        "summary": {
            "ceo_complete": ceo_done,
            "cio_open_count": cio_open_count,
            "can_proceed_to_quality": is_complete,
            "clarifications_total": len(clarifications),
            "clarifications_answered": answered_count,
            "clarifications_open": open_count,
        },
    }


@router.get("/completeness/{project_id}")
async def get_completeness_status(project_id: str, _user: str = Depends(require_auth)) -> dict:
    """Aktueller Vollständigkeits-Status (mit gespeicherten Antworten)."""
    completeness_data = _load_json(KANBAN_DIR / "completeness.json", default={})
    rec = completeness_data.get(project_id)
    if not rec:
        raise HTTPException(404, "Keine Completeness-Pruefung vorhanden — zuerst starten")
    return rec


# ─── 9-Schritt-Review-Pipeline (einzelne KI-Abfragen pro Schritt) ─────────────────

REVIEW_PIPELINE_STEPS = [
    {"id": "step_1_create_md", "label": "Ziel-MD Dokument erstellen", "icon": "📄"},
    {"id": "step_2_redundancy", "label": "Redundanzen suchen + beheben", "icon": "🗂️"},
    {"id": "step_3_open_topics", "label": "Offene Themen erkennen", "icon": "📋"},
    {"id": "step_4_spelling", "label": "Rechtschreibprüfung", "icon": "🔤"},
    {"id": "step_5_punctuation", "label": "Zeichensetzung", "icon": "⸮"},
    {"id": "step_6_sentences", "label": "Satzaufbau", "icon": "✍️"},
    {"id": "step_7_layout", "label": "Formales Layout", "icon": "📐"},
    {"id": "step_8_contradictions", "label": "Inhaltliche Widersprüche", "icon": "⚠️"},
    {"id": "step_9_questions", "label": "Offene Fragen (User)", "icon": "❓"},
]


def _run_step_1_create_md(project_id: str, proj: dict, brain_log: list, user_inputs: list) -> dict:
    """Schritt 1: Ziel-MD Dokument aus dem aktuellen Brainstorming-Log erstellen/aktualisieren."""
    _ensure_dir()
    files = sorted(REQUIREMENTS_DIR.glob(f"{project_id}_*.md"))
    if files:
        content = files[-1].read_text(encoding="utf-8", errors="ignore")
    else:
        content = f"# Ziel-MD: {proj['name']}\n\n> (noch nicht generiert)\n"
    return {
        "status": "done",
        "file": str(files[-1]) if files else None,
        "chars": len(content),
        "lines": content.count("\n") + 1,
        "summary": f"Ziel-MD Dokument mit {len(content)} Zeichen geladen." + (" (aus Cache)" if files else " (frisch)"),
    }


def _run_step_2_redundancy(project_id: str, proj: dict, brain_log: list, md_content: str) -> dict:
    """Schritt 2: Redundanzen im MD suchen + beheben."""
    issues = []
    h3_list = re.findall(r"^### (.+)$", md_content, re.MULTILINE)
    seen = {}
    for h in h3_list:
        seen[h] = seen.get(h, 0) + 1
    dups = [h for h, c in seen.items() if c > 1]
    if dups:
        issues.append({"type": "duplicate_heading", "items": dups[:5], "fix": "Doppelte Headings zusammenfuehren oder umformulieren"})
    paragraphs = re.split(r"\n\n+", md_content)
    para_starts = [p[:60] for p in paragraphs if len(p) > 60]
    seen_starts = {}
    for s in para_starts:
        seen_starts[s] = seen_starts.get(s, 0) + 1
    repeated = [s for s, c in seen_starts.items() if c > 1]
    if repeated:
        issues.append({"type": "repeated_paragraph", "items": repeated[:3], "fix": "Wiederholende Absaetze konsolidieren"})
    return {
        "status": "done",
        "redundancies_found": len(issues),
        "issues": issues,
        "summary": f"{len(issues)} Redundanz-Issue(s) gefunden." if issues else "Keine Redundanzen gefunden.",
    }


def _run_step_3_open_topics(project_id: str, proj: dict, brain_log: list, md_content: str) -> dict:
    """Schritt 3: Offene Themen erkennen."""
    proj_desc = (proj.get("description") or "").lower()
    all_text = (proj_desc + " " + md_content).lower()
    themes = {
        "Architektur": ["architektur", "microservice", "monolith", "soa", "modular"],
        "Tech-Stack": ["python", "javascript", "react", "node", "java", "typescript"],
        "Datenbank": ["datenbank", "postgres", "mysql", "mongo", "redis", "sql"],
        "Deployment": ["docker", "kubernetes", "aws", "azure", "cloud"],
        "Authentifizierung": ["oauth", "authentifizierung", "auth", "login", "jwt"],
        "Sicherheit": ["security", "sicherheit", "dsgvo", "gdpr", "verschl"],
        "Skalierung": ["skalier", "scale", "concurrent", "performance"],
        "Testing": ["test", "ci/cd", "pytest", "coverage"],
        "Backup": ["backup", "recovery", "snapshot"],
    }
    addressed = []
    open_topics = []
    for theme, kws in themes.items():
        if any(kw in all_text for kw in kws):
            addressed.append(theme)
        else:
            open_topics.append(theme)
    return {
        "status": "done",
        "addressed_themes": addressed,
        "open_topics": open_topics,
        "summary": f"{len(addressed)} adressiert, {len(open_topics)} offen: {', '.join(open_topics) if open_topics else '—'}",
    }


def _run_step_4_spelling(project_id: str, proj: dict, brain_log: list, md_content: str) -> dict:
    """Schritt 4: Rechtschreibpruefung."""
    typos = []
    typo_patterns = [
        (r"\bdass\s+ist\b", "dass vs. das"),
        (r"\bwiederspruch\w*\b", "Widerspruch (nicht Wiederspruch)"),
        (r"\brequirement\w*\b", "Mischsprache: Anforderung"),
        (r"\bRequierment\w*\b", "Tippfehler"),
        (r"\bstandart\w*\b", "Standard (nicht Standart)"),
    ]
    for pat, msg in typo_patterns:
        matches = re.findall(pat, md_content, re.IGNORECASE)
        if matches:
            typos.append({"term": matches[0], "message": msg, "count": len(matches)})
    return {
        "status": "done",
        "typos_found": len(typos),
        "typos": typos,
        "summary": f"{len(typos)} moegliche Tippfehler." if typos else "Keine Tippfehler.",
    }


def _run_step_5_punctuation(project_id: str, proj: dict, brain_log: list, md_content: str) -> dict:
    """Schritt 5: Zeichensetzung."""
    issues = []
    dbl_space = len(re.findall(r"  +", md_content))
    if dbl_space > 0:
        issues.append({"type": "double_spaces", "count": dbl_space, "fix": "Doppelte Leerzeichen entfernen"})
    triple_nl = md_content.count("\n\n\n")
    if triple_nl > 0:
        issues.append({"type": "triple_newlines", "count": triple_nl, "fix": "Maximal 2 Zeilenumbrueche"})
    bullets = re.findall(r"^[-*]\s+(.+)$", md_content, re.MULTILINE)
    no_punct = [b[:50] for b in bullets if b and not b.endswith((".", "!", "?", ":", "`")) and len(b) > 20]
    if no_punct:
        issues.append({"type": "bullet_no_punct", "count": len(no_punct), "samples": no_punct[:3], "fix": "Bullets mit Satzzeichen beenden"})
    return {
        "status": "done",
        "issues": issues,
        "summary": f"{len(issues)} Zeichensetzungs-Issue(s)." if issues else "Zeichensetzung OK.",
    }


def _run_step_6_sentences(project_id: str, proj: dict, brain_log: list, md_content: str) -> dict:
    """Schritt 6: Satzaufbau (Laenge, Lesbarkeit)."""
    sentences = re.split(r"[.!?]+\s+", md_content)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    long_sentences = [s for s in sentences if len(s) > 200]
    very_long = [s for s in sentences if len(s) > 300]
    try:
        from textstat import flesch_reading_ease
        flesch = round(flesch_reading_ease(md_content), 1)
    except Exception:
        flesch = None
    issues = []
    if long_sentences:
        issues.append({"type": "long_sentences", "count": len(long_sentences), "fix": "Saetze > 200 Zeichen aufteilen"})
    if very_long:
        issues.append({"type": "very_long_sentences", "count": len(very_long), "fix": "Saetze > 300 Zeichen unbedingt aufteilen"})
    if flesch is not None and flesch < 30:
        issues.append({"type": "low_readability", "flesch": flesch, "fix": "Lesbarkeit verbessern"})
    return {
        "status": "done",
        "total_sentences": len(sentences),
        "flesch": flesch,
        "issues": issues,
        "summary": f"{len(sentences)} Saetze, Flesch: {flesch}." if flesch is not None else f"{len(sentences)} Saetze.",
    }


def _run_step_7_layout(project_id: str, proj: dict, brain_log: list, md_content: str) -> dict:
    """Schritt 7: Formales Layout (Markdown-Hierarchie)."""
    issues = []
    headings = re.findall(r"^(#+)\s+(.+)$", md_content, re.MULTILINE)
    prev_level = 0
    for hashes, title in headings:
        level = len(hashes)
        if prev_level > 0 and level > prev_level + 1:
            issues.append({"type": "heading_skip", "from": prev_level, "to": level, "title": title[:50]})
        prev_level = level
    h1_count = sum(1 for h in headings if len(h[0]) == 1)
    h2_count = sum(1 for h in headings if len(h[0]) == 2)
    if h1_count == 0:
        issues.append({"type": "no_h1", "fix": "Dokument braucht eine H1-Ueberschrift"})
    if h2_count == 0 and len(headings) > 3:
        issues.append({"type": "no_h2", "fix": "Dokument sollte H2-Sektionen haben"})
    return {
        "status": "done",
        "headings_total": len(headings),
        "issues": issues,
        "summary": f"{len(headings)} Headings, {len(issues)} Layout-Issue(s)." if issues else f"{len(headings)} Headings, Layout OK.",
    }


def _run_step_8_contradictions(project_id: str, proj: dict, brain_log: list, md_content: str) -> dict:
    """Schritt 8: Inhaltliche Widersprueche."""
    contrad = []
    numbers = re.findall(r"(\d+)\s*(Minuten|Stunden|Tage|Wochen|Monate|%|Euro|€|ms|s)\b", md_content)
    seen = {}
    for num, unit in numbers:
        key = unit.lower()
        if key in seen and seen[key] != num:
            contrad.append({"type": "conflicting_numbers", "unit": unit, "values": [seen[key], num]})
        seen[key] = num
    time_patterns = re.findall(r"(\d+)\s*(Tage|Wochen|Monate)\b", md_content)
    if len(set([t[1] for t in time_patterns])) > 1:
        contrad.append({"type": "mixed_time_units", "units": list(set([t[1] for t in time_patterns]))})
    return {
        "status": "done",
        "contradictions_found": len(contrad),
        "contradictions": contrad,
        "summary": f"{len(contrad)} Widerspruch/Widersprueche." if contrad else "Keine Widersprueche.",
    }


def _run_step_9_questions(project_id: str, proj: dict, brain_log: list, md_content: str) -> dict:
    """Schritt 9: Offene Fragen erkennen, die User beantworten muss."""
    questions = []
    completeness_data = _load_json(KANBAN_DIR / "completeness.json", default={})
    comp_rec = completeness_data.get(project_id, {})
    for c in comp_rec.get("clarifications", []):
        ans = comp_rec.get("answers", {}).get(c["id"])
        answered = bool(ans and (ans.get("text") if isinstance(ans, dict) else ans))
        if not answered:
            questions.append({
                "id": c["id"], "source": "completeness",
                "phase": c.get("phase"), "category": c.get("category"),
                "question": c["question"], "context": c.get("context"),
            })
    quality_data = _load_json(KANBAN_DIR / "quality_clarifications.json", default={})
    qual_rec = quality_data.get(project_id, {})
    for c in qual_rec.get("clarifications", []):
        ans = qual_rec.get("answers", {}).get(c["id"])
        answered = bool(ans and (ans.get("text") if isinstance(ans, dict) else ans))
        if not answered:
            questions.append({
                "id": c["id"], "source": "quality",
                "category": c.get("category"),
                "question": c["question"], "context": c.get("context"),
            })
    return {
        "status": "done",
        "open_questions": questions,
        "open_count": len(questions),
        "summary": f"{len(questions)} offene Frage(n)." if questions else "Alle beantwortet.",
    }


@router.post("/review/pipeline/{project_id}")
async def run_review_pipeline(project_id: str, _user: str = Depends(require_auth)) -> dict:
    """Startet die 9-Schritt-Review-Pipeline."""
    _ensure_dir()
    projects = _load_json(KANBAN_DIR / "projects.json")
    proj = next((p for p in projects if p["id"] == project_id), None)
    if not proj:
        raise HTTPException(404, "Project not found")
    brain_log = proj.get("brainstorm_log", [])
    user_inputs = [t["text"] for t in brain_log if t["role"] == "user"]
    if not user_inputs:
        raise HTTPException(400, "Kein Brainstorming vorhanden")
    files = sorted(REQUIREMENTS_DIR.glob(f"{project_id}_*.md"))
    md_content = files[-1].read_text(encoding="utf-8", errors="ignore") if files else ""
    if not md_content:
        md_content = f"# {proj['name']}\n\n" + "\n\n".join([f"## Vision\n\n{user_inputs[0]}"] + [f"- {u}" for u in user_inputs[1:]])
    steps_results = []
    for i, step in enumerate(REVIEW_PIPELINE_STEPS):
        runner = globals().get(f"_run_{step['id']}")
        if runner:
            try:
                result = runner(project_id, proj, brain_log, md_content)
                result["step_id"] = step["id"]
                result["step_label"] = step["label"]
                result["step_icon"] = step["icon"]
                result["step_index"] = i + 1
            except Exception as e:
                result = {"status": "error", "error": str(e)[:200], "step_id": step["id"], "step_label": step["label"], "step_icon": step["icon"], "step_index": i + 1}
        else:
            result = {"status": "skipped", "step_id": step["id"], "step_label": step["label"]}
        steps_results.append(result)
    pipelines = _load_json(KANBAN_DIR / "review_pipelines.json", default={})
    pipelines[project_id] = {
        "project_id": project_id,
        "started_at": _now(),
        "completed_at": _now(),
        "steps": steps_results,
    }
    _save_json(KANBAN_DIR / "review_pipelines.json", pipelines)
    return {
        "ok": True,
        "project_id": project_id,
        "started_at": pipelines[project_id]["started_at"],
        "completed_at": pipelines[project_id]["completed_at"],
        "steps": steps_results,
    }


@router.get("/review/pipeline/{project_id}")
async def get_review_pipeline(project_id: str, _user: str = Depends(require_auth)) -> dict:
    """Liest den letzten Review-Pipeline-Status."""
    pipelines = _load_json(KANBAN_DIR / "review_pipelines.json", default={})
    rec = pipelines.get(project_id)
    if not rec:
        raise HTTPException(404, "Keine Review-Pipeline vorhanden — zuerst starten")
    return rec


@router.post("/completeness/{project_id}/answer")
async def answer_completeness_clarification(project_id: str, req: dict, _user: str = Depends(require_auth)) -> dict:
    """Beantwortet eine Klärungsfrage aus der Completeness-Pruefung."""
    completeness_data = _load_json(KANBAN_DIR / "completeness.json", default={})
    rec = completeness_data.get(project_id)
    if not rec:
        raise HTTPException(404, "Keine Completeness-Pruefung vorhanden")
    clarification_id = req.get("clarification_id", "")
    answer = req.get("answer", "")
    answers = rec.get("answers", {})
    if clarification_id not in answers:
        raise HTTPException(404, f"Unbekannte Klaerungsfrage: {clarification_id}")
    answers[clarification_id] = {
        "text": answer,
        "answered_at": _now(),
    }
    rec["answers"] = answers
    # Update is_complete: alle beantwortet? (None-Werte zaehlen als nicht beantwortet)
    def _has_answer(v):
        if v is None: return False
        if isinstance(v, dict): return bool((v.get("text") or "").strip())
        return bool(str(v).strip())
    all_answered = all(_has_answer(v) for v in answers.values())
    rec["is_complete"] = all_answered
    if all_answered:
        rec["completed_at"] = _now()
    completeness_data[project_id] = rec
    _save_json(KANBAN_DIR / "completeness.json", completeness_data)
    return {
        "ok": True,
        "clarification_id": clarification_id,
        "all_answered": all_answered,
        "is_complete": rec["is_complete"],
        "open_count": sum(1 for v in answers.values() if not _has_answer(v)),
    }


# ─── Quality-Rückfragen (aus NALABS-Review) ───────────────────────────────

@router.post("/quality/{project_id}/save-clarifications")
async def save_quality_clarifications(project_id: str, req: dict, _user: str = Depends(require_auth)) -> dict:
    """Speichert die aus dem Quality-Review generierten Rueckfragen persistent."""
    _ensure_dir()
    quality_data = _load_json(KANBAN_DIR / "quality_clarifications.json", default={})
    clarifications = req.get("clarifications", [])
    if not isinstance(clarifications, list):
        raise HTTPException(400, "clarifications muss eine Liste sein")
    for i, c in enumerate(clarifications):
        if not c.get("id"):
            c["id"] = f"qc_{i+1}"
    rec = quality_data.get(project_id, {})
    rec["clarifications"] = clarifications
    rec["answers"] = {c["id"]: rec.get("answers", {}).get(c["id"]) for c in clarifications}
    rec["started_at"] = rec.get("started_at") or _now()
    quality_data[project_id] = rec
    _save_json(KANBAN_DIR / "quality_clarifications.json", quality_data)
    return {"ok": True, "saved": len(clarifications), "project_id": project_id}


@router.get("/quality/{project_id}")
async def get_quality_status(project_id: str, _user: str = Depends(require_auth)) -> dict:
    quality_data = _load_json(KANBAN_DIR / "quality_clarifications.json", default={})
    rec = quality_data.get(project_id)
    if not rec:
        raise HTTPException(404, "Keine Quality-Klaerungsfragen vorhanden")
    return rec


@router.post("/quality/{project_id}/answer")
async def answer_quality_clarification(project_id: str, req: dict, _user: str = Depends(require_auth)) -> dict:
    """Beantwortet eine Quality-Rueckfrage. Antwort wird als User-Input ins Brainstorming-Log eingefuegt, damit das naechste Review sie beruecksichtigt."""
    quality_data = _load_json(KANBAN_DIR / "quality_clarifications.json", default={})
    rec = quality_data.get(project_id)
    if not rec:
        raise HTTPException(404, "Keine Quality-Klaerungsfragen vorhanden")
    clarification_id = req.get("clarification_id", "")
    answer = req.get("answer", "")
    answers = rec.get("answers", {})
    if clarification_id not in answers:
        raise HTTPException(404, f"Unbekannte Klaerungsfrage: {clarification_id}")
    answers[clarification_id] = {
        "text": answer,
        "answered_at": _now(),
    }
    rec["answers"] = answers
    quality_data[project_id] = rec
    _save_json(KANBAN_DIR / "quality_clarifications.json", quality_data)
    # Antwort als User-Input ins Brainstorming-Log einfuegen
    projects = _load_json(KANBAN_DIR / "projects.json")
    proj = next((p for p in projects if p["id"] == project_id), None)
    if proj:
        brain_log = proj.get("brainstorm_log", [])
        c = next((c for c in rec.get("clarifications", []) if c["id"] == clarification_id), None)
        if c:
            brain_log.append({
                "role": "user",
                "text": f"Klärung zu {c.get('category', 'Quality')}: {answer}",
                "phase": "clarification",
                "ts": _now(),
                "clarification_ref": clarification_id,
            })
            proj["brainstorm_log"] = brain_log
            _save_json(KANBAN_DIR / "projects.json", projects)
    def _has_answer(v):
        if v is None: return False
        if isinstance(v, dict): return bool((v.get("text") or "").strip())
        return bool(str(v).strip())
    all_answered = all(_has_answer(v) for v in answers.values())
    return {
        "ok": True,
        "clarification_id": clarification_id,
        "all_answered": all_answered,
        "open_count": sum(1 for v in answers.values() if not _has_answer(v)),
    }


# ─── OpenBrain DEV ────────────────────────────────────────────────

@router.get("/brain-dev")
async def get_brain_dev(_user: str = Depends(require_auth)) -> dict:
    """Holt Entwicklungs-Wissen aus OpenBrain DEV fuer hochwertige Anforderungsdokumente.

    Verwendet MCP/JSON-RPC-Protokoll gegen den lokalen OpenBrain DEV-Container.
    Sucht nach Vorgaben aus diesen Kategorien:
    - Architektur-Patterns (Microservices, Monolith, Modular, Event-driven)
    - API-Design-Standards (REST, OpenAPI, GraphQL, gRPC)
    - Code-Standards (Clean Code, SOLID, DRY, KISS, YAGNI)
    - Testing-Standards (TDD, Coverage, E2E, Unit)
    - Security-Standards (OWASP, Auth, DSGVO, Verschluesselung)
    - Performance-Standards (Latency, Throughput, Caching)
    - Documentation-Standards
    - Naming-Conventions
    - Datenbank-Design (Normalisierung, Indizes)
    - DevOps-Patterns (CI/CD, IaC, Container)
    - Observability (Logging, Monitoring, Tracing)
    """
    import httpx

    # DEV-Container Konfiguration (lokal)
    dev_url = "http://127.0.0.1:9303/"
    dev_key = "ob-dev-key-2026"

    # Strukturierte Themen-Kategorien mit spezifischen Suchanfragen
    DEV_TOPICS = [
        {"key": "architecture", "label": "Architektur-Patterns", "queries": ["Architektur Pattern Microservices", "Architektur Monolith Modular", "Event-driven Architecture", "Clean Architecture"]},
        {"key": "api_design", "label": "API-Design-Standards", "queries": ["REST API Design", "OpenAPI Swagger", "GraphQL Standards", "API Versioning"]},
        {"key": "code_standards", "label": "Code-Standards", "queries": ["Clean Code SOLID", "DRY KISS YAGNI", "Naming Conventions", "Code Style Guide"]},
        {"key": "testing", "label": "Testing-Standards", "queries": ["Test-Driven Development TDD", "Unit Test Integration", "Code Coverage", "E2E Testing"]},
        {"key": "security", "label": "Security-Standards", "queries": ["OWASP Top 10", "Authentifizierung OAuth", "DSGVO Compliance", "Encryption Standards"]},
        {"key": "performance", "label": "Performance-Standards", "queries": ["Performance Latency Throughput", "Caching Strategy", "Database Optimization", "Load Balancing"]},
        {"key": "documentation", "label": "Documentation-Standards", "queries": ["Technical Documentation", "API Documentation", "README Standards", "ADR Architecture Decision"]},
        {"key": "database", "label": "Datenbank-Design", "queries": ["Database Normalization", "SQL Index Strategy", "NoSQL Design", "Migration Strategy"]},
        {"key": "devops", "label": "DevOps-Patterns", "queries": ["CI CD Pipeline", "Docker Container", "Infrastructure as Code", "GitOps"]},
        {"key": "observability", "label": "Observability", "queries": ["Logging Standards", "Monitoring Metrics", "Tracing OpenTelemetry", "Alerting Strategy"]},
    ]

    thoughts_by_topic: dict = {t["key"]: [] for t in DEV_TOPICS}
    all_thoughts: list[dict] = []
    errors: list[str] = []
    queries_executed = 0

    for topic in DEV_TOPICS:
        for query in topic["queries"]:
            queries_executed += 1
            payload = {
                "jsonrpc": "2.0",
                "id": queries_executed,
                "method": "tools/call",
                "params": {
                    "name": "openbrain_search",
                    "arguments": {"query": query, "limit": 3, "threshold": 0.1},
                },
            }
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    r = await client.post(
                        dev_url,
                        json=payload,
                        headers={"Content-Type": "application/json", "x-brain-key": dev_key},
                    )
                if r.status_code != 200:
                    errors.append(f"DEV-Container HTTP {r.status_code} bei Query '{query}'")
                    continue
                data = r.json()
                content = data.get("result", {}).get("content", [])
                if not content:
                    continue
                text = content[0].get("text", "")
                # Parse Format: "[1] [type] [topic] content... (sim:0.4, tags:..., ts:...)"
                for line in text.split("\n"):
                    line = line.strip()
                    if not line or not line.startswith("["):
                        continue
                    m = re.match(r"\[\d+\]\s+\[([^\]]+)\]\s+(?:\[([^\]]+)\]\s+)?(.+?)\s*\(sim:([\d.]+),\s*tags:([^)]+),\s*([^)]+)\)", line)
                    if m:
                        thought = {
                            "thought_type": m.group(1).strip(),
                            "topic": (m.group(2) or "").strip(),
                            "content": m.group(3).strip(),
                            "similarity": float(m.group(4)),
                            "tags": [t.strip() for t in m.group(5).split(",") if t.strip()],
                            "timestamp": m.group(6).strip(),
                            "category_key": topic["key"],
                            "category_label": topic["label"],
                            "matched_query": query,
                        }
                        key = thought["content"][:80]
                        if not any(t["content"][:80] == key for t in all_thoughts):
                            all_thoughts.append(thought)
                            thoughts_by_topic[topic["key"]].append(thought)
            except Exception as e:
                errors.append(f"Exception bei Query '{query}': {type(e).__name__}: {str(e)[:200]}")

    # Sortiere Topics nach Thought-Count
    topics_with_thoughts = []
    for topic in DEV_TOPICS:
        thoughts = thoughts_by_topic[topic["key"]]
        if thoughts:
            topics_with_thoughts.append({
                "key": topic["key"],
                "label": topic["label"],
                "thought_count": len(thoughts),
                "thoughts": thoughts,
            })
    topics_with_thoughts.sort(key=lambda x: x["thought_count"], reverse=True)

    return {
        "source": "OpenBrain DEV (Port 9303)",
        "container": "openbrain-unified-dev",
        "queries_executed": queries_executed,
        "topics_searched": len(DEV_TOPICS),
        "total_thoughts": len(all_thoughts),
        "topics": topics_with_thoughts,
        "thoughts": all_thoughts[:30],
        "errors": errors[:5] if errors else [],
        "config_hint": "Fuer mehr Inhalte: openbrain_capture mit Kategorie-Prefix [Architektur], [Testing], [Security] etc. aufrufen.",
    }


# ─── Triage Processing ──────────────────────────────────────────────

@router.post("/triage/{project_id}/process")
async def process_triage(project_id: str, _user: str = Depends(require_auth)) -> list[dict]:
    tasks = _load_json(KANBAN_DIR / "tasks.json")
    triage = [t for t in tasks if t.get("project_id") == project_id and t.get("status") == "triage"]
    processed = []
    for t in triage:
        # Bug 3 Fix: Status-Setter via Helper (Audit-Pflicht)
        _set_task_status(t, "todo", agent="system", reason="process_triage")
        desc_len = len(t.get("description", ""))
        t["priority"] = 75 if desc_len > 500 else 50 if desc_len > 200 else 25
        t["assigned_role"] = "pi-coder"
        desc = t.get("description", "").lower()
        tools = []
        if any(w in desc for w in ["datei", "file", "read", "lesen"]): tools.append("read")
        if any(w in desc for w in ["schreiben", "write", "erstellen", "create"]): tools.append("write")
        if any(w in desc for w in ["bash", "shell", "terminal"]): tools.append("bash")
        if any(w in desc for w in ["test", "pruefen", "check"]):
            tools.append("bash")
            t["assigned_role"] = "pi-tester"
        t["tools"] = tools or ["auto"]
        t["needs_breakdown"] = desc_len > 800
        t["sub_agent"] = "pi-coder (ollama/gemma4:12b)" if desc_len > 800 else None
        t["review_model"] = "minimax-m3"
        t["updated_at"] = _now()
        processed.append(t)
    _save_json(KANBAN_DIR / "tasks.json", tasks)
    return processed


# ─── Review Task (MiniMax/DeepSeek) ────────────────────────────────

@router.post("/tasks/{task_id}/review")
async def review_task(task_id: str, _user: str = Depends(require_auth)) -> dict:
    tasks = _load_json(KANBAN_DIR / "tasks.json")
    t = next((t for t in tasks if t["id"] == task_id), None)
    if not t:
        raise HTTPException(404, "Task not found")
    # Bug 3 Fix: Status-Setter via Helper (Audit-Pflicht)
    _set_task_status(t, "review", agent="pi-reviewer", reason="review_endpoint")
    t["updated_at"] = _now()
    t["review"] = {
        "review_model": "minimax-m3",
        "fallback_model": "deepseek-v4-flash",
        "reviewer_role": "pi-reviewer",
        "soa_compliance": {"compliant": len(t.get("description", "")) < 1000},
        "timestamp": _now(),
    }
    _save_json(KANBAN_DIR / "tasks.json", tasks)
    return t["review"]


# ─── File I/O ───────────────────────────────────────────────────────

def _ensure_dir():
    KANBAN_DIR.mkdir(parents=True, exist_ok=True)
    REQUIREMENTS_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path, default=None):
    if not path.exists():
        return default or ([] if default is None else default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default or ([] if default is None else default)


def _save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _now():
    return datetime.now().isoformat()


def _id():
    return uuid.uuid4().hex[:12]


# === Bug 3 Fix (Task d63824618a8c): Audit-Pflicht fuer status=done ===
# Diese Helper-Funktionen stellen sicher, dass jeder Status-Wechsel MIT
# History-Eintrag erfolgt. Sie sind der einzige zulaessige Weg, den Task-Status
# zu setzen — direkte `t['status'] = ...` Schreibvorgaenge sind ein Anti-Pattern
# und fuehren zu Audit-Luecken.

def _set_task_status(t: dict, new_status: str, agent: str = "system", reason: str = "", **extra) -> None:
    """Setzt Task-Status MIT pflichtigem History-Eintrag (Bug 3 Fix).

    Verhalten:
    - Idempotent: Wenn old_status == new_status, KEIN Schreibvorgang + KEIN History-Eintrag
    - Pflicht: JEDER Status-Wechsel schreibt einen status_changed History-Eintrag
    - Spezielle Felder je nach Status: done_at, claimed_at, block_reason

    Args:
        t: Task-Dict (wird in-place mutiert)
        new_status: Neuer Status (triage|todo|in_progress|review|block|done|blocked)
        agent: Wer setzt den Status (pi-coder, kanban-operator, system, etc.)
        reason: Optionaler Grund (z.B. fuer block-Status)
        **extra: Weitere Details fuer den History-Eintrag
    """
    old_status = t.get("status")
    if old_status == new_status:
        return  # Idempotent: nichts tun wenn schon gleich
    now = _now()
    # UI-Redesign (Task d3dabcba252c): Phase-Tracking — Dauer der VORHERIGEN Phase
    # berechnen und als phase_completed History-Eintrag festhalten. Wird sowohl
    # fuer Frontend-Phase-Timer als auch fuer retrospektive Auswertungen genutzt.
    old_phase_started = t.get("phase_started_at")
    phase_duration_seconds: int | None = None
    phase_duration_human: str | None = None
    if old_phase_started:
        try:
            start_dt = datetime.fromisoformat(old_phase_started.replace("Z", "+00:00"))
            now_dt = datetime.fromisoformat(now)
            # Falls naive (kein tzinfo), als UTC interpretieren (sicherer Fallback)
            if start_dt.tzinfo is not None and now_dt.tzinfo is None:
                from datetime import timezone
                now_dt = now_dt.replace(tzinfo=timezone.utc)
            elif start_dt.tzinfo is None and now_dt.tzinfo is not None:
                from datetime import timezone
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            phase_duration_seconds = max(0, int((now_dt - start_dt).total_seconds()))
            # Human-readable: Xh Ymin / Ymin / Xs
            h = phase_duration_seconds // 3600
            m = (phase_duration_seconds % 3600) // 60
            s = phase_duration_seconds % 60
            if h > 0:
                phase_duration_human = f"{h}h {m}min"
            elif m > 0:
                phase_duration_human = f"{m}min"
            else:
                phase_duration_human = f"{s}s"
        except (ValueError, TypeError):
            pass
    t["status"] = new_status
    t["updated_at"] = now
    # UI-Redesign (Task d3dabcba252c): Phase-Start der NEUEN Phase setzen
    t["phase_started_at"] = now
    # Status-spezifische Felder
    if new_status == "done":
        t["done_at"] = now
    elif new_status == "in_progress" and not t.get("claimed_at"):
        t["claimed_at"] = now
    elif new_status == "block" and reason:
        t["block_reason"] = reason
    # Pflicht: History-Eintrag (kwargs direkt an _add_history uebergeben,
    # NICHT als 'details=...' wrapper, um Doppel-Verschachtelung zu vermeiden)
    _add_history(
        t, "status_changed", agent=agent,
        **{"from": old_status, "to": new_status, "reason": reason, **extra},
    )
    # UI-Redesign (Task d3dabcba252c): Zusaetzlicher phase_completed History-Eintrag
    # mit Dauer der vorherigen Phase. Wird vom Frontend fuer den Phase-Timer-Backfill
    # genutzt, falls Task-Daten im Nachhinein geladen werden.
    if phase_duration_seconds is not None and old_status is not None:
        _add_history(
            t, "phase_completed", agent=agent,
            **{"from_status": old_status, "to_status": new_status,
               "duration_seconds": phase_duration_seconds,
               "duration_human": phase_duration_human},
        )


def _ensure_minimal_history(t: dict) -> None:
    """Stellt sicher dass jeder Task mindestens 1 History-Eintrag hat (Bug 3 Fix).

    Fuer Legacy-Tasks (z.B. SRS-Migration) ohne History wird ein
    'history_reconstructed' Marker-Eintrag hinzugefuegt und ein
    audit_warning gesetzt. Wird in list_tasks/get_task aufgerufen.
    """
    if not t.get("history"):
        t["history"] = [{
            "ts": t.get("updated_at", _now()),
            "event": "history_reconstructed",
            "agent": "system",
            "details": {
                "note": "Task hatte keine History. Rekonstruiert fuer Audit-Trail (Bug 3 Fix, Task d63824618a8c).",
                "migrated_from": t.get("requirement_ref") or "unknown",
            },
        }]
        # Audit-Warnung setzen (Frontend zeigt '⚠️ Audit-Warnung'-Badge)
        t["audit_warning"] = "no_history_found"


# === Bug 2 Fix (Task d63824618a8c): Haenger-Erkennung ===
def _detect_haenger_tasks(tasks: list, now: datetime | None = None) -> list[dict]:
    """Erkennt Haenger: in_progress ohne agent_pid ODER agent_pid tot (Bug 2 Fix).

    Args:
        tasks: Liste aller Task-Dicts
        now: Optional datetime.now() Override (fuer Tests)

    Returns:
        Liste von Haenger-Tasks mit 'haenger_grund' + 'age_seconds' Annotations.
    """
    if now is None:
        now = datetime.now()
    haenger = []
    for t in tasks:
        if t.get("status") != "in_progress":
            continue
        # Alter pruefen (updated_at > 10 Min)
        try:
            updated_str = t.get("updated_at", "2000-01-01").replace("Z", "+00:00")
            updated_dt = datetime.fromisoformat(updated_str)
            # Falls naive (kein tzinfo), als UTC interpretieren
            if updated_dt.tzinfo is None:
                from datetime import timezone
                updated_dt = updated_dt.replace(tzinfo=timezone.utc)
                now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
            age = (now - updated_dt).total_seconds()
        except (ValueError, TypeError):
            continue
        if age < HAENGER_AGE_SECONDS:
            continue
        # Check 1: kein agent_pid
        if not t.get("agent_pid"):
            haenger.append({**t, "haenger_grund": "no_agent_pid", "age_seconds": int(age)})
            continue
        # Check 2: agent_pid Prozess existiert nicht mehr
        pid = t.get("agent_pid")
        try:
            os.kill(pid, 0)  # Signal 0 = nur pruefen, nicht killen
        except (ProcessLookupError, PermissionError):
            haenger.append({**t, "haenger_grund": "pid_dead", "age_seconds": int(age)})
        except OSError:
            # Andere OS-Errors (z.B. Windows): vorsichtig sein
            haenger.append({**t, "haenger_grund": "pid_check_failed", "age_seconds": int(age)})
    return haenger


def _coerce_prio_int(value, default: int = 50) -> int:
    """Konvertiert priority-Wert robust in int (0..100). String -> default."""
    if isinstance(value, str):
        try:
            return max(0, min(100, int(value)))
        except (TypeError, ValueError):
            return default
    if value is None:
        return default
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return default


def _migrate_task_prio(tasks: list) -> bool:
    """Migration: alle bestehenden Tasks bekommen priority=0 (Initial-Migration).
    Gibt True zurueck, wenn etwas geaendert wurde.
    Logik: Wenn 'priority' fehlt ODER ein String ist, wird 0 gesetzt.
    """
    changed = False
    for t in tasks:
        if "priority" not in t or isinstance(t.get("priority"), str):
            t["priority"] = 0
            changed = True
        else:
            # Numeric clamping
            try:
                p = int(t["priority"])
            except (TypeError, ValueError):
                t["priority"] = 0
                changed = True
                continue
            if p < 0 or p > 100:
                t["priority"] = max(0, min(100, p))
                changed = True
    return changed


# ─── Projekte ──────────────────────────────────────────────────────

@router.get("/projects", response_model=list[Project])
async def list_projects(_user: str = Depends(require_auth)) -> list[Project]:
    _ensure_dir()
    projects = _load_json(KANBAN_DIR / "projects.json")
    return [Project(**p) for p in projects]


@router.post("/projects", response_model=Project)
async def create_project(req: dict, _user: str = Depends(require_auth)) -> Project:
    _ensure_dir()
    projects = _load_json(KANBAN_DIR / "projects.json")
    p = Project(id=_id(), name=req["name"], description=req.get("description", ""),
                created_at=_now(), updated_at=_now())
    projects.append(p.model_dump())
    _save_json(KANBAN_DIR / "projects.json", projects)
    return p


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, _user: str = Depends(require_auth)) -> dict:
    """Loescht ein Projekt inkl. Brainstorming-Log, Tasks, SRS, Validierungen, Implementation."""
    projects = _load_json(KANBAN_DIR / "projects.json")
    proj = next((p for p in projects if p["id"] == project_id), None)
    if not proj:
        raise HTTPException(404, "Project not found")
    # 1. Projekt entfernen
    projects = [p for p in projects if p["id"] != project_id]
    _save_json(KANBAN_DIR / "projects.json", projects)
    # 2. Tasks entfernen
    tasks = _load_json(KANBAN_DIR / "tasks.json")
    tasks = [t for t in tasks if t.get("project_id") != project_id]
    _save_json(KANBAN_DIR / "tasks.json", tasks)
    # 3. SRS-Dateien entfernen
    for f in REQUIREMENTS_DIR.glob(f"{project_id}_*.md"):
        try: f.unlink()
        except Exception: pass
    # 4. Validation-/Completeness-/Quality-Status entfernen
    for fname in ["validations.json", "completeness.json", "quality_clarifications.json", "review_pipelines.json", "implementation.json"]:
        path = KANBAN_DIR / fname
        if path.exists():
            data = _load_json(path, default={})
            if project_id in data:
                del data[project_id]
                _save_json(path, data)
    return {"ok": True, "deleted": project_id, "name": proj["name"]}


# ─── Brainstorming ─────────────────────────────────────────────────

@router.post("/brainstorm/{project_id}")
async def brainstorm(project_id: str, req: dict, _user: str = Depends(require_auth)) -> dict:
    """Brainstorming: User-Input → KI strukturiert + Rueckfragen."""
    _ensure_dir()
    projects = _load_json(KANBAN_DIR / "projects.json")
    proj = next((p for p in projects if p["id"] == project_id), None)
    if not proj:
        raise HTTPException(404, "Project not found")

    user_input = req.get("text", "")
    brain_log = proj.get("brainstorm_log", [])

    # Zaehle existierende User-Turns BEVOR der neue angehaengt wird
    existing_user_turns = [t for t in brain_log if t["role"] == "user"]
    # Index der naechsten Frage: 0 = noch keine Frage beantwortet, 5 = alle beantwortet
    next_question_idx = len(existing_user_turns)

    # User-Turn speichern
    brain_log.append({"role": "user", "text": user_input, "phase": "input", "ts": _now()})

    # KI-Antwort: CEO + CIO konversational
    # Phase 1: CEO stellt 5 Verstaendnisfragen
    # Phase 2: CIO pruft 9 Entwicklungsthemen (Architektur, Tech-Stack, DB, Deployment, Auth, Security, Skalierung, Testing, Backup)
    #           - Themen, die User bereits erwaehnt hat, werden uebersprungen
    #           - Pro CIO-Frage: Frage + Empfehlung des CIO

    # Sammle alle bisherigen User-Texte (inkl. neuem Input) fuer CIO-Heuristik
    # Wichtig: AUCH die Projekt-Description beruecksichtigen, da dort oft schon Tech-Stack etc. steht
    all_user_text = " ".join(
        [proj.get("description", "")] + [t["text"] for t in existing_user_turns] + [user_input]
    ).lower()
    addressed_cio_topics: list[str] = []
    for check in CIO_CHECKS:
        for keyword in check["keywords"]:
            if keyword in all_user_text:
                addressed_cio_topics.append(check["topic"])
                break

    ceo_open = next_question_idx < len(CONVERSATION_QUESTIONS)
    cio_open_count = len(CIO_CHECKS) - len(addressed_cio_topics)

    if next_question_idx == 0:
        # Erste AI-Antwort: Vision bestaetigen + erste CEO-Frage
        assistant_text = (
            f"Ich habe Ihr Projekt '{proj['name']}' verstanden. "
            f"Um die Anforderungen sauber zu erstellen, stelle ich Ihnen jetzt Schritt fuer Schritt Fragen. "
            f"Zunaechst die Geschaeftsseite (CEO), danach technische Aspekte (CIO).\n\n"
            f"Frage 1 von {len(CONVERSATION_QUESTIONS)} (CEO): {CONVERSATION_QUESTIONS[0]}"
        )
        phase = "clarifying"
    elif ceo_open:
        # Naechste CEO-Frage
        assistant_text = (
            f"Danke fuer Ihre Antwort. "
            f"Frage {next_question_idx + 1} von {len(CONVERSATION_QUESTIONS)} (CEO): {CONVERSATION_QUESTIONS[next_question_idx]}"
        )
        phase = "clarifying"
    elif cio_open_count > 0:
        # CEO durch, jetzt CIO: naechstes nicht-adressiertes Thema
        next_cio = None
        for check in CIO_CHECKS:
            if check["topic"] not in addressed_cio_topics:
                next_cio = check
                break
        if next_cio:
            cio_done = len(addressed_cio_topics)
            assistant_text = (
                f"Danke. Die CEO-Geschaeftsfragen sind geklaert. "
                f"Der CIO hat nun zusaetzlich gepruft, welche technischen Vorgaben fuer die Entwicklung noch fehlen.\n\n"
                f"CIO-Thema ({cio_done + 1} von {len(CIO_CHECKS)} behandelten Themen): {next_cio['topic']}\n"
                f"Frage: {next_cio['question']}\n\n"
                f"{next_cio['recommendation']}"
            )
            phase = "clarifying"
        else:
            # Sollte nicht passieren (cio_open_count > 0)
            assistant_text = "Alle CIO-Themen behandelt. Sie koennen jetzt das Anforderungsdokument generieren."
            phase = "structuring"
    else:
        # Alle CEO- und CIO-Themen abgeschlossen
        assistant_text = (
            f"Ich habe nun alle {len(CONVERSATION_QUESTIONS)} CEO-Geschaeftsfragen und alle relevanten CIO-Entwicklungsthemen geklaert. "
            f"Sie koennen jetzt das Anforderungsdokument erstellen lassen. Klicken Sie dazu auf 'Generate Requirements' oder zuerst auf 'Review' fuer eine Qualitaetspruefung."
        )
        phase = "structuring"

    brain_log.append({"role": "assistant", "text": assistant_text, "phase": phase, "ts": _now()})
    proj["brainstorm_log"] = brain_log
    _save_json(KANBAN_DIR / "projects.json", projects)

    # Requirements koennen generiert werden sobald alle offenen Themen geklaert sind
    can_generate = (not ceo_open) and (cio_open_count == 0)

    return {
        "assistant_text": assistant_text,
        "phase": phase,
        "can_generate_requirements": can_generate,
        "log": brain_log[-4:],
    }


@router.get("/brainstorm/{project_id}/log")
async def get_brainstorm_log(project_id: str, _user: str = Depends(require_auth)) -> list[dict]:
    projects = _load_json(KANBAN_DIR / "projects.json")
    proj = next((p for p in projects if p["id"] == project_id), None)
    if not proj:
        raise HTTPException(404, "Project not found")
    return proj.get("brainstorm_log", [])


# ─── Anforderungsdokument ──────────────────────────────────────────

@router.post("/requirements/generate/{project_id}")
async def generate_requirements(project_id: str, _user: str = Depends(require_auth)) -> dict:
    """Generiert Anforderungsdokument aus Brainstorming-Log."""
    _ensure_dir()
    projects = _load_json(KANBAN_DIR / "projects.json")
    proj = next((p for p in projects if p["id"] == project_id), None)
    if not proj:
        raise HTTPException(404, "Project not found")

    brain_log = proj.get("brainstorm_log", [])
    user_inputs = [t["text"] for t in brain_log if t["role"] == "user"]
    ai_msgs = [t["text"] for t in brain_log if t["role"] == "assistant"]

    # Strukturiertes Parsing der Brainstorming-Antworten
    # CEO-Antworten: die ersten 5 User-Inputs (nach der initialen Vision)
    # CIO-Antworten: alle folgenden
    vision = user_inputs[0] if user_inputs else (proj.get("description") or "")
    ceo_answers = user_inputs[1:1+len(CONVERSATION_QUESTIONS)]
    cio_answers = user_inputs[1+len(CONVERSATION_QUESTIONS):]

    # Welche CIO-Themen wurden explizit beantwortet (vs. aus Description uebersprungen)
    all_text_lower = (proj.get("description", "") + " " + " ".join(user_inputs)).lower()
    addressed_cio = []
    for check in CIO_CHECKS:
        for kw in check["keywords"]:
            if kw in all_text_lower:
                addressed_cio.append(check["topic"])
                break
    cio_topic_to_answer = {}
    cio_answers_iter = iter(cio_answers)
    for check in CIO_CHECKS:
        if check["topic"] not in addressed_cio:
            try:
                cio_topic_to_answer[check["topic"]] = next(cio_answers_iter)
            except StopIteration:
                break

    # === SRS-Generierung nach ISO/IEC/IEEE 29148:2018 ===
    id_counters: dict[str, int] = {"FR": 0, "NFR": 0, "IF": 0, "DC": 0}
    def next_id(prefix: str) -> str:
        id_counters[prefix] = id_counters.get(prefix, 0) + 1
        return f"{prefix}-{id_counters[prefix]:03d}"

    fr_list: list[str] = []    # Functional Requirements
    nfr_list: list[str] = []   # Non-Functional Requirements
    ifr_list: list[str] = []   # Interface Requirements
    dcr_list: list[str] = []   # Design Constraints

    # === Functional Requirements aus Vision + CEO-Antworten ableiten ===
    # FR-VISION: das System soll die Vision umsetzen
    fr_id = next_id("FR")
    fr_list.append(
        f"### {fr_id}: System-Erstellung\n\n"
        f"**Quelle:** Brainstorming-Vision\n\n"
        f"**Requirement:** Das System '{proj['name']}' soll die folgende fachliche Vision umsetzen: {vision or 'Vision aus Brainstorming'}.\n\n"
        f"**Verifikation:** Anhand eines Akzeptanztests, der die genannten Anwendungsfaelle ausfuehrbar macht."
    )

    # FR-USER: Zielgruppe beruecksichtigen
    if ceo_answers and len(ceo_answers) >= 1:
        fr_id = next_id("FR")
        fr_list.append(
            f"### {fr_id}: Zielgruppen-Gerechte Bedienung\n\n"
            f"**Quelle:** CEO-Antwort 1 (Zielgruppe)\n\n"
            f"**Requirement:** Das System soll seine Benutzeroberflaeche und Funktionen auf die folgende Zielgruppe ausrichten: {ceo_answers[0]}.\n\n"
            f"**Verifikation:** Usability-Test mit Vertretern der Zielgruppe; Akzeptanz der Bedienung ohne Schulung."
        )

    # FR-PROBLEM: Problem loesen
    if ceo_answers and len(ceo_answers) >= 2:
        fr_id = next_id("FR")
        fr_list.append(
            f"### {fr_id}: Problemloesung\n\n"
            f"**Quelle:** CEO-Antwort 2 (Problem)\n\n"
            f"**Requirement:** Das System soll das folgende Problem nachweislich loesen: {ceo_answers[1]}.\n\n"
            f"**Verifikation:** Pilot-Einsatz mit Vergleich Vorher/Nachher fuer mindestens 3 Anwender."
        )

    # FR-TIMELINE: Budget/Zeit-Rahmen
    if ceo_answers and len(ceo_answers) >= 3:
        fr_id = next_id("FR")
        fr_list.append(
            f"### {fr_id}: Lieferzeitraum\n\n"
            f"**Quelle:** CEO-Antwort 3 (Zeit/Budget)\n\n"
            f"**Requirement:** Die Auslieferung des Systems soll im folgenden Zeit- und Budgetrahmen erfolgen: {ceo_answers[2]}.\n\n"
            f"**Verifikation:** Projektplan mit Meilensteinen, der die Vorgaben abbildet."
        )

    # FR-SUCCESS: Erfolgsmessung
    if ceo_answers and len(ceo_answers) >= 4:
        fr_id = next_id("FR")
        fr_list.append(
            f"### {fr_id}: Erfolgsmessung\n\n"
            f"**Quelle:** CEO-Antwort 4 (Erfolgsmessung)\n\n"
            f"**Requirement:** Das System soll den Erfolg anhand folgender Metriken nachweisbar machen: {ceo_answers[3]}.\n\n"
            f"**Verifikation:** KPI-Dashboard mit den genannten Metriken."
        )

    # FR-DEPENDENCIES: Abhaengigkeiten
    if ceo_answers and len(ceo_answers) >= 5:
        fr_id = next_id("FR")
        fr_list.append(
            f"### {fr_id}: System-Abhaengigkeiten\n\n"
            f"**Quelle:** CEO-Antwort 5 (Abhaengigkeiten)\n\n"
            f"**Requirement:** Das System soll die folgenden externen Abhaengigkeiten beruecksichtigen: {ceo_answers[4]}.\n\n"
            f"**Verifikation:** Integrations-Test mit den genannten externen Systemen/Diensten."
        )

    # === Non-Functional Requirements aus CIO-Antworten ===
    # Performance / Skalierung
    if "Skalierung & Last" in cio_topic_to_answer:
        nfr_id = next_id("NFR")
        nfr_list.append(
            f"### {nfr_id}: Performance- und Skalierungsanforderungen\n\n"
            f"**Quelle:** CIO-Antwort (Skalierung & Last)\n\n"
            f"**Requirement:** Das System soll die folgenden Last- und Performance-Vorgaben erfuellen: {cio_topic_to_answer['Skalierung & Last']}.\n\n"
            f"**Verifikation:** Lasttest mit der angegebenen Anzahl gleichzeitiger Nutzer; Antwortzeiten unter 1 Sekunde fuer 95% der Anfragen.\n\n"
            f"**Empfehlung des CIO:** {_clean(CIO_CHECKS[6]['recommendation'])}"
        )
    else:
        # Default: Mindestens
        nfr_id = next_id("NFR")
        nfr_list.append(
            f"### {nfr_id}: Performance- und Skalierungsanforderungen\n\n"
            f"**Quelle:** Default-Anforderung (CIO-Empfehlung)\n\n"
            f"**Requirement:** Das System soll fuer mindestens 1.000 gleichzeitige Benutzer ausgelegt sein und 95% aller Anfragen in unter 1 Sekunde beantworten.\n\n"
            f"**Verifikation:** Lasttest mit 1.000 virtuellen Nutzern (z.B. Locust, k6); Antwortzeit-Messung; horizontal skalierbar ohne Datenverlust.\n\n"
            f"**Empfehlung des CIO:** {_clean(CIO_CHECKS[6]['recommendation'])}"
        )

    # Security
    if "Sicherheit" in cio_topic_to_answer:
        nfr_id = next_id("NFR")
        nfr_list.append(
            f"### {nfr_id}: Sicherheitsanforderungen\n\n"
            f"**Quelle:** CIO-Antwort (Sicherheit)\n\n"
            f"**Requirement:** Das System soll die folgenden Sicherheitsanforderungen erfuellen: {cio_topic_to_answer['Sicherheit']}.\n\n"
            f"**Verifikation:** Security-Audit, Penetrationstest vor Go-Live, regelmaessige Dependency-Updates, Audit-Log fuer schreibende Aktionen.\n\n"
            f"**Empfehlung des CIO:** {_clean(CIO_CHECKS[5]['recommendation'])}"
        )
    else:
        nfr_id = next_id("NFR")
        nfr_list.append(
            f"### {nfr_id}: Sicherheitsanforderungen\n\n"
            f"**Quelle:** Default-Anforderung (CIO-Empfehlung)\n\n"
            f"**Requirement:** Das System soll HTTPS ausschliesslich verwenden, Passwoerter mit Argon2id verschluesseln, Audit-Log fuer alle schreibenden Aktionen fuehren, Rate-Limiting (z.B. 100 Anfragen/Minute/IP) durchsetzen und regelmaessige Dependency-Updates einspielen.\n\n"
            f"**Verifikation:** TLS-Check, Code-Audit auf Hartkodierte Secrets, OWASP-Top-10-Pruefung.\n\n"
            f"**Empfehlung des CIO:** {_clean(CIO_CHECKS[5]['recommendation'])}"
        )

    # Testing
    if "Testing & Qualitaet" in cio_topic_to_answer:
        nfr_id = next_id("NFR")
        nfr_list.append(
            f"### {nfr_id}: Test- und Qualitaetsanforderungen\n\n"
            f"**Quelle:** CIO-Antwort (Testing & Qualitaet)\n\n"
            f"**Requirement:** Das System soll die folgenden Test- und Qualitaetsvorgaben erfuellen: {cio_topic_to_answer['Testing & Qualitaet']}.\n\n"
            f"**Verifikation:** Coverage-Report, CI/CD-Pipeline, automatische Test-Ausfuehrung bei jedem Commit.\n\n"
            f"**Empfehlung des CIO:** {_clean(CIO_CHECKS[7]['recommendation'])}"
        )
    else:
        nfr_id = next_id("NFR")
        nfr_list.append(
            f"### {nfr_id}: Test- und Qualitaetsanforderungen\n\n"
            f"**Quelle:** Default-Anforderung (CIO-Empfehlung)\n\n"
            f"**Requirement:** Das System soll eine Test-Coverage von mindestens 70% (90% fuer Geschaeftslogik) aufweisen. CI/CD-Pipeline soll alle Tests automatisch bei jedem Commit ausfuehren.\n\n"
            f"**Verifikation:** Coverage-Report (pytest-cov/jest), CI-Log, Build-Status-Badge.\n\n"
            f"**Empfehlung des CIO:** {_clean(CIO_CHECKS[7]['recommendation'])}"
        )

    # Backup
    if "Backup & Recovery" in cio_topic_to_answer:
        nfr_id = next_id("NFR")
        nfr_list.append(
            f"### {nfr_id}: Backup- und Recovery-Anforderungen\n\n"
            f"**Quelle:** CIO-Antwort (Backup & Recovery)\n\n"
            f"**Requirement:** Das System soll die folgenden Backup- und Recovery-Vorgaben erfuellen: {cio_topic_to_answer['Backup & Recovery']}.\n\n"
            f"**Verifikation:** Disaster-Recovery-Drill mindestens quartalsweise, dokumentierte RPO/RTO-Werte.\n\n"
            f"**Empfehlung des CIO:** {_clean(CIO_CHECKS[8]['recommendation'])}"
        )
    else:
        nfr_id = next_id("NFR")
        nfr_list.append(
            f"### {nfr_id}: Backup- und Recovery-Anforderungen\n\n"
            f"**Quelle:** Default-Anforderung (CIO-Empfehlung)\n\n"
            f"**Requirement:** Das System soll taegliche automatisierte Backups erstellen (3-2-1-Regel: 3 Kopien, 2 Medien, 1 off-site) und ein Recovery innerhalb von 4 Stunden (RTO) mit max. 24 Stunden Datenverlust (RPO) ermoeglichen.\n\n"
            f"**Verifikation:** Backup-Log, quartalsweiser Restore-Test, dokumentiertes Runbook.\n\n"
            f"**Empfehlung des CIO:** {_clean(CIO_CHECKS[8]['recommendation'])}"
        )

    # Usability
    nfr_id = next_id("NFR")
    nfr_list.append(
        f"### {nfr_id}: Usability und Bedienbarkeit\n\n"
        f"**Quelle:** Abgeleitet aus Zielgruppe\n\n"
        f"**Requirement:** Die Benutzeroberflaeche soll ohne vorherige Schulung fuer mindestens 80% der Standardaufgaben verwendbar sein. Haeufige Aktionen sollen in maximal 3 Klicks erreichbar sein.\n\n"
        f"**Verifikation:** Usability-Test mit 5 Vertretern der Zielgruppe; Task-Completion-Rate >= 80% ohne Hilfestellung."
    )

    # Maintainability
    nfr_id = next_id("NFR")
    nfr_list.append(
        f"### {nfr_id}: Wartbarkeit und Erweiterbarkeit\n\n"
        f"**Quelle:** Default-Anforderung (Best Practice)\n\n"
        f"**Requirement:** Der Quellcode soll modular, dokumentiert und nach Clean-Architecture-Prinzipien strukturiert sein. Aenderungen sollen ohne Refactoring des gesamten Systems moeglich sein.\n\n"
        f"**Verifikation:** Code-Review, Modul-Abhaengigkeits-Graph (keine zyklischen Abhaengigkeiten), Dokumentations-Coverage der oeffentlichen API >= 90%."
    )

    # === Interface Requirements aus CIO-Antworten ===
    # User Interface
    ifr_id = next_id("IF")
    ifr_list.append(
        f"### {ifr_id}: Benutzeroberflaeche (Web)\n\n"
        f"**Quelle:** Default-Anforderung\n\n"
        f"**Requirement:** Die Anwendung soll eine Web-Oberflaeche bereitstellen, die in aktuellen Versionen von Chrome, Firefox, Edge und Safari lauffaehig ist. Mobile Browsers (iOS Safari, Android Chrome) sollen ebenfalls unterstuetzt werden.\n\n"
        f"**Verifikation:** Cross-Browser-Test mit BrowserStack, Responsive-Design-Pruefung in Breakpoints 320px, 768px, 1024px, 1920px."
    )

    # Tech-Stack Interface
    if "Tech-Stack" in cio_topic_to_answer or any(kw in all_text_lower for kw in ["python","javascript","typescript","react","vue","node"]):
        ifr_id = next_id("IF")
        tech_text = cio_topic_to_answer.get("Tech-Stack", "Aus Projektbeschreibung abgeleitet")
        ifr_list.append(
            f"### {ifr_id}: Technologie-Stack\n\n"
            f"**Quelle:** CIO-Antwort oder Projektbeschreibung\n\n"
            f"**Requirement:** Das System soll mit dem folgenden Technologie-Stack implementiert werden: {tech_text}.\n\n"
            f"**Verifikation:** Repository enthaelt die genannten Frameworks/Sprachen in den Konfigurationsdateien (package.json, pyproject.toml, etc.).\n\n"
            f"**Empfehlung des CIO:** {_clean(CIO_CHECKS[1]['recommendation'])}"
        )

    # Database Interface
    if "Datenbank" in cio_topic_to_answer or any(kw in all_text_lower for kw in ["postgres","mysql","mongo","redis","sql"]):
        ifr_id = next_id("IF")
        db_text = cio_topic_to_answer.get("Datenbank", "Aus Projektbeschreibung abgeleitet")
        ifr_list.append(
            f"### {ifr_id}: Datenbank-Schnittstelle\n\n"
            f"**Quelle:** CIO-Antwort oder Projektbeschreibung\n\n"
            f"**Requirement:** Das System soll die folgende Datenbank verwenden: {db_text}. Alle persistenten Daten sollen in dieser Datenbank gespeichert werden.\n\n"
            f"**Verifikation:** Datenbank-Connector in den Dependencies dokumentiert; Migration-Scripts vorhanden.\n\n"
            f"**Empfehlung des CIO:** {_clean(CIO_CHECKS[2]['recommendation'])}"
        )

    # Deployment Interface
    if "Deployment & Hosting" in cio_topic_to_answer or any(kw in all_text_lower for kw in ["docker","kubernetes","aws","azure","cloud"]):
        ifr_id = next_id("IF")
        dep_text = cio_topic_to_answer.get("Deployment & Hosting", "Aus Projektbeschreibung abgeleitet")
        ifr_list.append(
            f"### {ifr_id}: Deployment-Schnittstelle\n\n"
            f"**Quelle:** CIO-Antwort oder Projektbeschreibung\n\n"
            f"**Requirement:** Das System soll auf der folgenden Infrastruktur deployt werden: {dep_text}. Deployment soll automatisiert ueber CI/CD erfolgen.\n\n"
            f"**Verifikation:** Dockerfile, docker-compose.yml oder Kubernetes-Manifeste im Repository; CI/CD-Pipeline fuehrt Deployment automatisch aus.\n\n"
            f"**Empfehlung des CIO:** {_clean(CIO_CHECKS[3]['recommendation'])}"
        )

    # Auth Interface
    if "Authentifizierung" in cio_topic_to_answer or any(kw in all_text_lower for kw in ["authentifizierung","oauth","login","auth","jwt"]):
        ifr_id = next_id("IF")
        auth_text = cio_topic_to_answer.get("Authentifizierung", "Aus Projektbeschreibung abgeleitet")
        ifr_list.append(
            f"### {ifr_id}: Authentifizierung-Schnittstelle\n\n"
            f"**Quelle:** CIO-Antwort oder Projektbeschreibung\n\n"
            f"**Requirement:** Das System soll die folgenden Authentifizierungs-Mechanismen unterstuetzen: {auth_text}. Session-Tokens sollen nach Industriestandard verschluesselt und zeitlich begrenzt sein.\n\n"
            f"**Verifikation:** Auth-Provider konfiguriert, Login-Flow getestet, Token-Expiration geprueft.\n\n"
            f"**Empfehlung des CIO:** {_clean(CIO_CHECKS[4]['recommendation'])}"
        )

    # API Interface (default)
    ifr_id = next_id("IF")
    ifr_list.append(
        f"### {ifr_id}: REST-API\n\n"
        f"**Quelle:** Default-Anforderung (Best Practice)\n\n"
        f"**Requirement:** Das System soll eine versionierte REST-API (z.B. /api/v1/) anbieten, die JSON als Datenformat verwendet. OpenAPI-Spezifikation soll verfuegbar sein.\n\n"
        f"**Verifikation:** OpenAPI-Dokument unter /openapi.json erreichbar; Einhaltung der HTTP-Status-Code-Konventionen (200, 201, 400, 401, 403, 404, 500)."
    )

    # === Design Constraints (immer) ===
    dcr_id = next_id("DC")
    dcr_list.append(
        f"### {dcr_id}: Programmiersprache und Versionen\n\n"
        f"**Quelle:** Abgeleitet aus Tech-Stack\n\n"
        f"**Requirement:** Die Implementierung soll in den gewaehlten Programmiersprachen in unterstuetzten LTS-Versionen erfolgen (Python 3.11+, Node 20+, etc.)."
    )
    dcr_id = next_id("DC")
    dcr_list.append(
        f"### {dcr_id}: Lizenz\n\n"
        f"**Quelle:** Default\n\n"
        f"**Requirement:** Der Quellcode soll unter einer Open-Source-Lizenz stehen (z.B. MIT, Apache 2.0, AGPL-3.0) und Drittabhaengigkeiten sollen lizenzkonform verwendet werden."
    )

    # === SRS-Dokument zusammenbauen ===
    today = _now()
    project_id_short = project_id[:8]

    # 1. Introduction
    intro = f"""# Software Requirements Specification

**Projekt:** {proj['name']}
**Dokument-ID:** SRS-{project_id_short}-v1.0
**Version:** 1.0.0
**Status:** Draft
**Erstellt:** {today}
**Standard:** ISO/IEC/IEEE 29148:2018

---

## Revision History

| Version | Datum | Autor | Aenderung |
|---------|-------|-------|-----------|
| 1.0.0 | {today} | CEO-digital (generiert aus Brainstorming) | Initial-Version basierend auf Brainstorming-Output |

---

## Inhaltsverzeichnis

1. [Introduction](#1-introduction)
   1.1 [Purpose](#11-purpose)
   1.2 [Scope](#12-scope)
   1.3 [Definitions, Acronyms, Abbreviations](#13-definitions-acronyms-abbreviations)
   1.4 [References](#14-references)
   1.5 [Overview](#15-overview)
2. [Overall Description](#2-overall-description)
   2.1 [Product Perspective](#21-product-perspective)
   2.2 [Product Functions](#22-product-functions)
   2.3 [User Characteristics](#23-user-characteristics)
   2.4 [Limitations and Constraints](#24-limitations-and-constraints)
   2.5 [Assumptions and Dependencies](#25-assumptions-and-dependencies)
3. [Specific Requirements](#3-specific-requirements)
   3.1 [External Interface Requirements](#31-external-interface-requirements)
   3.2 [Functional Requirements](#32-functional-requirements)
   3.3 [Non-Functional Requirements](#33-non-functional-requirements)
   3.4 [Design Constraints](#34-design-constraints)
4. [Verification](#4-verification)
5. [Supporting Information](#5-supporting-information)

---

## 1. Introduction

### 1.1 Purpose

Dieses Software Requirements Specification (SRS)-Dokument beschreibt die funktionalen und nicht-funktionalen Anforderungen an das Projekt **{proj['name']}**. Es dient als vertragliche Grundlage zwischen Auftraggeber und Entwicklungsteam, als Basis fuer Kostenschaetzungen, als Referenz fuer Tests und Verifikation sowie als Kommunikationsmittel fuer alle Stakeholder.

### 1.2 Scope

**Produktname:** {proj['name']}
**Beschreibung:** {proj.get('description') or vision or 'Beschreibung aus dem Brainstorming'}

**Im Scope:**
- Umsetzung der im Brainstorming definierten Geschaeftsanforderungen
- Beruecksichtigung der vom CIO empfohlenen technischen Standards
- Verifikation durch automatisierte Tests

**Ausserhalb des Scopes:**
- Hardware-Beschaffung (sofern nicht in den Anforderungen erwaehnt)
- Schulung der Endnutzer (separates Schulungskonzept erforderlich)
- Migration von Bestandsdaten (separates Migrationsprojekt)

### 1.3 Definitions, Acronyms, Abbreviations

| Begriff | Erklaerung |
|---------|------------|
| SRS | Software Requirements Specification |
| FR | Functional Requirement (Funktionale Anforderung) |
| NFR | Non-Functional Requirement (Nicht-funktionale Anforderung) |
| IF | Interface Requirement |
| DC | Design Constraint (Design-Einschraenkung) |
| MVP | Minimum Viable Product |
| RPO | Recovery Point Objective (maximaler Datenverlust) |
| RTO | Recovery Time Objective (maximale Ausfallzeit) |
| TBD | To Be Determined (noch zu klaeren) |
| API | Application Programming Interface |

### 1.4 References

- Brainstorming-Protokoll des Projekts (Quelle aller Anforderungen)
- IEEE Recommended Practice for Software Requirements Specifications (IEEE 830-1998)
- ISO/IEC/IEEE 29148:2018 - Systems and software engineering - Life cycle processes - Requirements engineering
- RFC 7231 - HTTP/1.1 Semantics and Content (fuer REST-API-Design)

### 1.5 Overview

Kapitel 2 beschreibt das Produkt im Gesamtkontext. Kapitel 3 enthaelt die spezifischen Anforderungen, gegliedert in externe Schnittstellen, funktionale Anforderungen, nicht-funktionale Anforderungen und Design-Einschraenkungen. Kapitel 4 beschreibt die Verifikationsstrategie. Kapitel 5 enthaelt zusaetzliche Informationen.

---

## 2. Overall Description

### 2.1 Product Perspective

Das System **{proj['name']}** wird als eigenstaendige Anwendung entwickelt. Es ist eingebettet in die bestehende IT-Landschaft des Auftraggebers und interagiert mit den im Brainstorming identifizierten externen Systemen.

### 2.2 Product Functions

Die Hauptfunktionen des Systems ergeben sich aus der Brainstorming-Phase. Eine detaillierte Auflistung findet sich in [Abschnitt 3.2 Functional Requirements](#32-functional-requirements). Auf hoher Ebene umfasst das System:

"""
    # Funktionen-Uebersicht generieren
    fn_list = ["- Umsetzung der fachlichen Vision aus dem Brainstorming"]
    if ceo_answers and len(ceo_answers) >= 1:
        fn_list.append(f"- Zielgruppengerechte Bedienung fuer: {ceo_answers[0][:100]}")
    if ceo_answers and len(ceo_answers) >= 2:
        fn_list.append(f"- Loesung des Problems: {ceo_answers[1][:100]}")
    intro += "\n".join(fn_list) + "\n\n"

    intro += f"""### 2.3 User Characteristics

**Zielgruppe:** {ceo_answers[0] if ceo_answers and len(ceo_answers) >= 1 else 'Nicht spezifiziert'}

Die Benutzer werden als fachliche Anwender ohne tiefere IT-Kenntnisse charakterisiert. Die Bedienung soll daher selbsterklaerend und ohne Schulungsaufwand moeglich sein.

### 2.4 Limitations and Constraints

Die folgenden Einschraenkungen wurden durch den CIO identifiziert:
"""
    if "Architektur" in addressed_cio:
        intro += f"- **Architektur:** Aus der Projektvision abgeleitet\n"
    else:
        intro += f"- **Architektur:** Empfohlen: {_clean(CIO_CHECKS[0]['recommendation'])}\n"

    intro += f"""
### 2.5 Assumptions and Dependencies

**Annahmen:**
- Das Entwicklungsteam hat Erfahrung mit dem gewaehlten Tech-Stack
- Die erforderliche Infrastruktur (Cloud-Account, CI/CD-Pipeline) steht zur Verfuegung
- Die Stakeholder stehen fuer Rueckfragen zur Verfuegung

**Abhaengigkeiten:**
{('- ' + chr(10).join(ceo_answers[4:5])) if (ceo_answers and len(ceo_answers) >= 5) else '- Keine spezifischen externen Abhaengigkeiten identifiziert'}

---

## 3. Specific Requirements

### 3.1 External Interface Requirements

"""

    ifr_section = "\n".join(ifr_list) + "\n\n---\n\n"

    fr_section = "### 3.2 Functional Requirements\n\n" + "\n\n".join(fr_list) + "\n\n---\n\n"

    nfr_section = "### 3.3 Non-Functional Requirements\n\n" + "\n\n".join(nfr_list) + "\n\n---\n\n"

    dcr_section = "### 3.4 Design Constraints\n\n" + "\n\n".join(dcr_list) + "\n\n---\n\n"

    verification = f"""## 4. Verification

### 4.1 Verifikationsstrategie

Fuer jede Anforderung in Kapitel 3 ist eine Verifikationsmethode definiert. Diese wird in einer separaten Test-Spezifikation (Test-Spec) detailliert.

### 4.2 Verifikationsmethoden

- **Inspection (I):** Manuelle Pruefung (Code-Review, Dokumenten-Review)
- **Demonstration (D):** Funktionaler Test durch Vorfuehrung
- **Analysis (A):** Statische Analyse (z.B. Lasttest, Security-Scan, Coverage-Report)
- **Test (T):** Automatisierter Test (Unit, Integration, E2E)

### 4.3 Verifikationsmatrix

| Requirement-ID | Verifikationsmethode | Test-Art | Status |
|----------------|---------------------|----------|--------|
"""

    # Saubere Verifikationsmatrix aus den generierten Listen
    for i, _ in enumerate(fr_list, 1):
        verification += f"| FR-{i:03d} | Test + Demonstration | Funktional | Offen |\n"
    for i, _ in enumerate(nfr_list, 1):
        verification += f"| NFR-{i:03d} | Analysis | Nicht-funktional | Offen |\n"
    for i, _ in enumerate(ifr_list, 1):
        verification += f"| IF-{i:03d} | Inspection | Schnittstelle | Offen |\n"
    for i, _ in enumerate(dcr_list, 1):
        verification += f"| DC-{i:03d} | Inspection | Design | Offen |\n"

    # Hinweis: Korrekter Ansatz waere die ID direkt zu parsen, aber dies ist eine
    # pragmatische Alternative fuer die Verifikationsmatrix.

    supporting = f"""
---

## 5. Supporting Information

### 5.1 Anforderungs-Herkunft (Traceability)

Jede Anforderung in Kapitel 3 ist auf die entsprechende Brainstorming-Antwort zurueckzufuehren. Diese Traceability ermoeglicht es, bei Aenderungen am Brainstorming die betroffenen Requirements zu identifizieren.

### 5.2 Aenderungshistorie

Aenderungen an diesem Dokument sollen in der [Revision History](#revision-history) am Anfang erfasst werden. Jede Aenderung erfordert eine neue Versionsnummer (Semantic Versioning: Major.Minor.Patch).

### 5.3 Glossar

| Begriff | Erklaerung |
|---------|------------|
| Stakeholder | Alle Personen oder Organisationen, die ein Interesse am System haben |
| Verifikation | Pruefung, ob das System die Anforderungen erfuellt |
| Validierung | Pruefung, ob das System die Nutzerbeduerfnisse erfuellt |
| Acceptance Test | Test durch den Auftraggeber zur Abnahme |

---

**Ende des Dokuments**

*Dieses Dokument wurde automatisch auf Basis des Brainstormings generiert. Es entbindet den Auftraggeber nicht von der Pflicht, die Anforderungen kritisch zu pruefen und ggf. zu ergaenzen.*
"""

    doc_content = intro + ifr_section + fr_section + nfr_section + dcr_section + verification + supporting

    # Speichern
    req_file = REQUIREMENTS_DIR / f"{project_id}_v1.md"
    req_file.write_text(doc_content, encoding="utf-8")

    proj["requirements_file"] = str(req_file)
    _save_json(KANBAN_DIR / "projects.json", projects)

    return {"ok": True, "file": str(req_file), "content": doc_content}


# Helper-Funktion fuer saubere Empfehlungs-Texte (im generate_requirements verwendet)
def _clean(text: str) -> str:
    """Bereinigt Empfehlungs-Text: nimmt nur den ersten Satz."""
    if not text:
        return ""
    t = text.replace("Empfehlung des CIO:", "").strip()
    # Nur bis zum ersten Punkt nehmen
    parts = t.split(".")
    return (parts[0].strip() + ".") if parts else t

    # Speichern
    req_file = REQUIREMENTS_DIR / f"{project_id}_v1.md"
    req_file.write_text(doc_content, encoding="utf-8")

    proj["requirements_file"] = str(req_file)
    _save_json(KANBAN_DIR / "projects.json", projects)

    return {"ok": True, "file": str(req_file), "content": doc_content}


@router.get("/requirements/{project_id}")
async def get_requirements(project_id: str, _user: str = Depends(require_auth)) -> dict:
    """Liest das Anforderungsdokument."""
    _ensure_dir()
    files = sorted(REQUIREMENTS_DIR.glob(f"{project_id}_*.md"))
    if not files:
        raise HTTPException(404, "No requirements document found")
    latest = files[-1]
    return {
        "project_id": project_id,
        "file": str(latest),
        "content": latest.read_text(encoding="utf-8", errors="ignore"),
    }


@router.get("/requirements/{project_id}/versions")
async def list_requirement_versions(project_id: str, _user: str = Depends(require_auth)) -> list[dict]:
    """Listet alle gespeicherten Versionen des SRS auf."""
    files = sorted(REQUIREMENTS_DIR.glob(f"{project_id}_*.md"), reverse=True)
    out = []
    for f in files:
        stat = f.stat()
        # Extrahiere Versionsnummer aus Filename
        m = re.match(rf"{re.escape(project_id)}_v(\d+)(?:\.(\d+))?\.md", f.name)
        version = f"{m.group(1)}.{m.group(2) or 0}" if m else "1.0"
        out.append({
            "file": f.name,
            "path": str(f),
            "version": version,
            "size_bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return out


@router.get("/requirements/{project_id}/diff")
async def diff_requirements(project_id: str, from_version: str = "v1", to_version: str = "v2", _user: str = Depends(require_auth)) -> dict:
    """Vergleicht zwei Versionen des SRS (line-by-line diff)."""
    files = sorted(REQUIREMENTS_DIR.glob(f"{project_id}_*.md"))
    if len(files) < 2:
        raise HTTPException(400, "Mindestens 2 Versionen noetig fuer Diff")
    # Vereinfachung: nehme erste und letzte Datei
    from_file = files[0]
    to_file = files[-1]
    from_text = from_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    to_text = to_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    import difflib
    diff = list(difflib.unified_diff(from_text, to_text, lineterm="", fromfile=from_file.name, tofile=to_file.name))
    return {
        "from": str(from_file),
        "to": str(to_file),
        "diff": "\n".join(diff),
        "from_lines": len(from_text),
        "to_lines": len(to_text),
        "added": sum(1 for l in diff if l.startswith("+") and not l.startswith("+++")),
        "removed": sum(1 for l in diff if l.startswith("-") and not l.startswith("---")),
    }


@router.get("/requirements/{project_id}/export")
async def export_requirements(project_id: str, format: str = "md", _user: str = Depends(require_auth)) -> dict:
    """Exportiert das SRS in verschiedenen Formaten (md, html, json, txt)."""
    from fastapi.responses import Response
    files = sorted(REQUIREMENTS_DIR.glob(f"{project_id}_*.md"))
    if not files:
        raise HTTPException(404, "No requirements document found")
    latest = files[-1]
    content = latest.read_text(encoding="utf-8", errors="ignore")
    project_name = "requirements"
    # Versuche Projekt-Name zu lesen
    projects = _load_json(KANBAN_DIR / "projects.json")
    proj = next((p for p in projects if p["id"] == project_id), None)
    if proj:
        project_name = proj["name"].replace(" ", "_").replace("/", "-")
    if format == "md":
        return {"format": "md", "filename": f"{project_name}_SRS.md", "content": content, "mime": "text/markdown"}
    elif format == "html":
        # Simple MD -> HTML Konvertierung
        import re as _re
        html = _re.sub(r"^### (.+)$", r"<h3>\1</h3>", content, flags=_re.MULTILINE)
        html = _re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=_re.MULTILINE)
        html = _re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=_re.MULTILINE)
        html = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = _re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
        html = _re.sub(r"`(.+?)`", r"<code>\1</code>", html)
        html = _re.sub(r"^>\s+(.+)$", r"<blockquote>\1</blockquote>", html, flags=_re.MULTILINE)
        html = _re.sub(r"^---$", "<hr/>", html, flags=_re.MULTILINE)
        html_body = html.replace("\n", "<br/>\n")
        html_full = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{project_name} SRS</title>
<style>body{{font-family:system-ui,sans-serif;max-width:900px;margin:2em auto;padding:0 1em;line-height:1.6;color:#222;}}h1{{border-bottom:2px solid #333;}}h2{{color:#444;border-bottom:1px solid #ccc;}}blockquote{{background:#f0f0f0;padding:0.5em 1em;border-left:3px solid #888;margin:0.5em 0;}}code{{background:#f4f4f4;padding:1px 4px;border-radius:3px;}}</style>
</head><body>
{html_body}
</body></html>"""
        return {"format": "html", "filename": f"{project_name}_SRS.html", "content": html_full, "mime": "text/html"}
    elif format == "json":
        import json as _json
        # Parse MD zu strukturiertem JSON
        reqs = []
        current_type = None
        for line in content.splitlines():
            m = re.match(r"^### (FR|NFR|IF|DC)-(\d+):\s*(.+)", line)
            if m:
                reqs.append({
                    "id": f"{m.group(1)}-{m.group(2)}",
                    "type": m.group(1),
                    "title": m.group(3).strip(),
                    "source": "",
                    "requirement": "",
                    "verification": "",
                })
            else:
                if reqs:
                    if line.startswith("**Quelle:**"):
                        reqs[-1]["source"] = line.replace("**Quelle:**", "").strip()
                    elif line.startswith("**Requirement:**"):
                        reqs[-1]["requirement"] = line.replace("**Requirement:**", "").strip()
                    elif line.startswith("**Verifikation:**"):
                        reqs[-1]["verification"] = line.replace("**Verifikation:**", "").strip()
        return {
            "format": "json",
            "filename": f"{project_name}_SRS.json",
            "content": _json.dumps({
                "project_id": project_id,
                "project_name": proj["name"] if proj else project_id,
                "version": "1.0.0",
                "generated_at": _now(),
                "requirements": reqs,
            }, ensure_ascii=False, indent=2),
            "mime": "application/json",
        }
    elif format == "txt":
        # Plain text: entferne alle Markdown-Formatierung
        import re as _re
        plain = _re.sub(r"^#+\s+", "", content, flags=_re.MULTILINE)
        plain = _re.sub(r"\*\*(.+?)\*\*", r"\1", plain)
        plain = _re.sub(r"\*(.+?)\*", r"\1", plain)
        plain = _re.sub(r"`(.+?)`", r"\1", plain)
        plain = _re.sub(r"^>\s+", "  ", plain, flags=_re.MULTILINE)
        plain = _re.sub(r"^---$", "=" * 60, plain, flags=_re.MULTILINE)
        return {"format": "txt", "filename": f"{project_name}_SRS.txt", "content": plain, "mime": "text/plain"}
    else:
        raise HTTPException(400, f"Unbekanntes Format: {format}. Verfuegbar: md, html, json, txt")


# ─── Requirements → Tasks ──────────────────────────────────────────

@router.post("/requirements-to-tasks/{project_id}")
async def requirements_to_tasks(project_id: str, _user: str = Depends(require_auth)) -> list[dict]:
    """Uebersetzt Anforderungen in Tasks."""
    _ensure_dir()
    projects = _load_json(KANBAN_DIR / "projects.json")
    proj = next((p for p in projects if p["id"] == project_id), None)
    if not proj:
        raise HTTPException(404, "Project not found")

    # Bestehende Tasks laden
    tasks = _load_json(KANBAN_DIR / "tasks.json")

    # Aus Anforderungen Tasks generieren
    brain_log = proj.get("brainstorm_log", [])
    user_inputs = [t["text"] for t in brain_log if t["role"] == "user"]

    # SRS parsen, um Requirements zu extrahieren (fuer Traceability)
    files = sorted(REQUIREMENTS_DIR.glob(f"{project_id}_*.md"))
    srs_text = files[-1].read_text(encoding="utf-8", errors="ignore") if files else ""
    req_blocks = re.findall(r"### ((?:FR|NFR|IF|DC)-\d+):\s*([^\n]+)([\s\S]*?)(?=\n### |\n## |\Z)", srs_text)

    # Parent-Task erstellen
    parent_id = _id()
    parent_task = Task(
        id=parent_id, project_id=project_id,
        title=f"Projekt: {proj['name']}",
        description=f"Gesamtprojekt basierend auf:\n{user_inputs[0][:500] if user_inputs else 'Brainstorming'}",
        status="todo", priority=75,
        assigned_role="CEO-digital",
        success_criteria=["Alle Unter-Tasks abgeschlossen", "Qualitätskriterien erfüllt", "Dokumentation vollständig"],
        created_at=_now(), updated_at=_now(), order=0, iteration_count=0,
    )
    tasks.append(parent_task.model_dump())

    # === Granulare Tasks pro Requirement ===
    new_tasks = []
    if req_blocks:
        # Map: requirement_id -> (title, type, body)
        req_info = {}
        for req_id, title, body in req_blocks:
            req_info[req_id] = (title.strip(), body)
        # Sortierte Tasks: erst FR, dann NFR, dann IF, dann DC
        type_order = {"FR": 1, "IF": 2, "NFR": 3, "DC": 4}
        sorted_reqs = sorted(req_info.items(), key=lambda x: (type_order.get(x[0].split("-")[0], 99), x[0]))
        for i, (req_id, (title, body)) in enumerate(sorted_reqs):
            req_type = req_id.split("-")[0]
            # PERT-Schaetzung basierend auf Typ
            pert = {
                "FR": {"opt": 2, "ml": 6, "pess": 12, "unit": "h"},
                "NFR": {"opt": 1, "ml": 4, "pess": 8, "unit": "h"},
                "IF": {"opt": 3, "ml": 8, "pess": 16, "unit": "h"},
                "DC": {"opt": 0.5, "ml": 2, "pess": 4, "unit": "h"},
            }.get(req_type, {"opt": 2, "ml": 6, "pess": 12, "unit": "h"})
            # PERT-Erwartung = (opt + 4*ml + pess) / 6
            expected = round((pert["opt"] + 4 * pert["ml"] + pert["pess"]) / 6, 1)
            std_dev = round((pert["pess"] - pert["opt"]) / 6, 1)
            # Bestimme zustaendige Rolle
            role = {
                "FR": "pi-coder",
                "NFR": "pi-coder",
                "IF": "pi-coder",
                "DC": "CIO",
            }.get(req_type, "pi-coder")
            # Extrahiere Requirement-Text (falls vorhanden)
            req_text_match = re.search(r"\*\*Requirement:\*\*\s*([^\n]+)", body)
            req_text = req_text_match.group(1).strip() if req_text_match else title
            verif_match = re.search(r"\*\*Verifikation:\*\*\s*([^\n]+)", body)
            verif = verif_match.group(1).strip() if verif_match else "Akzeptanztest"
            child_id = _id()
            task = Task(
                id=child_id, project_id=project_id,
                title=f"[{req_id}] {title[:60]}",
                description=f"**Requirement ({req_id}):** {req_text}\n\n**Aus SRS:** {req_id}",
                status="todo",
                priority=75 if req_type in ("FR", "NFR") else 50,
                assigned_role=role,
                success_criteria=[verif] if verif else ["Akzeptanzkriterien erfüllt"],
                parent_id=parent_id,
                references=[parent_id],
                requirement_ref=req_id,  # Traceability
                tags=[req_type, "from-srs"],
                created_at=_now(), updated_at=_now(), order=i + 1,
                iteration_count=0,
            )
            task_dict = task.model_dump()
            # PERT-Schaetzung hinzufügen
            task_dict["pert"] = {**pert, "expected": expected, "std_dev": std_dev}
            tasks.append(task_dict)
            new_tasks.append(task_dict)
    else:
        # Fallback: generische Phasen-Tasks (kein SRS vorhanden)
        children = [
            {"title": "Analyse & Planung", "role": "CIO", "criteria": ["Anforderungsdokument erstellt"]},
            {"title": "Design & Architektur", "role": "CIO", "criteria": ["Architektur dokumentiert"]},
            {"title": "Implementierung Kernfunktion", "role": "pi-coder", "criteria": ["Code geschrieben"]},
            {"title": "Tests & Qualitätssicherung", "role": "pi-tester", "criteria": ["Alle Tests bestanden"]},
            {"title": "Review & Abnahme", "role": "pi-reviewer", "criteria": ["Review abgeschlossen"]},
            {"title": "Dokumentation & Delivery", "role": "CEO-digital", "criteria": ["Dokumentation vollständig"]},
        ]
        for i, child in enumerate(children):
            child_id = _id()
            task = Task(
                id=child_id, project_id=project_id,
                title=child["title"],
                description=f"Abgeleitet aus Projekt: {proj['name']}",
                status="triage", priority=50,
                assigned_role=child["role"],
                success_criteria=child["criteria"],
                parent_id=parent_id,
                references=[parent_id],
                tags=["fallback"],
                created_at=_now(), updated_at=_now(), order=i + 1,
                iteration_count=0,
            )
            task_dict = task.model_dump()
            task_dict["pert"] = {"opt": 2, "ml": 6, "pess": 12, "unit": "h", "expected": 6.3, "std_dev": 1.7}
            tasks.append(task_dict)
            new_tasks.append(task_dict)

    # Parent aktualisieren mit Child-IDs
    parent_task.child_ids = [t["id"] for t in tasks if t.get("parent_id") == parent_id]
    # Im parent_task auch PERT-Rollup speichern
    total_expected = sum(t.get("pert", {}).get("expected", 0) for t in new_tasks)
    total_variance = sum(t.get("pert", {}).get("std_dev", 0) ** 2 for t in new_tasks)
    total_std = round(total_variance ** 0.5, 1)
    # 95% Confidence Interval: expected +/- 2*sigma
    ci_low = round(total_expected - 2 * total_std, 1)
    ci_high = round(total_expected + 2 * total_std, 1)
    # Update parent
    for t in tasks:
        if t["id"] == parent_id:
            t["pert_rollup"] = {
                "total_expected_hours": round(total_expected, 1),
                "total_std_hours": total_std,
                "ci_95_low_hours": ci_low,
                "ci_95_high_hours": ci_high,
                "task_count": len(new_tasks),
            }
            break
    _save_json(KANBAN_DIR / "tasks.json", tasks)
    # Parent-Task + neue Child-Tasks zurueck
    parent = next((t for t in tasks if t["id"] == parent_id), None)
    return [parent] + new_tasks if parent else new_tasks


# ─── CIO-Review + Implementation-Start (Basissystem + erste App) ─────────────────

def _cio_review_tasks(tasks: list, brain_log: list) -> dict:
    """CIO-Review: pruft alle Tasks auf Vollstaendigkeit, generiert Freigabe-Empfehlung."""
    issues = []
    warnings = []
    if not tasks:
        return {"ready": False, "issues": ["Keine Tasks vorhanden"], "warnings": [], "stats": {"total": 0}}
    # Nur Child-Tasks pruefen (Parent ist "Projekt: X" und hat keinen realen Inhalt)
    child_tasks = [t for t in tasks if t.get("parent_id")]
    if not child_tasks:
        return {"ready": False, "issues": ["Keine Child-Tasks vorhanden"], "warnings": [], "stats": {"total": 0, "children": 0}}
    for t in child_tasks:
        # Pflichtfelder pruefen
        if not t.get("title") or t["title"].strip() in ("", "New Task"):
            issues.append({"task_id": t["id"], "type": "missing_title", "message": f"Task '{t.get('id', '?')[:8]}' hat keinen Titel"})
        if not t.get("description"):
            warnings.append({"task_id": t["id"], "type": "missing_description", "message": f"Task '{t.get('title', '?')[:50]}' hat keine Beschreibung"})
        if not t.get("success_criteria") or len(t["success_criteria"]) == 0:
            warnings.append({"task_id": t["id"], "type": "missing_criteria", "message": f"Task '{t.get('title', '?')[:50]}' hat keine Success-Criteria"})
        if not t.get("assigned_role") or t["assigned_role"] == "none":
            issues.append({"task_id": t["id"], "type": "missing_assignee", "message": f"Task '{t.get('title', '?')[:50]}' hat keinen Assignee"})
        if not t.get("priority") or t["priority"] == "none":
            warnings.append({"task_id": t["id"], "type": "missing_priority", "message": f"Task '{t.get('title', '?')[:50]}' hat keine Prioritaet"})
        # Status-Check
        if t.get("status") == "triage":
            warnings.append({"task_id": t["id"], "type": "in_triage", "message": f"Task '{t.get('title', '?')[:50]}' ist noch in Triage"})
    # Brainstorming-Vollstaendigkeit
    user_inputs = [t["text"] for t in brain_log if t["role"] == "user"]
    has_vision = len(user_inputs) > 0
    has_ceo = len(user_inputs) > 1
    if not has_vision:
        issues.append({"task_id": None, "type": "no_brainstorming", "message": "Kein Brainstorming vorhanden"})
    elif not has_ceo:
        warnings.append({"task_id": None, "type": "minimal_brainstorming", "message": "Brainstorming sehr kurz, mehr Details empfohlen"})
    ready = len(issues) == 0
    return {
        "ready": ready,
        "issues": issues,
        "warnings": warnings,
        "stats": {
            "total": len(tasks),
            "children": len(child_tasks),
            "issues_count": len(issues),
            "warnings_count": len(warnings),
        },
    }


@router.post("/implementation/{project_id}/cio-review")
async def cio_review_implementation(project_id: str, _user: str = Depends(require_auth)) -> dict:
    """CIO prueft alle Tasks und gibt Freigabe-Empfehlung."""
    _ensure_dir()
    projects = _load_json(KANBAN_DIR / "projects.json")
    proj = next((p for p in projects if p["id"] == project_id), None)
    if not proj:
        raise HTTPException(404, "Project not found")
    tasks_all = _load_json(KANBAN_DIR / "tasks.json")
    project_tasks = [t for t in tasks_all if t.get("project_id") == project_id]
    brain_log = proj.get("brainstorm_log", [])
    review = _cio_review_tasks(project_tasks, brain_log)
    # Speichern
    impl_data = _load_json(KANBAN_DIR / "implementation.json", default={})
    rec = impl_data.get(project_id, {})
    rec["cio_review"] = review
    rec["cio_review_at"] = _now()
    impl_data[project_id] = rec
    _save_json(KANBAN_DIR / "implementation.json", impl_data)
    return {
        "ok": True,
        "project_id": project_id,
        "ready": review["ready"],
        "issues": review["issues"],
        "warnings": review["warnings"],
        "stats": review["stats"],
    }


@router.post("/implementation/{project_id}/start")
async def start_implementation(project_id: str, _user: str = Depends(require_auth)) -> dict:
    """CIO gibt die Tasks frei und startet die Implementation.

    Erstellt einen Phasen-Plan:
    - Phase 1: Basissystem (Skeleton, Tests, CI, Docker)
    - Phase 2: Erste App (Hello-World mit Tech-Stack)
    - Phase 3+: Je ein Task = ein Prozessschritt
    """
    _ensure_dir()
    projects = _load_json(KANBAN_DIR / "projects.json")
    proj = next((p for p in projects if p["id"] == project_id), None)
    if not proj:
        raise HTTPException(404, "Project not found")
    tasks_all = _load_json(KANBAN_DIR / "tasks.json")
    project_tasks = [t for t in tasks_all if t.get("project_id") == project_id]
    brain_log = proj.get("brainstorm_log", [])
    # CIO-Review VOR dem Start
    review = _cio_review_tasks(project_tasks, brain_log)
    if not review["ready"]:
        raise HTTPException(400, {
            "message": "CIO-Review hat kritische Issues — erst beheben",
            "issues": review["issues"],
            "warnings": review["warnings"],
        })
    # Implementation-Plan erstellen
    child_tasks = [t for t in project_tasks if t.get("parent_id")]
    user_inputs = [t["text"] for t in brain_log if t["role"] == "user"]
    proj_desc = proj.get("description", "")
    # Phase 1: Basissystem (immer zuerst)
    phase_1_basissystem = {
        "phase_id": "phase_1_basissystem",
        "name": "Phase 1: Basissystem aufsetzen",
        "type": "baseline",
        "description": "Grundgerüst, Testing-Setup, CI-Pipeline, Docker-Container.",
        "steps": [
            {"id": "p1_1", "title": "Repository-Struktur anlegen", "description": "Standard-Layout (src/, tests/, docs/, docker/, ci/)", "role": "pi-coder", "estimated_h": 1},
            {"id": "p1_2", "title": "CI-Pipeline konfigurieren", "description": "GitHub Actions oder GitLab CI für Lint, Test, Build", "role": "pi-coder", "estimated_h": 2},
            {"id": "p1_3", "title": "Docker-Setup", "description": "Dockerfile + docker-compose.yml für lokale Entwicklung", "role": "pi-coder", "estimated_h": 1.5},
            {"id": "p1_4", "title": "Test-Framework einrichten", "description": "pytest/jest konfigurieren, Coverage-Report aktivieren", "role": "pi-coder", "estimated_h": 1},
            {"id": "p1_5", "title": "Linting & Formatierung", "description": "ESLint/Black/Prettier, Pre-Commit-Hook", "role": "pi-coder", "estimated_h": 1},
        ],
    }
    # Phase 2: Erste App (erste konkrete User-Story)
    phase_2_first_app = {
        "phase_id": "phase_2_first_app",
        "name": "Phase 2: Erste App erstellen (Hello-World)",
        "type": "first_app",
        "description": "Minimaler End-to-End-Flow: Eingabe -> Verarbeitung -> Ausgabe. Demonstriert den Tech-Stack in Aktion.",
        "steps": [
            {"id": "p2_1", "title": "Hello-World-Skeleton", "description": f"Minimale App mit dem gewaehlten Tech-Stack. Verbindet Frontend/Backend/Datenbank. Aufgabe: '{user_inputs[0][:100] if user_inputs else 'Vision'}' als Minimal-Version umsetzen.", "role": "pi-coder", "estimated_h": 4},
            {"id": "p2_2", "title": "Smoke-Test fuer Hello-World", "description": "End-to-End-Test: Eingabe -> Ausgabe funktioniert", "role": "pi-tester", "estimated_h": 1},
            {"id": "p2_3", "title": "README + Setup-Anleitung", "description": "Wie startet man die App lokal? Welche ENV-Vars? Wie testet man?", "role": "pi-coder", "estimated_h": 0.5},
        ],
    }
    # Phase 3+: Je ein Task = ein Prozessschritt
    phase_3_tasks = []
    for i, t in enumerate(child_tasks):
        pert = t.get("pert", {"expected": 4, "std_dev": 1})
        phase_3_tasks.append({
            "id": f"p3_{i+1}",
            "title": t.get("title", f"Task {i+1}"),
            "description": t.get("description", ""),
            "role": t.get("assigned_role", "pi-coder"),
            "task_id": t.get("id"),
            "requirement_ref": t.get("requirement_ref"),
            "estimated_h": pert.get("expected", 4),
            "success_criteria": t.get("success_criteria", []),
        })
    plan = {
        "phases": [phase_1_basissystem, phase_2_first_app] + ([
            {"phase_id": "phase_3_tasks", "name": "Phase 3: Tasks aus SRS umsetzen", "type": "feature_tasks",
             "description": f"{len(child_tasks)} Tasks aus dem generierten Anforderungsdokument, sortiert nach Requirement-ID.",
             "steps": phase_3_tasks}
        ] if phase_3_tasks else []),
    }
    # Status pro Step initial "todo"
    for phase in plan["phases"]:
        for step in phase["steps"]:
            step["status"] = "todo"
    # Speichern
    impl_data = _load_json(KANBAN_DIR / "implementation.json", default={})
    impl_data[project_id] = {
        "project_id": project_id,
        "started_at": _now(),
        "cio_review": review,
        "plan": plan,
        "current_phase_index": 0,
        "current_step_index": 0,
    }
    _save_json(KANBAN_DIR / "implementation.json", impl_data)
    return {
        "ok": True,
        "project_id": project_id,
        "started_at": impl_data[project_id]["started_at"],
        "plan": plan,
        "cio_review": review,
    }


@router.get("/implementation/{project_id}")
async def get_implementation(project_id: str, _user: str = Depends(require_auth)) -> dict:
    impl_data = _load_json(KANBAN_DIR / "implementation.json", default={})
    rec = impl_data.get(project_id)
    if not rec:
        raise HTTPException(404, "Keine Implementation vorhanden — zuerst starten")
    return rec


@router.post("/implementation/{project_id}/step/{step_id}/done")
async def mark_step_done(project_id: str, step_id: str, _user: str = Depends(require_auth)) -> dict:
    """Markiert einen Implementation-Step als done und springt zum naechsten."""
    impl_data = _load_json(KANBAN_DIR / "implementation.json", default={})
    rec = impl_data.get(project_id)
    if not rec:
        raise HTTPException(404, "Keine Implementation vorhanden")
    plan = rec.get("plan", {})
    found = False
    for pi, phase in enumerate(plan.get("phases", [])):
        for si, step in enumerate(phase.get("steps", [])):
            if step.get("id") == step_id:
                step["status"] = "done"
                step["completed_at"] = _now()
                rec["current_phase_index"] = pi
                rec["current_step_index"] = si + 1
                found = True
                break
        if found:
            break
    if not found:
        raise HTTPException(404, f"Step '{step_id}' nicht gefunden")
    impl_data[project_id] = rec
    _save_json(KANBAN_DIR / "implementation.json", impl_data)
    return {"ok": True, "project_id": project_id, "step_id": step_id, "status": "done"}


# ─── Erweiterte Tasks (mit Parent/Child/References) ───────────────


# ─── Erweiterte Tasks (mit Parent/Child/References) ───────────────

@router.get("/tasks", response_model=list[Task])
async def list_tasks(project_id: str | None = None, _user: str = Depends(require_auth)) -> list[Task]:
    all_tasks = _load_json(KANBAN_DIR / "tasks.json")
    # Initial-Migration: alle bestehenden Tasks ohne/mit String-Prio -> 0
    if _migrate_task_prio(all_tasks):
        _save_json(KANBAN_DIR / "tasks.json", all_tasks)
    # Bug 3 Fix (Task d63824618a8c): Audit-Pflicht — alle Tasks bekommen mindestens
    # 1 History-Eintrag (history_reconstructed fuer Legacy). Frontend zeigt
    # `_audit_warning` als '⚠️ Audit-Warnung'-Badge.
    audit_changed = False
    for t in all_tasks:
        if not t.get("history"):
            _ensure_minimal_history(t)
            audit_changed = True
    if audit_changed:
        _save_json(KANBAN_DIR / "tasks.json", all_tasks)
    # UI-Redesign (Task d3dabcba252c): Phase-Tracking-Migration — bestehende Tasks
    # ohne phase_started_at bekommen den Fallback created_at. Damit funktioniert
    # der Phase-Timer auch fuer Legacy-Tasks korrekt (Annahme: Phase startete bei
    # Task-Erstellung, was fuer die meisten realistisch ist).
    phase_migration_changed = False
    for t in all_tasks:
        if not t.get("phase_started_at"):
            t["phase_started_at"] = t.get("created_at") or t.get("updated_at") or _now()
            phase_migration_changed = True
    if phase_migration_changed:
        _save_json(KANBAN_DIR / "tasks.json", all_tasks)
    if project_id:
        all_tasks = [t for t in all_tasks if t.get("project_id") == project_id]
    return [Task(**t) for t in all_tasks]


@router.post("/tasks", response_model=Task)
async def create_task(req: dict, _user: str = Depends(require_auth)) -> Task:
    tasks = _load_json(KANBAN_DIR / "tasks.json")
    # Priority: 0..100 validieren. Falls String (alte Clients) -> 0 (Initial-Migration)
    raw_prio = req.get("priority", 50)
    if isinstance(raw_prio, str):
        try:
            prio_int = int(raw_prio)
        except ValueError:
            prio_int = 0  # String-Prios aus alter Datenstruktur -> 0
    else:
        try:
            prio_int = int(raw_prio)
        except (TypeError, ValueError):
            prio_int = 50
    prio_int = max(0, min(100, prio_int))  # clamp 0..100
    t = Task(
        id=_id(),
        project_id=req.get("project_id", ""),
        title=req.get("title", "New Task"),
        description=req.get("description", ""),
        priority=prio_int,
        assigned_role=req.get("assigned_role", "pi-coder"),
        success_criteria=req.get("success_criteria", []),
        parent_id=req.get("parent_id"),
        references=req.get("references", []),
        requirement_ref=req.get("requirement_ref"),
        tags=req.get("tags", []),
        created_at=_now(), updated_at=_now(),
        order=len(tasks),
        iteration_count=0,
        # UI-Redesign (Task d3dabcba252c): Phase-Tracking — neue Tasks starten ihre
        # Phase direkt bei Erstellung. Bei spaeteren Status-Wechseln (z.B. auto_claim)
        # wird das Feld via _set_task_status() aktualisiert.
        phase_started_at=_now(),
    )
    task_dict = t.model_dump()
    task_dict["history"] = []
    _add_history(task_dict, "task_created", agent="user", details={"prio": prio_int, "role": task_dict.get("assigned_role")})
    tasks.append(task_dict)
    _save_json(KANBAN_DIR / "tasks.json", tasks)
    # SSE-Event: neue Task
    await _publish_task_event(t.project_id, "task_created", task_dict)
    return t


class TaskStatusUpdate(BaseModel):
    status: str  # "triage" | "todo" | "in_progress" | "review" | "done" | "blocked"


# === SSE Event-Bus fuer Echtzeit-Updates ===
import asyncio
import json
from collections import defaultdict

# project_id -> set von asyncio.Queue (eine pro Client-Subscription)
_event_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

async def _publish_task_event(project_id: str, event_type: str, task: dict) -> None:
    """Publish Task-Event an alle SSE-Subscriber des Projekts."""
    payload = json.dumps({
        "type": event_type,
        "task_id": task.get("id"),
        "task": task,
        "ts": task.get("updated_at", ""),
    }, ensure_ascii=False)
    dead_queues: list[asyncio.Queue] = []
    for q in _event_subscribers.get(project_id, set()):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead_queues.append(q)
    for q in dead_queues:
        _event_subscribers[project_id].discard(q)


@router.get("/events/{project_id}")
async def stream_task_events(project_id: str, _user: str = Depends(require_auth)):
    """SSE-Endpoint: streamt Task-Aenderungen als Server-Sent Events.

    Client subscribed via `new EventSource('/api/kanban/events/{project_id}')`.
    Server pusht Events im JSON-Format: { type, task_id, task, ts }.
    Heartbeat alle 25s, damit Load-Balancer die Connection nicht killen.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _event_subscribers[project_id].add(queue)
    print(f"[SSE] Client subscribed to project {project_id} (total: {len(_event_subscribers[project_id])})")
    async def event_generator():
        try:
            # Initial-Event, damit der Client weiss, dass die Verbindung steht
            yield f"data: {json.dumps({'type': 'connected', 'project_id': project_id})}\n\n"
            last_heartbeat = asyncio.get_event_loop().time()
            while True:
                try:
                    # 25s-Timeout fuer Heartbeat
                    payload = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield f"data: {payload}\n\n"
                    last_heartbeat = asyncio.get_event_loop().time()
                except asyncio.TimeoutError:
                    # Heartbeat (vom Browser ignoriert, haelt aber die Connection am Leben)
                    yield ": heartbeat\n\n"
                    last_heartbeat = asyncio.get_event_loop().time()
        except asyncio.CancelledError:
            print(f"[SSE] Client disconnected from project {project_id}")
        finally:
            _event_subscribers[project_id].discard(queue)
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx: kein Buffering
        },
    )


class TaskPriorityUpdate(BaseModel):
    priority: int  # 0..100


class TaskDispatchUpdate(BaseModel):
    role: str | None = None
    status: str | None = None  # dispatching | dispatched | dry-run | done
    model: str | None = None
    agent_pid: int | None = None
    ts: str | None = None
    reason: str | None = None
    tokens_in: int | None = 0
    tokens_out: int | None = 0


class TaskTokenReport(BaseModel):
    """Meldet die kumulierten Token-Counts eines laufenden Sub-Agents."""
    model: str | None = None
    role: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    note: str | None = None  # optional, z.B. "after final tool call"


# === Task-Historie Helper (Task 5b56c7584669) ===
def _add_history(t: dict, event: str, agent: str = "system", **details) -> None:
    """Haengt einen History-Eintrag an task.history an. In-place."""
    if "history" not in t or not isinstance(t.get("history"), list):
        t["history"] = []
    entry = {
        "ts": _now(),
        "event": event,
        "agent": agent,
    }
    if details:
        entry["details"] = details
    t["history"].append(entry)


def _aggregate_task_stats(t: dict) -> dict:
    """Aggregiert Stats aus task.history: tokens, cost, duration, model.

    Tokens werden aus BODEN gesucht: erst Top-Level (tokens_in/tokens_out),
    dann in details (aelteres Schema). So werden sowohl alte als auch neue
    History-Eintraege korrekt aggregiert.

    Cost wird IMMER aus dem pricing_snapshot berechnet (falls vorhanden),
    damit abgeschlossene Tasks nicht durch spaetere Provider-Preisaenderungen
    beruehrt werden. Fallback: in History-Eintrag gespeichertes cost_usd.
    """
    history = t.get("history") or []
    tokens_in = 0
    tokens_out = 0
    cost_usd = 0.0
    model_usage: dict[str, int] = {}
    for h in history:
        # Tokens: Top-Level hat Vorrang (neues Schema), Fallback details
        ti = h.get("tokens_in")
        to = h.get("tokens_out")
        if ti is None or to is None:
            details = h.get("details", {}) or {}
            ti = ti if ti is not None else details.get("tokens_in", 0) or 0
            to = to if to is not None else details.get("tokens_out", 0) or 0
        tokens_in  += ti
        tokens_out += to
        m = h.get("model") or "unknown"
        model_usage[m] = model_usage.get(m, 0) + 1
    # Snapshot-Preis holen (wenn vorhanden)
    snap = t.get("pricing_snapshot")
    if snap:
        # Kosten werden aus dem Snapshot berechnet - das ist der
        # abrechnungsrelevante Preis, unabhaengig von aktuellen Provider-Preisen.
        cost_usd = _calc_cost_from_snapshot(tokens_in, tokens_out, snap)
    else:
        # Fallback: in History-Eintraegen gespeicherte cost_usd summieren
        for h in history:
            c = h.get("cost_usd")
            if c is None:
                c = (h.get("details", {}) or {}).get("cost_usd", 0.0) or 0.0
            cost_usd += c
    # Dauer
    duration_s = 0
    if len(history) >= 1:
        try:
            first = datetime.fromisoformat(history[0].get("ts", ""))
            last = datetime.fromisoformat(history[-1].get("ts", ""))
            duration_s = int((last - first).total_seconds())
        except (ValueError, TypeError):
            pass
    # haeufigstes Modell
    main_model = max(model_usage, key=model_usage.get) if model_usage else "unknown"
    return {
        "task_id": t.get("id"),
        "model": main_model,
        "model_usage": model_usage,
        "tokens": {"in": tokens_in, "out": tokens_out, "total": tokens_in + tokens_out},
        "cost_usd": round(cost_usd, 6),
        "duration_s": duration_s,
        "history_count": len(history),
        "pricing_snapshot": snap,  # eingefuegt: Snapshot mit anzeigen
    }


# Pricing-Config (USD pro Token).
# HINWEIS: Diese Werte sind nur ein FALLBACK. Die echten Preise kommen aus
# `models.json` (pro Provider, pro Modell, mit last_updated Timestamp).
# Beim Task-Start wird ein PRICING-SNAPSHOT im Task gespeichert, damit
# spaetere Provider-Preisaenderungen abgeschlossene Tasks NICHT beruehren.
#
# Quelle (15.06.2026): https://platform.minimax.io/docs/guides/pricing-paygo
#   - MiniMax-M3 (50% off launch promo): $0.30/M input, $1.20/M output
#   - MiniMax-M2.7:                       $0.30/M input, $1.20/M output
#   - MiniMax-M2.5:                       $0.15/M input, $1.08/M output
#   - Ollama (lokal):                     $0 (keine API-Kosten)
DEFAULT_MODEL_PRICING = {
    # USD pro Token (also input_per_1m / 1_000_000)
    "minimax/minimax-m3":  {"in": 0.00000030, "out": 0.00000120},
    "minimax/minimax-m2.7":{"in": 0.00000030, "out": 0.00000120},
    "minimax/minimax-m2.5":{"in": 0.00000015, "out": 0.00000108},
    "ollama/gemma4:12b":   {"in": 0.0,        "out": 0.0},
    "ollama/gemma3:4b":    {"in": 0.0,        "out": 0.0},
    "ollama/gemma4-long:latest": {"in": 0.0,  "out": 0.0},
    "ollama/qwen3.6:latest":      {"in": 0.0,  "out": 0.0},
    "openrouter/anthropic/claude-sonnet-4": {"in": 0.00000300, "out": 0.00001500},
}


def _get_current_pricing(model_id: str) -> dict:
    """Holt aktuellen Provider-Preis (USD/Token) fuer ein Modell.

    Akzeptiert verschiedene Formate:
    - "minimax/minimax-m3" (kanonisch, wird vom Dashboard verwendet)
    - "minimax-direct/minimax-m3" (Provider/Model aus models.json)
    - "openrouter/anthropic/claude-sonnet-4" (Provider/Org/Model)

    Lookup-Reihenfolge:
    1. models.json (manuell editierbar, hat last_updated)
    2. DEFAULT_MODEL_PRICING (Fallback)
    """
    if not model_id:
        return {"in": 0.0, "out": 0.0, "source": "unknown"}
    cfg = read_json(settings.models_json, {}) or {}
    providers = cfg.get("providers", {}) or {}
    # Provider-Aliase: "minimax" -> "minimax-direct"
    PROVIDER_ALIAS = {"minimax": "minimax-direct"}
    # 1) Versuche Modelle aller Provider, deren Models-Liste den passenden Model-Namen enthaelt
    # Format: "minimax/minimax-m3" -> provider="minimax", wanted_model="minimax-m3"
    # Format: "openrouter/anthropic/claude-sonnet-4" -> provider="openrouter", wanted_model kann "anthropic/claude-sonnet-4" oder "claude-sonnet-4" sein
    if "/" in model_id:
        prov_part, rest = model_id.split("/", 1)
        real_prov = PROVIDER_ALIAS.get(prov_part, prov_part)
        prov = providers.get(real_prov, {}) or {}
        pricing_map = prov.get("pricing", {}) or {}
        # 1a) Vollqualifizierter Match (z.B. "anthropic/claude-sonnet-4" als key)
        p = pricing_map.get(rest)
        # 1b) Nur letzter Teil (z.B. "claude-sonnet-4")
        if not p:
            last = rest.split("/")[-1]
            p = pricing_map.get(last)
        # 1c) Provider-Default
        if not p:
            p = pricing_map.get("default")
        if p:
            return {
                "in":  float(p.get("input_per_1m", 0))  / 1_000_000,
                "out": float(p.get("output_per_1m", 0)) / 1_000_000,
                "input_per_1m":  float(p.get("input_per_1m", 0)),
                "output_per_1m": float(p.get("output_per_1m", 0)),
                "source":   p.get("source", "models.json"),
                "last_updated": p.get("last_updated"),
                "note":     p.get("note", ""),
                "provider": real_prov,
            }
    # 2) Statischer Fallback (mit allen Alias-Kombinationen versuchen)
    for full_id in [model_id,
                    model_id.replace("minimax/", "minimax-direct/", 1) if model_id.startswith("minimax/") else None]:
        if full_id and full_id in DEFAULT_MODEL_PRICING:
            return {**DEFAULT_MODEL_PRICING[full_id], "provider": model_id.split("/", 1)[0], "source": "fallback"}
    return {"in": 0.0, "out": 0.0, "source": "unknown", "provider": model_id.split("/", 1)[0] if "/" in model_id else model_id}


def _take_pricing_snapshot(t: dict) -> dict:
    """Speichert aktuellen Provider-Preis im Task.

    Wird bei auto_claim / emergency_watchdog / Dispatch aufgerufen.
    So wird der Preis FIXIERT, mit dem der Task abgerechnet wird -
    auch wenn sich Provider-Preise spaeter aendern.
    """
    model_id = t.get("dispatch_model") or t.get("model") or "minimax/minimax-m3"
    pricing = _get_current_pricing(model_id)
    snap = {
        "model":          model_id,
        "provider":       pricing.get("provider", model_id.split("/", 1)[0] if "/" in model_id else "unknown"),
        "input_per_1m":   pricing.get("input_per_1m", pricing["in"] * 1_000_000),
        "output_per_1m":  pricing.get("output_per_1m", pricing["out"] * 1_000_000),
        "snapshot_at":    _now(),
        "source":         pricing.get("source", "fallback"),
        "note":           pricing.get("note", ""),
    }
    t["pricing_snapshot"] = snap
    return snap


def _calc_cost_from_snapshot(tokens_in: int, tokens_out: int, snap: dict | None) -> float:
    """Berechnet USD-Kosten basierend auf Task-Snapshot (NICHT aktuellem Preis)."""
    if not snap:
        return 0.0
    in_per_t  = float(snap.get("input_per_1m", 0)) / 1_000_000
    out_per_t = float(snap.get("output_per_1m", 0)) / 1_000_000
    return round(tokens_in * in_per_t + tokens_out * out_per_t, 6)


# Backward-Compat: MODEL_PRICING bleibt als Fallback exportiert
MODEL_PRICING = DEFAULT_MODEL_PRICING


# === Kanban-Operator: Auto-Transitionen ===
def _kanban_operator_auto_claim(task: dict, now: str) -> dict:
    """Wenn Status auf 'todo' gesetzt wird, uebernimmt der PI-Worker automatisch (Triage->Todo->In Progress)."""
    if task.get("status") != "todo":
        return {"auto_action": None}
    # Bug 3 Fix: Status-Setter via Helper (Audit-Pflicht)
    _set_task_status(task, "in_progress", agent="kanban-operator", reason="auto_claim")
    task["claimed_at"] = now
    task["assigned_role"] = task.get("assigned_role") or "pi-coder"
    # PREIS-SNAPSHOT: aktuellen Provider-Preis fixieren fuer spaetere Cost-Berechnung
    snap = _take_pricing_snapshot(task)
    return {
        "auto_action": "auto_claim",
        "new_status": "in_progress",
        "message": f"PI-Worker ({task['assigned_role']}) hat automatisch uebernommen.",
        "pricing_snapshot": snap,
    }


@router.put("/tasks/{task_id}/status")
async def update_task_status(task_id: str, req: TaskStatusUpdate, _user: str = Depends(require_auth)) -> dict:
    """Setzt den Status einer Task (fuer Drag-and-Drop im Board).

    KANBAN-OPERATOR: Wenn Status auf 'todo' gesetzt wird, uebernimmt der PI-Worker
    automatisch (Task wandert direkt von Todo nach In Progress).
    """
    tasks = _load_json(KANBAN_DIR / "tasks.json")
    t = next((t for t in tasks if t["id"] == task_id), None)
    if not t:
        raise HTTPException(404, "Task not found")
    valid_statuses = ("triage", "todo", "in_progress", "review", "done", "blocked")
    if req.status not in valid_statuses:
        raise HTTPException(400, f"Ungueltiger Status. Erlaubt: {valid_statuses}")
    now = _now()
    # Bug 3 Fix: Status-Setter via Helper (Audit-Pflicht)
    _set_task_status(t, req.status, agent="user", reason="update_task_status")
    auto_log = None
    # Kanban-Operator: Auto-Claim wenn Status auf 'todo' gesetzt wird
    if req.status == "todo":
        auto_log = _kanban_operator_auto_claim(t, now)
    _save_json(KANBAN_DIR / "tasks.json", tasks)
    # SSE-Event: Task-Status geaendert
    await _publish_task_event(t.get("project_id", ""), "task_status_changed", t)
    return {
        "ok": True,
        "task_id": task_id,
        "status": t["status"],
        "auto_action": auto_log,
    }


# === Kanban-Operator: EMERGENCY-WATCHDOG (Prio=100) ===
def _kanban_operator_emergency_watchdog(task: dict, now: str) -> dict:
    """Wenn Prio=100 gesetzt wird, loest der Watchdog eine Notfallumsetzung aus:
    - Task wird sofort von PI-Worker uebernommen (Status -> in_progress)
    - Notfall-Flag + Timestamp werden gesetzt
    - assigned_role wird auf 'pi-coder' gesetzt (oder beibehalten, wenn schon spezifischer)
    """
    if task.get("status") in ("done",):
        return {"auto_action": None, "skipped": "task_already_done"}  # Erledigte Tasks nicht mehr starten
    previous_status = task.get("status", "?")
    # Bug 3 Fix: Status-Setter via Helper (Audit-Pflicht)
    _set_task_status(task, "in_progress", agent="kanban-operator", reason="emergency_watchdog: priority>=90")
    task["emergency"] = True
    task["emergency_at"] = now
    task["emergency_reason"] = "priority=100 (Watchdog-Auto-Claim)"
    task["claimed_at"] = now
    # assigned_role beibehalten falls schon gesetzt, sonst default
    if not task.get("assigned_role") or task.get("assigned_role") == "":
        task["assigned_role"] = "pi-coder"
    # PREIS-SNAPSHOT: Notfall = aktueller Preis wird sofort fixiert
    snap = _take_pricing_snapshot(task)
    return {
        "auto_action": "emergency_claim",
        "previous_status": previous_status,
        "new_status": "in_progress",
        "message": f"🚨 NOTFALL (Prio {task.get('priority', 100)}): Task '{task.get('title', '?')[:50]}' — sofortige Uebernahme durch {task['assigned_role']}.",
        "task_id": task.get("id"),
        "pricing_snapshot": snap,
    }


@router.put("/tasks/{task_id}/priority")
async def update_task_priority(task_id: str, req: TaskPriorityUpdate, _user: str = Depends(require_auth)) -> dict:
    """Setzt die Prioritaet (0..100) einer Task.

    KANBAN-OPERATOR-WATCHDOG: Wenn priority=100 gesetzt wird, loest der Watchdog
    eine Notfallumsetzung aus (Auto-Claim + Status -> in_progress + emergency-Flag).
    """
    tasks = _load_json(KANBAN_DIR / "tasks.json")
    t = next((t for t in tasks if t["id"] == task_id), None)
    if not t:
        raise HTTPException(404, "Task not found")
    # Clamp 0..100
    prio = max(0, min(100, int(req.priority)))
    now = _now()
    t["priority"] = prio
    t["updated_at"] = now
    auto_log = None
    # Watchdog: Prio >= 90 -> Notfallumsetzung (alle Prio ueber 90 sind Notfall)
    if prio >= 90:
        auto_log = _kanban_operator_emergency_watchdog(t, now)
    else:
        # Wenn Prio unter 90 faellt, Notfall-Flag entfernen
        if t.get("emergency"):
            t["emergency"] = False
            t["emergency_cleared_at"] = now
    _save_json(KANBAN_DIR / "tasks.json", tasks)
    # SSE-Event: Task-Priority geaendert
    await _publish_task_event(t.get("project_id", ""), "task_priority_changed", t)
    return {
        "ok": True,
        "task_id": task_id,
        "priority": t["priority"],
        "status": t.get("status"),
        "emergency": t.get("emergency", False),
        "auto_action": auto_log,
    }


@router.patch("/tasks/{task_id}/dispatch")
async def update_dispatch_status(task_id: str, req: TaskDispatchUpdate, _user: str = Depends(require_auth)) -> dict:
    """Aktualisiert den Dispatch-Status eines Tasks (vom Sub-Agent aufgerufen).

    Wird vom swarm-spawner oder direkt vom Sub-Agent nach Process-Start aufgerufen,
    um Rolle, PID und Status zurueck ans Dashboard zu melden.

    Bug 1 Fix (Task d63824618a8c): SYNC-BUG
    ---------------------------------------
    Wenn SubAgent `status=done` meldet, wird `task.status` automatisch auf `done` gesetzt
    (statt nur `dispatch_status`). Analog fuer `status=dispatched` -> `task.status=in_progress`
    falls Task noch in 'todo' war. Idempotent: Mehrfaches done erzeugt nur 1 History-Eintrag.
    """
    tasks = _load_json(KANBAN_DIR / "tasks.json")
    t = next((t for t in tasks if t["id"] == task_id), None)
    if not t:
        raise HTTPException(404, "Task not found")
    now = _now()
    # Update Felder (nur nicht-leere)
    if req.role is not None: t["dispatch_role"] = req.role
    if req.status is not None: t["dispatch_status"] = req.status
    if req.model is not None: t["dispatch_model"] = req.model
    if req.agent_pid is not None: t["agent_pid"] = req.agent_pid
    if req.reason is not None: t["dispatch_reason"] = req.reason
    t["updated_at"] = now
    # History-Eintrag
    model = req.model or t.get("dispatch_model") or "minimax/minimax-m3"
    t["dispatch_model"] = model
    # PREIS-SNAPSHOT: bei erstem Dispatch festlegen, bei spaeteren verwenden
    if not t.get("pricing_snapshot") or t["pricing_snapshot"].get("model") != model:
        snap = _take_pricing_snapshot(t)
    else:
        snap = t["pricing_snapshot"]
    # Token-Stats: aus request oder default
    tokens_in = req.tokens_in or 0
    tokens_out = req.tokens_out or 0
    # Kosten aus SNAPSHOT berechnen, nicht aus aktuellem Preis
    cost = _calc_cost_from_snapshot(tokens_in, tokens_out, snap)
    t.setdefault("history", []).append({
        "ts": now,
        "event": "subagent_dispatched",
        "agent": req.role or "unknown",
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost,
        "details": {
            "status": req.status,
            "agent_pid": req.agent_pid,
            "reason": req.reason,
            "pricing_snapshot_used": snap,  # Traceability: Welcher Preis wurde verwendet
        },
    })

    # ─── SYNC-Bug 1 Fix: dispatch_status synchronisiert task.status ───
    # Wenn SubAgent 'done' meldet, Task auf done setzen
    # Wenn SubAgent 'dispatched' meldet und Task noch in 'todo' war, auf 'in_progress'
    sync_status_changed = False
    if req.status == "done" and t.get("status") != "done":
        old_status = t["status"]
        _set_task_status(
            t, "done", agent=req.role or "subagent",
            reason=f"SubAgent meldete done: {req.reason or 'kein Grund'}",
            sync_from="dispatch",
            dispatch_pid=req.agent_pid,
        )
        sync_status_changed = True
    elif req.status == "dispatched" and t.get("status") == "todo":
        # SubAgent hat uebernommen: todo -> in_progress
        _set_task_status(
            t, "in_progress", agent=req.role or "subagent",
            reason="SubAgent hat Task uebernommen (dispatched)",
            sync_from="dispatch",
            dispatch_pid=req.agent_pid,
        )
        sync_status_changed = True

    _save_json(KANBAN_DIR / "tasks.json", tasks)
    # SSE-Event
    await _publish_task_event(t.get("project_id", ""), "task_dispatched", t)
    return {
        "ok": True,
        "task_id": task_id,
        "dispatch_role": t.get("dispatch_role"),
        "dispatch_status": t.get("dispatch_status"),
        "dispatch_model": t.get("dispatch_model"),
        "agent_pid": t.get("agent_pid"),
        "task_status_synced": sync_status_changed,  # Bug 1 Fix: zeigt an ob task.status geaendert wurde
        "task_status": t.get("status"),
    }


# === Bug 2 Fix (Task d63824618a8c): Haenger-Erkennung als Endpoint ===
@router.get("/haenger")
async def list_haenger(_user: str = Depends(require_auth)) -> dict:
    """Listet alle Haenger-Tasks (Bug 2 Fix).

    Ein Task gilt als Haenger, wenn:
    - status == 'in_progress'
    - updated_at > 10 Min her
    - UND (kein agent_pid ODER agent_pid Prozess existiert nicht mehr)

    Returns:
        { haenger: [...], count: N, checked_at: ISO-Timestamp }
    """
    tasks = _load_json(KANBAN_DIR / "tasks.json")
    now = datetime.now()
    haenger = _detect_haenger_tasks(tasks, now)
    return {
        "haenger": haenger,
        "count": len(haenger),
        "checked_at": now.isoformat(),
        "thresholds": {
            "age_seconds": HAENGER_AGE_SECONDS,
            "worker_switch_age": HAENGER_WORKER_SWITCH_AGE,
            "emergency_age": HAENGER_EMERGENCY_AGE,
        },
    }


@router.post("/tasks/{task_id}/usage")
async def report_task_usage(task_id: str, req: TaskTokenReport, _user: str = Depends(require_auth)) -> dict:
    """Sub-Agent meldet kumulierte Token-Counts zurueck ans Dashboard.

    Wird typischerweise vom spawn.sh nach Beendigung des Sub-Agents aufgerufen.
    Die Tokens werden in einen neuen History-Eintrag 'token_usage_report'
    geschrieben. Der Stats-Endpoint summiert alle tokens_in/tokens_out aus
    der History und berechnet den Cost mit dem pricing_snapshot, der bei
    auto_claim/emergency_watchdog festgelegt wurde.

    So ist sichergestellt: Cost = aktuelle Provider-Preise ZUM ZEITPUNKT
    des Task-Starts, nicht der aktuelle Preis.
    """
    tasks = _load_json(KANBAN_DIR / "tasks.json")
    t = next((t for t in tasks if t["id"] == task_id), None)
    if not t:
        raise HTTPException(404, "Task not found")
    now = _now()
    model = req.model or t.get("dispatch_model") or "minimax/minimax-m3"
    t["dispatch_model"] = model
    # Snapshot sicherstellen
    if not t.get("pricing_snapshot"):
        _take_pricing_snapshot(t)
    snap = t["pricing_snapshot"]
    # Cost aus Snapshot berechnen (unabhaengig von aktuellem Provider-Preis)
    cost = _calc_cost_from_snapshot(req.tokens_in, req.tokens_out, snap)
    # History-Eintrag
    t.setdefault("history", []).append({
        "ts": now,
        "event": "token_usage_report",
        "agent": req.role or t.get("dispatch_role") or "subagent",
        "model": model,
        "tokens_in": req.tokens_in,
        "tokens_out": req.tokens_out,
        "cost_usd": cost,
        "details": {
            "note": req.note or "",
            "pricing_snapshot_used": snap,
        },
    })
    _save_json(KANBAN_DIR / "tasks.json", tasks)
    return {
        "ok": True,
        "task_id": task_id,
        "tokens_in": req.tokens_in,
        "tokens_out": req.tokens_out,
        "cost_usd": cost,
        "pricing_snapshot": snap,
    }


# === Sub-Task-Erstellung (PI-Worker teilt grosse Tasks) ===
class SubTaskCreate(BaseModel):
    subtasks: list[dict]  # [{title, description, assigned_role, success_criteria}]


@router.post("/tasks/{task_id}/subtasks")
async def create_subtasks(task_id: str, req: SubTaskCreate, _user: str = Depends(require_auth)) -> dict:
    """PI-Worker erstellt Sub-Tasks fuer eine grosse Task.

    Jede Sub-Task bekommt parent_id=task_id und assigned_role des gewaehlten Sub-Agents.
    """
    tasks = _load_json(KANBAN_DIR / "tasks.json")
    parent = next((t for t in tasks if t["id"] == task_id), None)
    if not parent:
        raise HTTPException(404, "Parent-Task nicht gefunden")
    if not req.subtasks:
        raise HTTPException(400, "subtasks darf nicht leer sein")
    new_subtasks = []
    for st in req.subtasks:
        if not st.get("title"):
            continue
        subtask = {
            "id": _id(),
            "project_id": parent.get("project_id"),
            "title": st["title"],
            "description": st.get("description", ""),
            "status": "triage",
            "priority": _coerce_prio_int(st.get("priority", parent.get("priority", 50))),
            "assigned_role": st.get("assigned_role", "pi-coder"),
            "success_criteria": st.get("success_criteria", []),
            "parent_id": task_id,
            "references": [task_id],
            "requirement_ref": parent.get("requirement_ref"),
            "tags": ["sub-task"] + (st.get("tags", [])),
            "created_at": _now(),
            "updated_at": _now(),
            "order": len(tasks),
            "iteration_count": 0,
        }
        new_subtasks.append(subtask)
    tasks.extend(new_subtasks)
    # Parent-Task markieren
    parent["has_subtasks"] = True
    parent["subtask_count"] = len([t for t in tasks if t.get("parent_id") == task_id])
    parent["updated_at"] = _now()
    _save_json(KANBAN_DIR / "tasks.json", tasks)
    return {
        "ok": True,
        "parent_id": task_id,
        "created": len(new_subtasks),
        "subtasks": new_subtasks,
    }


@router.post("/tasks/{task_id}/aggregate")
async def aggregate_subtask_status(task_id: str, _user: str = Depends(require_auth)) -> dict:
    """Aggregiert den Sub-Task-Status zum Parent-Task.

    Wenn alle Sub-Tasks 'done' sind, wird der Parent auf 'done' gesetzt.
    Wenn mind. eine Sub-Task 'in_progress' ist, wird der Parent auf 'in_progress' gesetzt.
    """
    tasks = _load_json(KANBAN_DIR / "tasks.json")
    parent = next((t for t in tasks if t["id"] == task_id), None)
    if not parent:
        raise HTTPException(404, "Parent-Task nicht gefunden")
    subtasks = [t for t in tasks if t.get("parent_id") == task_id]
    if not subtasks:
        raise HTTPException(400, "Task hat keine Sub-Tasks")
    # Aggregation-Logik
    statuses = [t["status"] for t in subtasks]
    old_status = parent.get("status")
    new_status = old_status
    if all(s == "done" for s in statuses):
        new_status = "done"
    elif any(s == "in_progress" for s in statuses):
        new_status = "in_progress"
    elif any(s == "block" for s in statuses):
        new_status = "block"
    elif all(s == "review" for s in statuses):
        new_status = "review"
    elif any(s == "review" for s in statuses):
        new_status = "review"
    elif any(s == "triage" for s in statuses):
        # Sub-Tasks muessen erst in Todo/InProgress sein
        pass
    # Bug 3 Fix: Status-Setter via Helper (Audit-Pflicht)
    _set_task_status(parent, new_status, agent="kanban-operator", reason="aggregate_subtask_status", subtask_statuses=statuses)
    _save_json(KANBAN_DIR / "tasks.json", tasks)
    return {
        "ok": True,
        "parent_id": task_id,
        "old_status": old_status,
        "new_status": new_status,
        "subtask_count": len(subtasks),
        "subtask_statuses": statuses,
    }


# ─── Automatisierter Task-Workflow (CIO + PI-Worker + Auto-Review) ─────────────────

def _auto_review_task(task: dict) -> dict:
    """Automatischer Review-Prozess fuer eine Task.

    Prueft:
    - Security: Beschreibungs-Analyse (NALABS-like)
    - Architektur: Passt zu OpenBrain-Vorgaben (Heuristik)
    - Schnittstellen: API-Design (Heuristik)
    - Dokumentation: Hat Task description?

    Returns: { ok, issues, suggestions }
    """
    issues = []
    suggestions = []
    description = task.get("description", "")
    title = task.get("title", "")
    text = f"{title} {description}".lower()
    # 1. Security-Check (einfache Heuristik)
    security_keywords = ["auth", "password", "token", "secret", "key", "encrypt", "ssl", "tls"]
    if any(kw in text for kw in security_keywords):
        if "verschlüssel" not in text and "encrypt" not in text and "hash" not in text and "bcrypt" not in text and "argon" not in text:
            issues.append({"category": "security", "severity": "high", "message": "Security-relevanter Task: Verschluesselung/Hashing fehlt in der Beschreibung"})
    # 2. Architektur-Check
    arch_keywords = ["api", "endpoint", "service", "module", "component", "klasse", "class"]
    if any(kw in text for kw in arch_keywords):
        if "architektur" not in text and "architecture" not in text and "design" not in text and "pattern" not in text:
            suggestions.append({"category": "architecture", "message": "API/Service-Task: Architektur-Design dokumentieren (Pattern, Layer)"})
    # 3. Schnittstellen-Check
    if any(kw in text for kw in ["api", "endpoint", "interface", "schnitstelle"]):
        if "openapi" not in text and "swagger" not in text and "request" not in text and "response" not in text and "json" not in text:
            issues.append({"category": "interface", "severity": "medium", "message": "API/Schnittstellen-Task: Request/Response-Format und OpenAPI-Spec fehlen"})
    # 4. Dokumentations-Check
    if not description or len(description) < 30:
        issues.append({"category": "documentation", "severity": "high", "message": "Beschreibung zu kurz oder fehlt — Code ohne Doku ist nicht review-faehig"})
    if "readme" not in text and "doc" not in text and "kommentar" not in text and "comment" not in text:
        suggestions.append({"category": "documentation", "message": "README/Kommentare im Code ergaenzen"})
    # 5. Success-Criteria
    if not task.get("success_criteria") or len(task["success_criteria"]) == 0:
        issues.append({"category": "definition", "severity": "high", "message": "Keine Success-Criteria definiert — Task ist nicht messbar"})
    # Score
    high = sum(1 for i in issues if i.get("severity") == "high")
    medium = sum(1 for i in issues if i.get("severity") == "medium")
    ok = high == 0 and medium == 0
    return {
        "ok": ok,
        "issues": issues,
        "suggestions": suggestions,
        "score": "ok" if ok else ("block" if high > 0 else "review"),
        "issue_counts": {"high": high, "medium": medium, "low": 0},
    }


@router.post("/tasks/{task_id}/workflow")
async def task_workflow_action(task_id: str, req: dict, _user: str = Depends(require_auth)) -> dict:
    """Fuehrt eine Workflow-Action auf einer Task aus.

    Actions:
    - "claim": Triage -> Todo + automatisch in_progress (PI-Worker uebernimmt)
    - "submit_review": In Progress -> Review (fuehrt Auto-Review aus)
                  -> Done (OK) oder zurueck zu In Progress (Fail, iteration++)
    - "cio_approve": Done (bleibt Done, CIO-Approved-Flag)
    - "cio_reject": Done -> Todo (Standard) oder In Progress (req.target=in_progress)
    - "block": Setzt Status auf block (mit reason)
    """
    tasks = _load_json(KANBAN_DIR / "tasks.json")
    t = next((t for t in tasks if t["id"] == task_id), None)
    if not t:
        raise HTTPException(404, "Task not found")
    action = req.get("action", "")
    now = _now()
    if action == "claim":
        # Triage -> Todo -> In Progress (PI-Worker uebernimmt)
        if t["status"] not in ("triage", "todo"):
            raise HTTPException(400, f"Task kann nicht 'claim' von Status '{t['status']}'")
        # Bug 3 Fix: Status-Setter via Helper (Audit-Pflicht)
        _set_task_status(t, "in_progress", agent="pi-worker", reason="workflow:claim")
        t["claimed_at"] = now
        t["assigned_role"] = t.get("assigned_role") or "pi-coder"
        result = {"action": "claim", "new_status": "in_progress", "message": f"PI-Worker hat Task uebernommen."}
    elif action == "submit_review":
        # In Progress -> Review (Auto-Review)
        if t["status"] != "in_progress":
            raise HTTPException(400, f"Task kann nicht 'submit_review' von Status '{t['status']}'")
        review = _auto_review_task(t)
        t["last_review"] = {**review, "reviewed_at": now}
        if review["ok"]:
            # OK -> Done (Bug 3 Fix: Status-Setter via Helper)
            _set_task_status(t, "done", agent="pi-worker", reason="auto_review_ok", iteration=t.get("iteration_count", 0))
            t["completed_at"] = now
            result = {"action": "submit_review", "new_status": "done", "review_ok": True, "message": "Auto-Review bestanden -> Done."}
        else:
            # Fail -> zurueck zu In Progress (Iteration++)
            t["iteration_count"] = t.get("iteration_count", 0) + 1
            # Bug 3 Fix: Status-Setter via Helper (Audit-Pflicht)
            _set_task_status(t, "in_progress", agent="pi-worker", reason="auto_review_fail", issues=review.get("issue_counts", {}))
            result = {"action": "submit_review", "new_status": "in_progress", "review_ok": False, "message": f"Auto-Review fehlgeschlagen ({review['issue_counts']['high']} kritisch, {review['issue_counts']['medium']} mittel) -> Iteration {t['iteration_count']}."}
    elif action == "cio_approve":
        if t["status"] != "done":
            raise HTTPException(400, f"Task muss 'done' sein fuer CIO-Approve")
        t["cio_approved"] = True
        t["cio_approved_at"] = now
        t["updated_at"] = now
        result = {"action": "cio_approve", "new_status": "done", "message": "CIO hat Task abgenommen."}
    elif action == "cio_reject":
        if t["status"] != "done":
            raise HTTPException(400, f"Task muss 'done' sein fuer CIO-Reject")
        target = req.get("target", "todo")
        if target not in ("todo", "in_progress", "triage"):
            target = "todo"
        t["cio_approved"] = False
        # Bug 3 Fix: Status-Setter via Helper (Audit-Pflicht)
        _set_task_status(t, target, agent="cio", reason=f"cio_reject: {req.get('reason', 'kein Grund')}")
        t["cio_reject_reason"] = req.get("reason", "")
        result = {"action": "cio_reject", "new_status": target, "message": f"CIO hat Task abgelehnt -> {target}."}
    elif action == "block":
        reason = req.get("reason", "Manuell blockiert")
        # Bug 3 Fix: Status-Setter via Helper (Audit-Pflicht)
        _set_task_status(t, "block", agent="user", reason=reason)
        t["block_reason"] = reason
        result = {"action": "block", "new_status": "block", "message": f"Task blockiert: {reason}"}
    elif action == "tester_ok":
        # Review -> Block + auto-create CIO-Sub-Task (in Todo)
        if t["status"] != "review":
            raise HTTPException(400, f"Task muss 'review' sein fuer tester_ok, ist aber '{t['status']}'")
        previous_status = t["status"]
        # Bug 3 Fix: Status-Setter via Helper (Audit-Pflicht)
        _set_task_status(t, "block", agent="pi-tester", reason="tester_ok: review bestanden, warte auf CIO-Freigabe")
        t["tester_passed_at"] = now
        # Auto-Create CIO-Sub-Task
        cio_sub = {
            "id": _id(),
            "project_id": t.get("project_id", ""),
            "title": f"[CIO-APPROVAL] Freigabe fuer '{t.get('title', '?')[:60]}'",
            "description": (
                f"**CIO-Freigabe erforderlich fuer Task {t['id']}**\n\n"
                f"**Original-Task:** {t.get('title', '?')}\n\n"
                f"**Tester-Ergebnis:** OK (Review bestanden)\n\n"
                f"**Review-Notes:** {t.get('last_review', {}).get('reviewed_at', 'keine')}\n\n"
                f"**Action noetig:** Task pruefen + freigeben oder ablehnen."
            ),
            "status": "todo",
            "priority": t.get("priority", 75),
            "assigned_role": "CIO",
            "success_criteria": [
                "Pruefen, ob die Implementation korrekt ist",
                "Entweder 'cio_approve' oder 'cio_reject' ausfuehren",
                "Bei Approve: Original-Task -> done"
            ],
            "parent_id": t["id"],
            "child_ids": [],
            "references": [t["id"]],
            "requirement_ref": t.get("requirement_ref"),
            "tags": ["cio-approval", "sub-task", "auto-created"],
            "created_at": now,
            "updated_at": now,
            "order": len(tasks),
            "iteration_count": 0,
            "needs_breakdown": False,
            "sub_agent": None,
            "review_model": "minimax-m3",
            "tools": ["read", "write"],
            "emergency": False,
        }
        tasks.append(cio_sub)
        # Parent-Referenz aktualisieren
        if t.get("child_ids") is None:
            t["child_ids"] = []
        t["child_ids"].append(cio_sub["id"])
        result = {
            "action": "tester_ok",
            "new_status": "block",
            "previous_status": previous_status,
            "cio_subtask_id": cio_sub["id"],
            "cio_subtask_title": cio_sub["title"],
            "message": f"Tester OK -> Block + CIO-Sub-Task {cio_sub['id'][:12]} erstellt.",
        }
    elif action == "tester_reject":
        # Review -> In Progress (Fix-Loop)
        if t["status"] != "review":
            raise HTTPException(400, f"Task muss 'review' sein fuer tester_reject, ist aber '{t['status']}'")
        # Bug 3 Fix: Status-Setter via Helper (Audit-Pflicht)
        _set_task_status(t, "in_progress", agent="pi-tester", reason=f"tester_reject: {req.get('reason', 'Tester hat Issues gefunden')}")
        t["tester_rejected_at"] = now
        t["tester_reject_reason"] = req.get("reason", "Tester hat Issues gefunden")
        t["iteration_count"] = t.get("iteration_count", 0) + 1
        result = {
            "action": "tester_reject",
            "new_status": "in_progress",
            "message": f"Tester REJECT -> zurueck zu In Progress (Iteration {t['iteration_count']}).",
        }
    else:
        raise HTTPException(400, f"Unbekannte Action: {action}. Erlaubt: claim, submit_review, cio_approve, cio_reject, block, tester_ok, tester_reject")
    _add_history(t, f"workflow_{action}", agent=action.split("_")[0], details=result)
    _save_json(KANBAN_DIR / "tasks.json", tasks)
    return {"ok": True, "task_id": task_id, "result": result}


@router.get("/tasks/{task_id}/stats")
async def get_task_stats(task_id: str, _user: str = Depends(require_auth)) -> dict:
    """Aggregierte Statistiken einer Task: tokens, cost, model, duration."""
    tasks = _load_json(KANBAN_DIR / "tasks.json")
    t = next((t for t in tasks if t["id"] == task_id), None)
    if not t:
        raise HTTPException(404, "Task not found")
    return _aggregate_task_stats(t)


@router.get("/tasks/{task_id}/history")
async def get_task_history(task_id: str, _user: str = Depends(require_auth)) -> dict:
    """Vollstaendige History einer Task."""
    tasks = _load_json(KANBAN_DIR / "tasks.json")
    t = next((t for t in tasks if t["id"] == task_id), None)
    if not t:
        raise HTTPException(404, "Task not found")
    return {
        "task_id": task_id,
        "history": t.get("history", []),
        "stats": _aggregate_task_stats(t),
    }


@router.get("/tasks/{task_id}/review")
async def get_task_review(task_id: str, _user: str = Depends(require_auth)) -> dict:
    """Letzten Auto-Review einer Task abfragen."""
    tasks = _load_json(KANBAN_DIR / "tasks.json")
    t = next((t for t in tasks if t["id"] == task_id), None)
    if not t:
        raise HTTPException(404, "Task not found")
    return {
        "task_id": task_id,
        "title": t.get("title"),
        "status": t.get("status"),
        "iteration_count": t.get("iteration_count", 0),
        "cio_approved": t.get("cio_approved", False),
        "last_review": t.get("last_review"),
        "block_reason": t.get("block_reason"),
        "cio_reject_reason": t.get("cio_reject_reason"),
    }


@router.post("/tasks/bulk-triage/{project_id}")
async def bulk_set_tasks_to_triage(project_id: str, _user: str = Depends(require_auth)) -> dict:
    """Setzt alle Tasks eines Projekts auf status='triage'."""
    tasks = _load_json(KANBAN_DIR / "tasks.json")
    count = 0
    for t in tasks:
        if t.get("project_id") == project_id:
            # Bug 3 Fix: Status-Setter via Helper (Audit-Pflicht)
            _set_task_status(t, "triage", agent="system", reason="bulk_set_tasks_to_triage")
            count += 1
    _save_json(KANBAN_DIR / "tasks.json", tasks)
    return {"ok": True, "project_id": project_id, "updated": count}


@router.put("/tasks/{task_id}/iterate")
async def iterate_task(task_id: str, req: dict, _user: str = Depends(require_auth)) -> Task:
    """Iterative Task-Verbesserung: User-Feedback → Task-Updates."""
    tasks = _load_json(KANBAN_DIR / "tasks.json")
    t = next((t for t in tasks if t["id"] == task_id), None)
    if not t:
        raise HTTPException(404, "Task not found")

    feedback = req.get("feedback", "")
    clarification = req.get("clarification", "")

    # Task verbessern basierend auf Feedback
    t["iteration_count"] = t.get("iteration_count", 0) + 1
    if feedback:
        t["description"] += f"\n\n**Iteration {t['iteration_count']}:**\n{feedback}"
    if clarification:
        t["description"] += f"\n\n**Rückfrage:** {clarification}"
    t["updated_at"] = _now()

    _save_json(KANBAN_DIR / "tasks.json", tasks)
    return Task(**t)


# ─── KPIs ──────────────────────────────────────────────────────────

@router.get("/kpis/{project_id}")
async def get_kpis(project_id: str, _user: str = Depends(require_auth)) -> dict:
    _ensure_dir()
    tasks = _load_json(KANBAN_DIR / "tasks.json")
    project_tasks = [t for t in tasks if t.get("project_id") == project_id]

    total = len(project_tasks)
    done = sum(1 for t in project_tasks if t.get("status") == "done")
    in_progress = sum(1 for t in project_tasks if t.get("status") == "in_progress")
    blocked = sum(1 for t in project_tasks if t.get("status") == "blocked")
    avg_iterations = sum(t.get("iteration_count", 0) for t in project_tasks) / max(total, 1)
    completion_rate = (done / max(total, 1)) * 100

    kpis = [
        {"name": "Task Completion Rate", "value": round(completion_rate, 1), "target": 80.0, "unit": "%", "category": "efficiency"},
        {"name": "Avg Iterations per Task", "value": round(avg_iterations, 1), "target": 3.0, "unit": "iterations", "category": "quality"},
        {"name": "Blocked Tasks", "value": float(blocked), "target": 0.0, "unit": "tasks", "category": "speed"},
        {"name": "Active Tasks", "value": float(in_progress), "target": 5.0, "unit": "tasks", "category": "speed"},
        {"name": "Total Tasks", "value": float(total), "target": 20.0, "unit": "tasks", "category": "efficiency"},
        {"name": "Task Health Score", "value": round(max(0, 100 - (blocked * 10) - max(0, avg_iterations - 2) * 5), 1), "target": 80.0, "unit": "%", "category": "quality"},
    ]
    return {"kpis": kpis, "project_id": project_id}


@router.post("/kpis/{project_id}")
async def record_kpi(project_id: str, req: dict, _user: str = Depends(require_auth)) -> dict:
    _ensure_dir()
    kpis = _load_json(KANBAN_DIR / "kpis.json")
    kpi = KpiMetric(
        id=_id(), project_id=project_id,
        name=req["name"], value=req["value"],
        target=req.get("target", 100),
        unit=req.get("unit", "%"),
        category=req.get("category", "efficiency"),
        timestamp=_now(),
    )
    kpis.append(kpi.model_dump())
    _save_json(KANBAN_DIR / "kpis.json", kpis)
    return kpi.model_dump()
