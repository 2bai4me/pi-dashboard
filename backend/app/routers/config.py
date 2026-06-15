"""Config: settings.json + models.json lesen/schreiben."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_auth
from ..config import settings
from ..utils import mask_config, read_json, write_json

router = APIRouter(prefix="/api/config", tags=["config"])


class ConfigResponse(BaseModel):
    filename: str
    path: str
    data: dict
    masked: dict


@router.get("/settings", response_model=ConfigResponse)
async def get_settings(_user: str = Depends(require_auth)) -> ConfigResponse:
    data = read_json(settings.settings_json, {}) or {}
    return ConfigResponse(
        filename="settings.json",
        path=str(settings.settings_json),
        data=data,
        masked=mask_config(data),
    )


@router.put("/settings")
async def put_settings(payload: dict, _user: str = Depends(require_auth)) -> dict:
    current = read_json(settings.settings_json, {}) or {}
    # flacher merge für Top-Level Keys
    current.update(payload)
    write_json(settings.settings_json, current)
    return {"ok": True, "path": str(settings.settings_json)}


@router.get("/models", response_model=ConfigResponse)
async def get_models(_user: str = Depends(require_auth)) -> ConfigResponse:
    data = read_json(settings.models_json, {}) or {}
    return ConfigResponse(
        filename="models.json",
        path=str(settings.models_json),
        data=data,
        masked=mask_config(data),
    )


@router.put("/models")
async def put_models(payload: dict, _user: str = Depends(require_auth)) -> dict:
    write_json(settings.models_json, payload)
    return {"ok": True, "path": str(settings.models_json)}


@router.get("/auth", response_model=ConfigResponse)
async def get_auth(_user: str = Depends(require_auth)) -> ConfigResponse:
    data = read_json(settings.auth_json, {}) or {}
    return ConfigResponse(
        filename="auth.json",
        path=str(settings.auth_json),
        data=data,
        masked=mask_config(data),
    )


@router.get("/trust")
async def get_trust(_user: str = Depends(require_auth)) -> dict:
    data = read_json(settings.trust_json, {}) or {}
    return {"path": str(settings.trust_json), "data": data}


@router.get("/all")
async def get_all_configs(_user: str = Depends(require_auth)) -> dict:
    """Alle Config-Files auf einen Blick."""
    return {
        "settings": {
            "path": str(settings.settings_json),
            "exists": settings.settings_json.exists(),
            "size": settings.settings_json.stat().st_size if settings.settings_json.exists() else 0,
        },
        "models": {
            "path": str(settings.models_json),
            "exists": settings.models_json.exists(),
            "size": settings.models_json.stat().st_size if settings.models_json.exists() else 0,
        },
        "auth": {
            "path": str(settings.auth_json),
            "exists": settings.auth_json.exists(),
        },
        "trust": {
            "path": str(settings.trust_json),
            "exists": settings.trust_json.exists(),
        },
    }
