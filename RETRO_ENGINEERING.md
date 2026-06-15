# Pi Dashboard — Retro-Engineering & Funktionskatalog

**Projekt:** Pi Dashboard
**Status:** Produktiv (Sprint 4+)
**Erstellt:** 15.06.2026
**Maintainer:** PI-CIO (selbst-bootstrappend)
**Code-Umfang:** ~15.340 Zeilen (Backend: ~6.060, Frontend: ~9.280)

---

## 1. Projekt-Beschreibung

### Vision
Ein **Hermes-Style Web-Dashboard** für den lokalen PI Coding Agent, das alle operativen Aspekte des Agent-Systems in einer einzigen Web-UI zugänglich macht: Agent-Steuerung, Modell-Verwaltung, Tool/Skill/Extension-Übersicht, Kosten-Tracking, Session-Management, Live-Logs, Cron-Jobs, MCP-Server, Webhooks, API-Keys, und ein vollständiges Kanban-Workflow-System für software-entwickelnde Agent-Teams.

### Zielgruppe
- **Primär:** PI-Agent (CEO-digital, CIO, Sub-Agenten pi-coder/pi-tester/pi-reviewer/pi-fixer)
- **Sekundär:** Menschliche Operatoren, die den Agent-Stack überwachen und steuern

### Technologie-Stack
| Schicht | Technologie | Details |
|---|---|---|
| Frontend | React 19 + TypeScript | Vite 8 als Bundler, Lucide-React Icons, TanStack Query |
| Backend | FastAPI 0.136 + Python 3.14 | JWT-Auth, Pydantic-Modelle, Static-Files-Serving |
| Persistenz | JSON-Dateien | `backend/data/kanban/{projects,tasks,requirements,...}.json` |
| Graph-DB | Neo4j (OpenBrain) | Optional — semantische Suche, Task-Graph |
| Auth | JWT mit konfigurierbarem Secret | TTL konfigurierbar (default 24h) |
| Port | 9219 | HTTP-Frontend + Backend in einem Prozess |

### Token-Budget-Schutz (Hybrid-Strategie)
- **Hauptinstanz** (UI/Orchestrierung): `minimax-direct` / `minimax-m3` (kostenpflichtig)
- **Sub-Agenten** (coder/tester/reviewer/fixer): `ollama` / `gemma4:12b` (lokal, **0 Kosten**)
- **Geschätzte Ersparnis:** ~$0.45 pro 4-Phasen-Workflow

---

## 2. Architektur-Übersicht

```
Browser (http://127.0.0.1:9219)
  │
  ├─ Frontend (React SPA, Vite-Build, ~865 KB)
  │   ├─ App.tsx          (Routing)
  │   ├─ Layout.tsx       (Navigation, Sidebar)
  │   ├─ TTSContext.tsx   (Text-to-Speech State)
  │   ├─ GatewayStatusBar (Connection-Status)
  │   └─ pages/           (27 Page-Komponenten)
  │
  ├─ Backend (FastAPI, Single-Process, 131 Endpoints)
  │   ├─ /api/auth/*                (Login, Me)
  │   ├─ /api/overview              (Dashboard-Stats)
  │   ├─ /api/chat                  (Streaming Chat)
  │   ├─ /api/chat-pty              (PTY-Chat)
  │   ├─ /api/sessions              (Session-Liste/Detail/Delete)
  │   ├─ /api/config                (settings.json Editor)
  │   ├─ /api/models                (Provider/Model-Verwaltung)
  │   ├─ /api/tools                 (Built-in Tools)
  │   ├─ /api/skills                (SKILL.md Loader)
  │   ├─ /api/extensions            (Extension-Status)
  │   ├─ /api/cost                  (Token/Cost-Tracking)
  │   ├─ /api/logs                  (Live SSE-Tail)
  │   ├─ /api/cron                  (Cron-Jobs CRUD)
  │   ├─ /api/mcp                   (MCP-Server CRUD)
  │   ├─ /api/webhooks              (Webhook-Management)
  │   ├─ /api/env                   (Environment-Variables)
  │   ├─ /api/roles                 (Roles/Sub-Agents)
  │   ├─ /api/openbrain             (OpenBrain-Integration)
  │   ├─ /api/kanban/*              (42 Kanban-Endpoints)
  │   ├─ /api/sop/*                 (SOP-Verwaltung, 11 Endpoints)
  │   ├─ /api/selfimprovement       (Self-Improvement-Loops)
  │   ├─ /api/users                 (User-Admin)
  │   └─ /api/gateway               (Gateway-Status)
  │
  └─ Persistenz
      ├─ backend/data/              (JSON-Files für Kanban/SOPs/Validation)
      ├─ backend/auth.json          (User-Credentials)
      └─ ~/.pi/agent/               (PI-Agent-Config, Sessions, Skills)
```

---

## 3. Funktionskatalog (Retro-Engineering)

### 3.1 Auth & User-Management
- **Login/Logout**: JWT-basierte Auth, konfigurierbarer Secret + TTL
- **Multi-User-Admin** (`/api/users`): CRUD für Benutzer, Passwort-Reset
- **Default-User**: `admin/admin` (konfigurierbar)
- **Schutz**: Alle Endpoints außer `/api/auth/login` und Static-Files erfordern JWT

### 3.2 Übersicht & System-Status
- **Status-Page** (`/system`): Agent-Version, Modell, CPU/Memory/Disk, Extensions
- **SysInfo-Page**: Erweiterte System-Metriken mit Token-Budget-Schutz-Anzeige
- **Gateway-Status-Bar**: Live-Connection-Indicator

### 3.3 Chat & Sessions
- **Streaming-Chat** (`/api/chat`, SSE): mit dem PI-Agent in Echtzeit
- **PTY-Chat** (`/chat-pty`): Terminal-basierter Agent-Chat
- **Session-Management** (`/sessions`): Liste, Suche, Delete, Detail-View
- **Session-Detail**: Message-Timeline mit Token-Counts

### 3.4 Konfiguration
- **Settings-Editor** (`/config`): Live-JSON-Editor für `settings.json`, `models.json`, `auth.json`
- **Model-Verwaltung** (`/models`): Liste, Toggle, Set-Default, Provider-Status
- **API-Key-Management** (`/apikeys`): Environment-Variablen nach Kategorie, Sensitive-Data-Check

### 3.5 Tools, Skills, Extensions, Roles
- **Tools** (`/tools`): Übersicht der 7 Built-in Tools (read/write/bash/edit/etc.)
- **Skills** (`/skills`): SKILL.md aus `~/.pi/agent/skills/` als Browse-Tree
- **Extensions** (`/extensions`): Status aller Extensions mit Sub-Agent-Überwachung
- **Extension-Detail**: Detaillierte Extension-Info mit Health-Checks
- **Roles** (`/roles`): Definition + Verwaltung der Sub-Agent-Rollen

### 3.6 Kosten & Logs
- **Cost & Usage** (`/cost`): Token/Cost by Provider, Daily-Chart, Savings-Analyse
- **Live-Logs** (`/logs`): SSE-Tail für Session + Extension-Logs mit Filter

### 3.7 Cron & Webhooks
- **Cron-Jobs** (`/cron`): Vollständiges CRUD: Create, Run, Pause, Resume, Delete, Trigger
- **Webhooks** (`/webhooks`): Create, Toggle, Delete mit Secret-Anzeige

### 3.8 MCP & SOPs
- **MCP-Server** (`/mcp`): Add/Remove/Test von MCP-Servern (stdio + SSE)
- **SOPs** (`/sop`): Standard Operating Procedures mit Versions + Quality-Score + Steps

### 3.9 OpenBrain (Graph-DB-Integration)
- **OpenBrain-Search** (`/openbrain`): Semantische Suche im Neo4j-Graph
- **OpenBrain-Graph** (`/openbrain/graph`): Visuelle Darstellung der Thought-Connections
- **Stats**: Anzahl Thoughts, Themen, Tags

### 3.10 Self-Improvement
- **Self-Improvement** (`/selfimprovement`): Verwaltung der Self-Improvement-Loops mit Auto-Detection von Patterns

---

## 4. KANBAN-SYSTEM (Kernstück) — 42 Endpoints

### 4.1 Projekt-Management
- `GET /api/kanban/projects` — Liste aller Projekte
- `POST /api/kanban/projects` — Neues Projekt anlegen
- `DELETE /api/kanban/projects/{id}` — Projekt löschen

### 4.2 Brainstorming (Phase 1)
- `POST /api/kanban/brainstorm/{id}` — User-Eingabe + AI-Antwort
- `GET /api/kanban/brainstorm/{id}/log` — Bestehender Log abrufen
- **5 CEO-Fragen** (Zielgruppe, Problem, Zeit/Budget, Erfolgsmetriken, Abhängigkeiten)
- **9 CIO-Theme-Checks** (Architektur, Tech-Stack, DB, Deployment, Auth, Security, Skalierung, Testing, Backup)
- **OpenBrain-Validierung**: Iterativer Klärungsfragen-Wizard für Vollständigkeit
- **NALABS-Quality-Validierung**: Widerspruchsprüfung + Heuristik-Issues
- **Completeness-Check**: Erkennt unvollständige Antworten, fordert Klärung

### 4.3 Requirements (Phase 2)
- `POST /api/kanban/requirements/generate/{id}` — SRS-Dokument generieren (ISO/IEC/IEEE 29148:2018)
- `GET /api/kanban/requirements/{id}` — Aktuelles SRS abrufen
- `GET /api/kanban/requirements/{id}/versions` — Versions-Historie
- `GET /api/kanban/requirements/{id}/diff` — Unified-Diff zwischen Versionen
- `GET /api/kanban/requirements/{id}/export` — Export als md/html/json/txt
- `POST /api/kanban/requirements/review/{id}` — 9-Schritte-Review-Pipeline
- **20 typisierte Requirements** pro Projekt: FR (Functional), NFR (Non-Functional), IF (Interface), DC (Design-Constraint)

### 4.4 Validation-Pipeline
- `POST /api/kanban/validation/{id}/start` — Validation starten
- `GET /api/kanban/validation/{id}` — Validation-Status
- `POST /api/kanban/validation/{id}/answer` — User-Antwort auf Clarification

### 4.5 Tasks (Phase 3) — 8 Endpoints
- `GET /api/kanban/tasks` — Liste mit Filter `project_id`
- `POST /api/kanban/tasks` — Task erstellen
- `PUT /api/kanban/tasks/{id}/status` — Status ändern (Drag & Drop)
- `PUT /api/kanban/tasks/{id}/priority` — **Prio 0-100 setzen (Watchdog: 100=Notfall)**
- `POST /api/kanban/tasks/bulk-triage/{id}` — Alle Tasks zurück zu Triage
- `PUT /api/kanban/tasks/{id}/iterate` — Iteration-Counter erhöhen
- `POST /api/kanban/tasks/{id}/subtasks` — Sub-Tasks erstellen
- `POST /api/kanban/tasks/{id}/aggregate` — Sub-Task-Status → Parent rollen
- `POST /api/kanban/tasks/{id}/workflow` — Workflow-Aktionen (claim/submit/cio-approve/cio-reject/block)
- `POST /api/kanban/tasks/{id}/review` — Auto-Review durchführen
- `GET /api/kanban/tasks/{id}/review` — Letzten Review-Status abrufen

### 4.6 PERT & Quality
- **PERT-Berechnung** pro Task: optimistic/most_likely/pessimistic → expected + std_dev
- **Parent-Rollup**: 95% CI über alle Sub-Tasks
- **Quality-Score**: NALABS-basierte Bewertung der Brainstorming-Inputs

### 4.7 Implementation (CIO-Approval)
- `POST /api/kanban/implementation/{id}/cio-review` — CIO prüft alle Tasks auf Vollständigkeit
- `POST /api/kanban/implementation/{id}/start` — Implementation-Plan generieren
- `GET /api/kanban/implementation/{id}` — Plan lesen
- `POST /api/kanban/implementation/{id}/step/{step_id}/done` — Step markieren
- **3 Phasen** pro Implementation: Phase 1 Basissystem, Phase 2 Hello-World-App, Phase 3 Tasks aus SRS

### 4.8 Brain-Dev
- `GET /api/kanban/brain-dev` — OpenBrain-Entwicklungs-Wissen (SOA, Microservices, Standards)

### 4.9 KPIs
- `GET /api/kanban/kpis/{id}` — Effizienz-KPIs (Coverage, Iteration-Rate, PERT-Accuracy, etc.)
- `POST /api/kanban/kpis/{id}` — KPIs zurücksetzen/recalculieren

---

## 5. Kanban-Operator (Watchdog-System)

### 5.1 Auto-Claim (Status → in_progress)
- Bei `status="todo"` setzt der Operator automatisch:
  - `assigned_role` (default `pi-coder`)
  - `claimed_at` (Timestamp)
  - Status auf `in_progress`

### 5.2 Notfall-Watchdog (Prio = 100) ⭐ NEU
- **Trigger:** `PUT /tasks/{id}/priority` mit `priority=100`
- **Sofort-Reaktion:**
  - `status` → `in_progress` (außer bei `done`)
  - `emergency=True` Flag
  - `emergency_at` Timestamp
  - `assigned_role` beibehalten oder auf `pi-coder`
  - `claimed_at` Timestamp
- **UI-Indikatoren:**
  - 🚨 Prio-Badge mit roter Pulse-Animation
  - Workflow-Toast "🚨 NOTFALL: ... sofortige Übernahme"
  - Glow-Box-Shadow
- **Beim Runtersetzen** (<100): `emergency=False` + `emergency_cleared_at`

### 5.3 Bulk-Operations
- `bulk-triage`: Alle Tasks eines Projekts auf `status=triage` zurücksetzen

---

## 6. Frontend-UI-Struktur

### 6.1 Kanban-Page (3129 Zeilen — größte Page)
**Tabs:** projects | brainstorm | requirements | tasks | board | kpis | brain-dev

**Global Search (Volltextsuche)** ⭐ NEU:
- Suche in allen Task-Feldern (title, description, success_criteria, tags, references, pert, last_review.issues)
- Highlighting mit `<mark>`-Tags (XSS-sicher via `escapeHtml`)
- Live-Counter + ESC-Reset
- Auto-Expand von Parent-Tasks bei Treffern in Children

**Filter & Sort** ⭐ NEU:
- **Prio-Range** (0-100) mit Doppel-Slider
- **Status-Multi-Select** (Triage/Todo/In Progress/Review/Block/Done)
- **Role-Multi-Select** (dynamisch aus verfügbaren Rollen)
- **Sort-Optionen:** Prio / Verantwortlich / Titel / Status / Erstellt (auf-/absteigend)
- **Live-Counter** "X von Y sichtbar"

**Prio-Badge** ⭐ NEU:
- 🔥 75-100 = rot (kritisch/Notfall)
- 🟧 50-74 = orange (hoch)
- 🔵 25-49 = blau (mittel)
- ⚪ 0-24 = grau (niedrig)
- 🚨 100 = Notfall-Modus mit Pulse-Animation

### 6.2 Andere Pages
| Page | Zweck | Besonderheit |
|---|---|---|
| Sessions | Session-Liste + Detail | Message-Timeline |
| Models | Provider/Model-Toggle | Token-Budget-Anzeige |
| OpenBrain + Graph | Semantische Suche + Visuelle Graph | Neo4j-Integration |
| Self-Improvement | Pattern-Detection für Auto-Improvements | Loop-Verwaltung |
| SOPs | Standard-Operating-Procedures | Versionierung + Quality-Score |
| Logs | Live-Tail via SSE | Filter nach Session/Extension |
| Cost | Token/Cost-Tracking | Daily-Chart + Savings |
| Extensions | Status + Sub-Agent-Überwachung | Health-Checks |
| Roles | Sub-Agent-Definitionen | pi-coder/pi-tester/etc. |

---

## 7. Datenmodell

### 7.1 Task (zentrale Entität)
```python
{
  "id": "abc123",
  "project_id": "proj-xyz",
  "title": "...",
  "description": "...",
  "status": "triage|todo|in_progress|review|block|done",
  "priority": 0..100,           # 100 = Notfall (Watchdog)
  "assigned_role": "pi-coder",
  "success_criteria": ["..."],
  "parent_id": "...",            # für Sub-Tasks
  "child_ids": ["..."],
  "references": ["..."],
  "requirement_ref": "FR-001",   # Traceability zum SRS
  "tags": ["..."],
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "order": 0,
  "iteration_count": 0,
  # Watchdog-Felder:
  "emergency": True,             # Prio=100
  "emergency_at": "ISO8601",
  "emergency_cleared_at": "ISO8601",
  "claimed_at": "ISO8601",
  # PERT:
  "pert": {"opt": 1, "ml": 2, "pess": 6, "expected": 2.5, "std_dev": 0.83},
  "pert_rollup": {...},          # nur bei Parent-Tasks
  # Auto-Review:
  "last_review": {"ok": True, "issues": [...], "suggestions": [...], "reviewed_at": "..."}
}
```

### 7.2 Project
```python
{
  "id": "proj-xyz",
  "name": "...",
  "description": "...",
  "status": "active|archived",
  "brainstorm_log": [...],
  "requirements_file": "path/to/srs.md",
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

### 7.3 Workflow-Status-Machine
```
triage → todo → in_progress → review → done
                              ↓
                            block → in_progress (unblock)
```

### 7.4 Prio-Schema (Initial-Migration: alle bestehenden Tasks → 0)
- **0-24:** Niedrig (grau)
- **25-49:** Mittel (blau)
- **50-74:** Hoch (orange)
- **75-99:** Kritisch (rot)
- **100:** Notfall (🚨 rot pulsierend) → Watchdog-Auto-Claim

---

## 8. Integrationen

### 8.1 OpenBrain (Neo4j)
- Semantic Search für Brainstorming-Validierung
- Brain-Dev-Wissen für Development-Standards
- Task-Graph (visuell)

### 8.2 NALABS
- 295-Zeilen Quality-Rule-Engine (`nalabs_rules.py`)
- Widerspruchsprüfung, Heuristik-Issues, Quality-Score

### 8.3 MCP-Server
- Externe Tools via stdio + SSE
- 4 Endpoints für CRUD + Test

### 8.4 Webhooks
- Outgoing-Webhooks mit Secret-Auth
- 5 Endpoints

---

## 9. Aktuelle Stärken & Schwächen

### ✅ Stärken
- **Vollständige Traceability:** Vision → Brainstorming → Requirements → Tasks → Implementation
- **Multi-Agent-Workflow:** CEO/CIO/Coder/Tester/Reviewer/Fixer als Rollen
- **Selbst-bootstrappend:** Tool baut Tool
- **Token-Budget-Schutz:** Hybrid Cloud/Local
- **Watchdog-System:** Notfall-Eskalation bei Prio=100
- **9-Schritte-Review-Pipeline:** Automatisierte Qualitätssicherung
- **Volltextsuche + Filter + Sort:** Effiziente Task-Verwaltung

### ⚠️ Schwächen / Verbesserungspotenzial
- **TypeScript-Errors:** Mehrere Pages haben `any`-Type-Issues (SopView, Status, SysInfo, Tools, UserAdmin, Webhooks)
- **Bundle-Size:** 865 KB (Vite warnt vor >500 KB Chunks) → Code-Splitting fehlt
- **Persistenz:** JSON-Files statt SQLite/Postgres (Skalierung problematisch)
- **Kein Echtzeit-Multi-User:** WebSocket/SSE-Updates für Multi-User fehlt
- **Tests:** Keine Frontend-Tests (Backend-Tests nur ad-hoc)
- **Documentation:** Außer diesem Retro-Engineering keine zentrale Doku
- **Prio-System ist neu:** Migration noch nicht produktiv getestet
- **Sub-Agent-Loop:** Auto-Claim → in_progress, aber kein Auto-Progress zu review/done

---

## 10. Roadmap-Vorschläge (für die nächste Brainstorming-Runde)

1. **TypeScript-Cleanup:** Alle `any`-Type-Issues systematisch beheben
2. **Code-Splitting:** Vite-Chunks aufteilen (React.lazy + Suspense)
3. **SQLite-Migration:** Persistenz auf SQLite für bessere Skalierung
4. **Echtzeit-Updates:** WebSocket/SSE für Multi-User-Collaboration
5. **Prio-Quick-Buttons:** Bulk-Operations (z.B. "alle In-Progress → 50")
6. **Sub-Agent-Loop-Completion:** Auto-Progress zu review/done nach Auto-Review-OK
7. **Bulk-Implementation:** Multi-Project-Implementation-Plan
8. **Dashboard-Widgets:** Drag-and-Drop-Widgets für Overview-Page
9. **Mobile-Responsive:** Touch-Optimierung für Tablet-Use
10. **Audit-Log:** Vollständige Nachvollziehbarkeit aller Task-Änderungen

---

**Verwendung dieses Dokuments:**
1. Im Pi Dashboard → Projekt "Pi Dashboard" öffnen
2. Im Brainstorming-Tab den **Text aus Abschnitt 1** (Projekt-Beschreibung) einfügen
3. Im Requirements-Tab den **Text aus Abschnitt 3+4** (Funktionskatalog) als initiale Anforderungen generieren
4. Über den Standardprozess (CIO-Review → Implementation-Plan) die nächsten Features umsetzen
