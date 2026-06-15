# Pi Dashboard

**Hermes-Style Web-Dashboard für den lokalen PI Coding Agent**

![Pi Version](https://img.shields.io/badge/PI-0.79.3-blue)
![React](https://img.shields.io/badge/React-19-58c4dc?logo=react)
![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688?logo=fastapi)
![License](https://img.shields.io/badge/license-MIT-green)

```
http://127.0.0.1:9219
Login: admin / admin (konfigurierbar)
```

---

## Features

### Übersicht

| Page | Beschreibung |
|------|-------------|
| **Status** | Agent-Version, Modell, System-Metriken (CPU/Memory/Disk), Extensions-Status |
| **Chat** | Streaming Chat mit dem PI Agent via SSE |
| **Sessions** | Browse, Search, Delete, Detail-Ansicht mit Message-Timeline |
| **Config** | JSON-Editor für `settings.json`, `models.json`, `auth.json` |
| **Models** | Model-Liste, Toggle, Set Default, Provider-Status mit API-Key-Erkennung |
| **Tools** | Übersicht der 7 Built-in Tools |
| **Skills** | SKILL.md aus `~/.pi/agent/skills/` |
| **Extensions** | Status aller 5 Extensions mit Sub-Agent-Überwachung |
| **Cost & Usage** | Token/Cost by Provider, Daily Chart, Savings-Analyse |
| **Logs** | Live-Tail via SSE, Session + Extension Logs |
| **Cron Jobs** | Vollständiges CRUD: Create, Run, Pause, Resume, Delete, Trigger |
| **MCP Servers** | Add/Remove/Test von MCP-Servern (stdio + SSE) |
| **Webhooks** | Create, Toggle, Delete mit Secret-Anzeige |
| **API Keys** | Environment-Variablen nach Kategorie, Sensitive-Data-Check |
| **OpenBrain** | Status, Semantic Search, Stats (wenn konfiguriert) |

### Token-Budget-Schutz (14.06.2026)

| Instanz | Provider | Modell | Kosten |
|---------|----------|--------|--------|
| **Hauptinstanz** (UI, Orchestrierung) | `minimax-direct` | `minimax-m3` | 💰 MiniMax-Tokens |
| **Sub-Agenten** (swarm-spawner: coder/tester/reviewer/fixer) | `ollama` | `gemma4:12b` | 🆓 **0 Kosten (lokal)** |

> **Sub-Agent-Modell wurde am 14.06.2026 von MiniMax auf Ollama Gemma4 12b umgestellt.**  
> Geschätzte Ersparnis: ~$0.45 pro 4-Phasen-Workflow (write → test → review → fix).

---

## Quick Start

### 1. Backend starten

```bash
cd backend
pip install -r requirements.txt
PYTHONIOENCODING=utf-8 python -m uvicorn app.main:app --host 127.0.0.1 --port 9219
```

Oder mit dem Start-Skript:

```bash
cd backend
PYTHONIOENCODING=utf-8 python -m uvicorn app.main:app --host 127.0.0.1 --port 9219 --no-access-log
```

### 2. Frontend bauen (einmalig)

```bash
cd frontend
npm install
npm run build
```

### 3. Im Browser öffnen

```
http://127.0.0.1:9219
```

Login: `admin` / `admin`

### Frontend-Entwicklung (mit Hot-Reload)

```bash
cd frontend
npm run dev
# Vite Dev Server: http://localhost:5173 (proxied zu Backend :9219)
```

---

## Architektur

```
┌──────────────────────────────────────────────────────┐
│                    Browser (SPA)                      │
│          React 19 + TypeScript + Tailwind 4           │
│   TanStack Query │ React Router 7 │ Recharts │ SSE   │
├──────────────────────┬───────────────────────────────┤
│                      │ REST API / SSE                │
├──────────────────────┴───────────────────────────────┤
│                    FastAPI Backend                    │
│               (Python 3.14, Uvicorn)                  │
├──────────────────────────────────────────────────────┤
│  19 API Router · JWT Auth · SSE Log Stream          │
│  File CRUD · Subprocess · Ollama CLI Wrapper        │
├──────────┬─────────────────────────────────┬────────┤
│          │                                 │        │
│    ┌─────┴──────┐                    ┌─────┴──────┐ │
│    │ ~/.pi/agent│                    │ pi CLI     │ │
│    │ settings   │                    │ (Subprocess)│ │
│    │ models     │                    └────────────┘ │
│    │ sessions/  │                                   │
│    │ extensions │                                   │
│    │ skills/    │                                   │
│    └────────────┘                                   │
└──────────────────────────────────────────────────────┘
```

### Tech Stack

| Layer | Technologie |
|-------|------------|
| **Backend Framework** | FastAPI 0.136 |
| **Server** | Uvicorn 0.49 |
| **Auth** | JWT (PyJWT) + bcrypt |
| **Config** | PyYAML + python-dotenv |
| **HTTP** | httpx (für OpenBrain-Proxy) |
| **System** | psutil (CPU/Memory/Disk) |
| **Frontend Framework** | React 19 |
| **Build** | Vite 8 |
| **Routing** | React Router 7 (HashRouter) |
| **Data Fetching** | TanStack React Query 5 |
| **Charts** | Recharts |
| **Icons** | Lucide React |
| **Styling** | Tailwind CSS 4 |
| **Terminal (geplant)** | xterm.js |

---

## API Endpoints

### Overview
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/overview/status` | Agent-Status, Modell, Extensions, Savings |
| GET | `/api/overview/system` | CPU, Memory, Disk, Uptime |
| GET | `/api/overview/version` | PI-Version |
| GET | `/api/overview/extensions` | Extension-Status-Liste |

### Chat
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/chat/sessions` | Chat-Sessions |
| POST | `/api/chat/stream` | SSE-Streaming Chat |

### Sessions
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/sessions` | Session-Liste (limit, sort) |
| GET | `/api/sessions/{id}` | Session-Detail |
| GET | `/api/sessions/{id}/messages` | Messages mit pagination |
| GET | `/api/sessions/search/query` | Volltextsuche |
| DELETE | `/api/sessions/{id}` | Session löschen |
| GET | `/api/sessions/stats/summary` | Session-Statistiken |

### Config
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/config/settings` | settings.json lesen |
| PUT | `/api/config/settings` | settings.json schreiben |
| GET | `/api/config/models` | models.json lesen |
| PUT | `/api/config/models` | models.json schreiben |
| GET | `/api/config/auth` | auth.json lesen (maskiert) |

### Models
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/models` | Alle Modelle mit Status |
| GET | `/api/models/providers` | Provider mit API-Key-Status |
| POST | `/api/models/default` | Default-Modell setzen |
| POST | `/api/models/toggle` | Model Enable/Disable |

### Extensions
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/extensions` | Extension-Liste mit Sub-Agent-Status |
| GET | `/api/extensions/{name}` | Extension-Detail mit SKILL.md |

### Cost & Usage
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/cost/summary` | Kosten by Model/Provider/Day + Savings |
| GET | `/api/cost/by-session` | Top-Sessions by Cost |

### Logs
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/logs/recent` | Letzte Log-Einträge |
| GET | `/api/logs/stream` | SSE-Live-Stream |

### Cron Jobs
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/cron/jobs` | Alle Jobs |
| POST | `/api/cron/jobs` | Job erstellen |
| PUT | `/api/cron/jobs/{id}` | Job aktualisieren |
| DELETE | `/api/cron/jobs/{id}` | Job löschen |
| POST | `/api/cron/jobs/{id}/pause` | Pausieren |
| POST | `/api/cron/jobs/{id}/resume` | Fortsetzen |
| POST | `/api/cron/jobs/{id}/trigger` | Sofort ausführen |

### MCP
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/mcp/servers` | MCP-Server-Liste |
| PUT | `/api/mcp/servers` | MCP-Server speichern |
| POST | `/api/mcp/servers/test` | Verbindung testen |

### Webhooks
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/webhooks` | Webhook-Liste |
| POST | `/api/webhooks` | Webhook erstellen |
| PUT | `/api/webhooks/{id}` | Webhook aktualisieren |
| DELETE | `/api/webhooks/{id}` | Webhook löschen |
| POST | `/api/webhooks/{id}/toggle` | Enable/Disable |

### Environment
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/env/vars` | Bekannte env vars by Kategorie |
| GET | `/api/env/sensitive` | Secret-Leak-Check |

### OpenBrain
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/openbrain/status` | Verbindungsstatus |
| POST | `/api/openbrain/search` | Semantische Suche |
| GET | `/api/openbrain/stats` | Brain-Statistiken |

### Auth
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/auth/login` | JWT-Login |
| GET | `/api/auth/me` | Aktueller User |
| GET | `/api/health` | Health-Check |

---

## Konfiguration

### `.env` (Backend)

| Variable | Default | Beschreibung |
|----------|---------|-------------|
| `PI_DASHBOARD_HOST` | `127.0.0.1` | Bind-Adresse |
| `PI_DASHBOARD_PORT` | `9219` | Port |
| `PI_AGENT_DIR` | `~/.pi/agent` | PI-Agent-Pfad |
| `PI_BIN` | `pi` | PI-Binary |
| `PI_DASHBOARD_JWT_SECRET` | `change-me-...` | JWT Signing-Key |
| `PI_DASHBOARD_ADMIN_USER` | `admin` | Admin-Username |
| `PI_DASHBOARD_ADMIN_PASSWORD` | `admin` | Admin-Passwort |
| `OPENBRAIN_URL` | — | OpenBrain-Server-URL |
| `OPENBRAIN_ACCESS_KEY` | — | OpenBrain-Access-Key |
| `PI_DASHBOARD_CORS_ORIGINS` | `http://localhost:5173,...` | CORS-Origins |

### Extensions

Die folgenden 5 PI-Extensions werden vom Dashboard erkannt und überwacht:

| Extension | Zweck | Status |
|-----------|-------|--------|
| **swarm-spawner** | Spawnt Sub-PI-Instanzen (pi-coder, pi-tester, pi-reviewer, pi-fixer) — **alle auf ollama/gemma4:12b** | ✅ Aktiv |
| **context-workflow** | Stage-Transition (write → test → review → fix → verify) | ✅ Installiert |
| **cost-tracker** | Token-Usage-Tracking | ✅ Installiert |
| **openbrain-bridge** | PI-Session-Events → OpenBrain | ✅ Installiert |
| **git-checkpoint** | Git-Checkpoints vor riskanten Operationen | ✅ Installiert |

---

## Entwicklung

### Verzeichnisstruktur

```
pi-dashboard/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI-App + SPA-Serving
│   │   ├── config.py            # .env-Konfiguration
│   │   ├── auth.py              # JWT + bcrypt
│   │   ├── utils.py             # pi-Subprocess, JSON, Secret-Masking
│   │   └── routers/             # 15 API-Router
│   ├── requirements.txt
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # Router + QueryClient
│   │   ├── Layout.tsx           # Sidebar-Navigation
│   │   ├── api.ts               # API-Client + SSE-Helper
│   │   ├── index.css            # Tailwind 4 + Hermes-Theme
│   │   └── pages/               # 16 Page-Komponenten
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── dist/                    # Gebautes Frontend
└── README.md
```

### Python Syntax-Check

```bash
cd backend
python -m py_compile app/main.py app/config.py app/utils.py app/auth.py app/routers/*.py
```

### TypeScript Check

```bash
cd frontend
npx tsc --noEmit
```

### Production Build

```bash
cd frontend
npm run build
# → dist/ wird automatisch vom Backend ausgeliefert
```

---

## Security

- **JWT-Auth** auf allen API-Endpoints (außer `/api/health` und `/api/auth/login`)
- **Secret-Masking** in Config-Responses (API-Keys werden maskiert ausgeliefert)
- **Path-Traversal-Schutz** in allen File-Operationen
- Standard-Bind auf `127.0.0.1` (localhost-only)
- `--insecure` nicht nötig — das Dashboard läuft per Default nur lokal

---

## Lizenz

MIT

---

## Verwandte Projekte

- [PI Coding Agent](https://github.com/earendil-works/pi) — Der lokale PI-Agent
- [OpenBrain](https://github.com/uwean/openbrain) — Semantischer Gedächtnisspeicher
- [Hermes Agent](https://github.com/NousResearch/hermes-agent) — Inspiration für UI/UX

---

## 🚀 Quickstart (Setup in 5 Minuten)

### 1. Voraussetzungen

- **Node.js** ≥ 20 ([Download](https://nodejs.org))
- **Python** ≥ 3.10 ([Download](https://python.org))
- **PI Coding Agent** global installiert:
  ```bash
  npm install -g --ignore-scripts @earendil-works/pi-coding-agent
  ```
- **PI-Agent-Daten-Verzeichnis** mit Provider-Config: `~/.pi/agent/`
  - `models.json` — Provider + Modelle + API-Keys (siehe [Provider-Setup](#provider-setup))
  - `settings.json` — Default-Modell, Enabled-Models (optional)

### 2. Repository klonen + Backend starten

```bash
git clone https://github.com/2bai4me/pi-dashboard.git
cd pi-dashboard

# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # Linux/macOS
pip install -r requirements.txt
copy .env.example .env           # Windows
# cp .env.example .env           # Linux/macOS
uvicorn app.main:app --host 127.0.0.1 --port 9219
```

### 3. Frontend starten (neues Terminal)

```bash
cd frontend
npm install
npm run dev
```

### 4. Browser öffnen

```
http://127.0.0.1:9219
Login: admin / admin (siehe .env)
```

### Provider-Setup

Das Backend liest Provider-Konfiguration + API-Keys aus `~/.pi/agent/models.json`
zur Laufzeit. Diese Datei ist **NICHT** im Repo (enthält sensible Keys), muss
aber existieren. Mindest-Inhalt:

```json
{
  "providers": {
    "minimax-direct": {
      "api": "openai-completions",
      "apiKey": "sk-cp-DEIN-KEY",
      "baseUrl": "https://api.minimax.io/v1",
      "models": [
        {"id": "minimax-m3", "contextWindow": 1000000, "input": ["text", "image"], "reasoning": true}
      ]
    }
  }
}
```

Preise (USD pro 1M Tokens, Stand 15.06.2026 — 50% off launch promo):
- `minimax-m3`: $0.30 input / $1.20 output
- `ollama/gemma4:12b`: $0 (lokal)

→ Details: siehe [Models-Page](http://127.0.0.1:9219/models) im Dashboard.
