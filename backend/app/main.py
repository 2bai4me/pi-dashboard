"""Pi Dashboard Backend — FastAPI Main."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .auth import create_token, init_admin_user, require_auth, verify_user
from .config import settings
from .routers import (
    chat as chat_router,
    config as config_router,
    cost as cost_router,
    cron as cron_router,
    env_vars as env_router,
    extensions as ext_router,
    logs as logs_router,
    mcp as mcp_router,
    models as models_router,
    openbrain as ob_router,
    overview,
    sessions as sessions_router,
    skills as skills_router,
    tools as tools_router,
    webhooks as webhooks_router,
)

app = FastAPI(
    title="Pi Dashboard",
    description="Hermes-style dashboard for the local PI coding agent",
    version="0.1.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth beim Start initialisieren
init_admin_user()

# Router (API)
app.include_router(overview.router)
app.include_router(sessions_router.router)
app.include_router(config_router.router)
app.include_router(models_router.router)
app.include_router(tools_router.router)
app.include_router(skills_router.router)
app.include_router(ext_router.router)
app.include_router(cost_router.router)
app.include_router(logs_router.router)
app.include_router(chat_router.router)
app.include_router(cron_router.router)
app.include_router(mcp_router.router)
app.include_router(env_router.router)
app.include_router(webhooks_router.router)
from .routers import roles as roles_router
app.include_router(roles_router.router)
app.include_router(ob_router.router)

from .routers import kanban as kanban_router
from .routers import selfimprovement as selfimp_router
app.include_router(kanban_router.router)
app.include_router(selfimp_router.router)

from .routers import pty as pty_router
from .routers import users as users_router
from .routers import gateway as gateway_router
from .routers import sop as sop_router
app.include_router(pty_router.router)
app.include_router(users_router.router)
app.include_router(gateway_router.router)
app.include_router(sop_router.router)


# ── Auth-Endpoints ───────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
async def login(req: LoginRequest) -> dict:
    if not verify_user(req.username, req.password):
        raise HTTPException(401, "Invalid credentials")
    token = create_token(req.username)
    return {
        "token": token,
        "user": req.username,
        "ttl_hours": settings.JWT_TTL_HOURS,
    }


@app.get("/api/auth/me")
async def me(user: str = Depends(require_auth)) -> dict:
    return {"user": user}


# ── Health ──────────────────────────────────────────────────────────

@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "agent_dir": str(settings.PI_AGENT_DIR),
        "agent_dir_exists": settings.PI_AGENT_DIR.exists(),
    }


# ── Static Frontend (SPA) ──────────────────────────────────────────

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
INDEX_HTML = FRONTEND_DIST / "index.html"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str) -> FileResponse:
        """SPA Catch-All: API-Routen werden vorher gematcht, alles andere ist SPA."""
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        if not INDEX_HTML.exists():
            return FileResponse(str(INDEX_HTML)) if INDEX_HTML.exists() else {"error": "Frontend not built"}
        return FileResponse(str(INDEX_HTML))
else:
    @app.get("/")
    async def root() -> dict:
        return {
            "name": "Pi Dashboard",
            "version": "0.1.0",
            "pi_package": settings.PI_CODING_AGENT_PKG,
            "frontend": "not built — run `cd frontend && npm run build`",
            "api_docs": "/docs",
        }


# ── Startup-Banner ─────────────────────────────────────────────────

@app.on_event("startup")
async def _startup() -> None:
    built = "Yes" if FRONTEND_DIST.exists() else "No (run `cd frontend && npm run build`)"
    print(f"""
+---------------------------------------------------------+
|  Pi Dashboard                                            |
|  http://{settings.HOST}:{settings.PORT}                              |
|  PI Agent Dir: {settings.PI_AGENT_DIR}
|  Frontend built: {built}
|  API Docs: http://{settings.HOST}:{settings.PORT}/docs
|  Login: {settings.ADMIN_USER} / <PI_DASHBOARD_ADMIN_PASSWORD>
+---------------------------------------------------------+
""")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=("--reload" in sys.argv),
        log_level="info",
    )
