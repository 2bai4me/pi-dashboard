"""MCP: Model Context Protocol-Server-Verwaltung."""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_auth
from ..config import settings
from ..utils import read_json, write_json

router = APIRouter(prefix="/api/mcp", tags=["mcp"])

# MCP-Server werden in models.json oder settings.json gespeichert
# Typischer Key: "mcp_servers" oder "mcpServers"


class McpServer(BaseModel):
    name: str
    command: str | None = None
    args: list[str] = []
    url: str | None = None
    env: dict[str, str] = {}
    enabled: bool = True
    transport: str = "stdio"  # "stdio" | "sse" | "oauth"


@router.get("/servers", response_model=list[McpServer])
async def list_mcp_servers(_user: str = Depends(require_auth)) -> list[McpServer]:
    """Liest MCP-Server aus settings.json oder models.json."""
    settings_data = read_json(settings.settings_json, {}) or {}
    models_data = read_json(settings.models_json, {}) or {}

    # Suche in verschiedenen möglichen Locations
    raw = settings_data.get("mcpServers") or settings_data.get("mcp_servers") or {}
    if not raw:
        raw = models_data.get("mcpServers") or models_data.get("mcp_servers") or {}

    out: list[McpServer] = []
    for name, cfg in raw.items():
        if isinstance(cfg, dict):
            out.append(McpServer(
                name=name,
                command=cfg.get("command"),
                args=cfg.get("args", []),
                url=cfg.get("url"),
                env=cfg.get("env", {}),
                enabled=cfg.get("enabled", True),
                transport=cfg.get("transport", "stdio"),
            ))
    return out


class McpServerCreate(BaseModel):
    name: str
    command: str | None = None
    args: list[str] = []
    url: str | None = None
    env: dict[str, str] = {}
    transport: str = "stdio"


@router.put("/servers", response_model=dict)
async def save_mcp_servers(servers: list[McpServerCreate], _user: str = Depends(require_auth)) -> dict:
    """Speichert MCP-Server in settings.json."""
    settings_data = read_json(settings.settings_json, {}) or {}
    mcp_dict = {}
    for s in servers:
        entry = {
            "command": s.command,
            "args": s.args,
            "url": s.url,
            "env": s.env,
            "enabled": True,
            "transport": s.transport,
        }
        mcp_dict[s.name] = entry
    settings_data["mcpServers"] = mcp_dict
    write_json(settings.settings_json, settings_data)
    return {"ok": True, "count": len(servers)}


@router.post("/servers/test")
async def test_mcp_server(req: McpServerCreate, _user: str = Depends(require_auth)) -> dict:
    """Test-Verbindung zu einem MCP-Server (nur connectivity check)."""
    import subprocess, os
    if req.command:
        try:
            result = subprocess.run(
                [req.command, *req.args, "--version"] if req.args else [req.command, "--version"],
                capture_output=True, text=True, timeout=5,
                env={**os.environ, **req.env},
            )
            return {
                "ok": result.returncode == 0,
                "stdout": result.stdout[:200],
                "stderr": result.stderr[:200],
                "exitCode": result.returncode,
            }
        except FileNotFoundError:
            raise HTTPException(400, f"Command not found: {req.command}")
        except Exception as e:
            return {"ok": False, "error": str(e)[:300]}
    elif req.url:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(req.url)
            return {"ok": r.status_code < 500, "status": r.status_code}
        except Exception as e:
            return {"ok": False, "error": str(e)[:300]}
    return {"ok": False, "error": "No command or url specified"}


@router.get("/connections", response_model=list[dict])
async def mcp_connections(_user: str = Depends(require_auth)) -> list[dict]:
    """Prueft alle konfigurierten MCP-Server auf aktive Verbindung."""
    servers = await list_mcp_servers(_user)
    import subprocess, os, httpx
    out: list[dict] = []
    for srv in servers:
        status = "unknown"
        latency_ms: float | None = None
        error: str | None = None
        import time
        start = time.time()
        try:
            if srv.command:
                result = subprocess.run(
                    [srv.command, *srv.args, "--version"] if srv.args else [srv.command, "--version"],
                    capture_output=True, text=True, timeout=5,
                    env={**os.environ, **srv.env},
                )
                status = "connected" if result.returncode == 0 else "error"
                if result.returncode != 0:
                    error = result.stderr[:200]
            elif srv.url:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.get(srv.url)
                status = "connected" if r.status_code < 500 else "error"
            else:
                status = "unknown"
        except subprocess.TimeoutExpired:
            status = "timeout"
            error = "Connection timed out after 5s"
        except FileNotFoundError:
            status = "not_found"
            error = f"Command not found: {srv.command}"
        except Exception as e:
            status = "error"
            error = str(e)[:200]
        latency_ms = round((time.time() - start) * 1000, 1) if status != "unknown" else None
        out.append({
            "name": srv.name,
            "command": srv.command,
            "url": srv.url,
            "transport": srv.transport,
            "status": status,
            "latency_ms": latency_ms,
            "error": error,
        })
    return out
