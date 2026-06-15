"""Webhooks: Verwalte Webhook-Abonnements.

Speichert in settings.json unter `webhooks`.
"""
from __future__ import annotations

import os
import subprocess
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_auth
from ..config import settings
from ..utils import read_json, write_json

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


class Webhook(BaseModel):
    id: str
    name: str
    url: str
    events: list[str] = ["all"]
    enabled: bool = True
    secret: str | None = None
    created_at: str | None = None


class WebhookCreate(BaseModel):
    name: str
    url: str
    events: list[str] = ["all"]


@router.get("", response_model=list[Webhook])
async def list_webhooks(_user: str = Depends(require_auth)) -> list[Webhook]:
    settings_data = read_json(settings.settings_json, {}) or {}
    raw = settings_data.get("webhooks", []) or []
    return [Webhook(**w) for w in raw]


@router.post("", response_model=Webhook)
async def create_webhook(req: WebhookCreate, _user: str = Depends(require_auth)) -> Webhook:
    secret = f"whsec_{uuid.uuid4().hex[:32]}"
    wh = Webhook(
        id=uuid.uuid4().hex[:12],
        name=req.name, url=req.url, events=req.events,
        enabled=True, secret=secret,
        created_at=datetime.now().isoformat(),
    )
    settings_data = read_json(settings.settings_json, {}) or {}
    webhooks = settings_data.get("webhooks", []) or []
    webhooks.append(wh.model_dump())
    settings_data["webhooks"] = webhooks
    write_json(settings.settings_json, settings_data)
    return wh


@router.put("/{webhook_id}")
async def update_webhook(webhook_id: str, req: WebhookCreate, _user: str = Depends(require_auth)) -> Webhook:
    settings_data = read_json(settings.settings_json, {}) or {}
    webhooks = settings_data.get("webhooks", []) or []
    for w in webhooks:
        if w["id"] == webhook_id:
            w.update({"name": req.name, "url": req.url, "events": req.events})
            settings_data["webhooks"] = webhooks
            write_json(settings.settings_json, settings_data)
            return Webhook(**w)
    raise HTTPException(404, "Webhook not found")


@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str, _user: str = Depends(require_auth)) -> dict:
    settings_data = read_json(settings.settings_json, {}) or {}
    webhooks = settings_data.get("webhooks", []) or []
    before = len(webhooks)
    webhooks = [w for w in webhooks if w["id"] != webhook_id]
    if len(webhooks) == before:
        raise HTTPException(404, "Webhook not found")
    settings_data["webhooks"] = webhooks
    write_json(settings.settings_json, settings_data)
    return {"ok": True, "deleted": webhook_id}


@router.post("/{webhook_id}/toggle")
async def toggle_webhook(webhook_id: str, _user: str = Depends(require_auth)) -> dict:
    settings_data = read_json(settings.settings_json, {}) or {}
    webhooks = settings_data.get("webhooks", []) or []
    for w in webhooks:
        if w["id"] == webhook_id:
            w["enabled"] = not w.get("enabled", True)
            settings_data["webhooks"] = webhooks
            write_json(settings.settings_json, settings_data)
            return {"ok": True, "enabled": w["enabled"]}
    raise HTTPException(404, "Webhook not found")
