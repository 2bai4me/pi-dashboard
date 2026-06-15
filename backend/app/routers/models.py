"""Model-Liste, Provider-Liste, Model-Switch."""
from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_auth
from ..config import settings
from ..utils import read_json, write_json

router = APIRouter(prefix="/api/models", tags=["models"])


class ModelInfo(BaseModel):
    id: str
    provider: str
    full_id: str
    context_window: int | None = None
    reasoning: bool | None = None
    input: list[str] | None = None
    enabled: bool = False
    is_default: bool = False
    input_per_1m: float | None = None
    output_per_1m: float | None = None
    price_source: str | None = None
    price_last_updated: str | None = None


class ProviderInfo(BaseModel):
    name: str
    api: str | None
    base_url: str | None
    model_count: int
    has_key: bool
    has_pricing: bool = False  # NEU


@router.get("", response_model=list[ModelInfo])
async def list_models(_user: str = Depends(require_auth)) -> list[ModelInfo]:
    cfg = read_json(settings.models_json, {}) or {}
    settings_data = read_json(settings.settings_json, {}) or {}
    enabled = set(settings_data.get("enabledModels", []) or [])
    default = settings_data.get("defaultModel") or ""

    out: list[ModelInfo] = []
    providers = cfg.get("providers", {})
    for prov_name, prov in providers.items():
        pricing_map = prov.get("pricing", {}) or {}
        for m in prov.get("models", []) or []:
            full_id = f"{prov_name}/{m['id']}"
            # Pricing-Lookup: exakter Match, dann Default
            p = pricing_map.get(m["id"]) or pricing_map.get("default") or {}
            out.append(ModelInfo(
                id=m["id"],
                provider=prov_name,
                full_id=full_id,
                context_window=m.get("contextWindow"),
                reasoning=m.get("reasoning"),
                input=m.get("input"),
                enabled=full_id in enabled,
                is_default=(full_id == default),
                input_per_1m=p.get("input_per_1m"),
                output_per_1m=p.get("output_per_1m"),
                price_source=p.get("source"),
                price_last_updated=p.get("last_updated"),
            ))
    return out


@router.get("/providers", response_model=list[ProviderInfo])
async def list_providers(_user: str = Depends(require_auth)) -> list[ProviderInfo]:
    cfg = read_json(settings.models_json, {}) or {}
    auth = read_json(settings.auth_json, {}) or {}
    out: list[ProviderInfo] = []
    for name, prov in (cfg.get("providers") or {}).items():
        # heuristisch: hat Key, wenn apiKey gesetzt (oder env-var)
        has_key = bool(prov.get("apiKey")) or bool(prov.get("authHeader"))
        # auth.json kann Provider-Keys enthalten
        if isinstance(auth, dict) and name in auth:
            has_key = has_key or bool(auth[name])
        has_pricing = bool(prov.get("pricing"))
        out.append(ProviderInfo(
            name=name,
            api=prov.get("api"),
            base_url=prov.get("baseUrl"),
            model_count=len(prov.get("models", []) or []),
            has_key=has_key,
            has_pricing=has_pricing,
        ))
    return out


class SetDefaultRequest(BaseModel):
    model_id: str  # z.B. "minimax-direct/minimax-m3"


@router.post("/default")
async def set_default_model(req: SetDefaultRequest, _user: str = Depends(require_auth)) -> dict:
    if "/" not in req.model_id:
        raise HTTPException(400, "model_id must be in 'provider/model' format")
    provider, model_id = req.model_id.split("/", 1)
    current = read_json(settings.settings_json, {}) or {}
    current["defaultModel"] = req.model_id
    current["defaultProvider"] = provider
    # ensure in enabled list
    enabled = set(current.get("enabledModels", []) or [])
    enabled.add(req.model_id)
    current["enabledModels"] = sorted(enabled)
    write_json(settings.settings_json, current)
    return {"ok": True, "defaultModel": req.model_id}


@router.post("/toggle")
async def toggle_model(req: SetDefaultRequest, _user: str = Depends(require_auth)) -> dict:
    current = read_json(settings.settings_json, {}) or {}
    enabled = list(current.get("enabledModels", []) or [])
    if req.model_id in enabled:
        enabled.remove(req.model_id)
        new_state = False
    else:
        enabled.append(req.model_id)
        new_state = True
    current["enabledModels"] = sorted(set(enabled))
    write_json(settings.settings_json, current)
    return {"ok": True, "model_id": req.model_id, "enabled": new_state}


# ─── Pricing-Management (Pro Modell + Auto-Update) ─────────────────────

# Statische Preisdatenbank (USD pro 1M Tokens, Stand 15.06.2026).
# Quelle: https://platform.minimax.io/docs/guides/pricing-paygo
# Hinweis: Beim Modell-Wechsel / Refresh wird dieser Wert als Default
# uebernommen, kann aber im UI pro Modell ueberschrieben werden.
KNOWN_MODEL_PRICING: dict[str, dict] = {
    # MiniMax-Familie (50% off launch promo)
    "minimax-direct/minimax-m3":  {"input_per_1m": 0.30, "output_per_1m": 1.20, "source": "https://platform.minimax.io/docs/guides/pricing-paygo"},
    "minimax-direct/minimax-m2.7":{"input_per_1m": 0.30, "output_per_1m": 1.20, "source": "https://platform.minimax.io/docs/guides/pricing-paygo"},
    "minimax-direct/minimax-m2.5":{"input_per_1m": 0.15, "output_per_1m": 1.08, "source": "https://platform.minimax.io/docs/guides/pricing-paygo"},
    # Ollama (lokal, keine Kosten)
    "ollama/gemma4:12b":         {"input_per_1m": 0.0,  "output_per_1m": 0.0,  "source": "local"},
    "ollama/gemma3:4b":          {"input_per_1m": 0.0,  "output_per_1m": 0.0,  "source": "local"},
    "ollama/gemma4-long:latest": {"input_per_1m": 0.0,  "output_per_1m": 0.0,  "source": "local"},
    "ollama/qwen3.6:latest":     {"input_per_1m": 0.0,  "output_per_1m": 0.0,  "source": "local"},
    # OpenRouter (Beispielwerte, genaue Preise siehe openrouter.ai/models)
    "openrouter/anthropic/claude-sonnet-4": {"input_per_1m": 3.0, "output_per_1m": 15.0, "source": "https://openrouter.ai/models"},
    "openrouter/minimax/minimax-m3":        {"input_per_1m": 0.30, "output_per_1m": 1.20, "source": "https://openrouter.ai/minimax/minimax-m3"},
}


class PricingUpdateRequest(BaseModel):
    """Manuelles Pricing-Update pro Provider/Modell."""
    provider: str
    model_id: str | None = None  # wenn None: Default des Providers
    input_per_1m: float
    output_per_1m: float
    note: str | None = None


@router.get("/pricing")
async def get_pricing(_user: str = Depends(require_auth)) -> dict:
    """Liefert aktuelle Provider-Preise (input/output pro 1M Tokens)."""
    cfg = read_json(settings.models_json, {}) or {}
    providers = cfg.get("providers", {}) or {}
    out: dict = {}
    for prov_name, prov in providers.items():
        pricing_map = prov.get("pricing", {}) or {}
        out[prov_name] = {
            "models": {
                model_key: {
                    "input_per_1m":  p.get("input_per_1m", 0),
                    "output_per_1m": p.get("output_per_1m", 0),
                    "currency":      p.get("currency", "USD"),
                    "source":        p.get("source", "unknown"),
                    "last_updated":  p.get("last_updated"),
                    "note":          p.get("note", ""),
                }
                for model_key, p in pricing_map.items()
            }
        }
    return out


@router.post("/pricing/refresh")
async def refresh_pricing(_user: str = Depends(require_auth)) -> dict:
    """Aktualisiert ALLE Provider-Preise aus der statischen Preisdatenbank.

    Aktionen pro Provider:
    1. Lookup in KNOWN_MODEL_PRICING (vollqualifiziert: "provider/model")
    2. Falls gefunden: input_per_1m, output_per_1m, source, last_updated ueberschreiben
    3. last_updated = aktuelle Server-Zeit
    4. Wenn KEIN Match: bisherigen Wert beibehalten (manuelle Konfig nicht ueberschreiben)
    """
    cfg = read_json(settings.models_json, {}) or {}
    providers = cfg.get("providers", {}) or {}
    updated: list[dict] = []
    skipped: list[dict] = []
    now_iso = datetime.now().isoformat(timespec="seconds")
    for prov_name, prov in providers.items():
        pricing_map = prov.setdefault("pricing", {})
        for m in (prov.get("models") or []):
            model_id = m.get("id", "")
            full_id = f"{prov_name}/{model_id}"
            if full_id in KNOWN_MODEL_PRICING:
                ref = KNOWN_MODEL_PRICING[full_id]
                old = pricing_map.get(model_id, {})
                pricing_map[model_id] = {
                    "input_per_1m":  ref["input_per_1m"],
                    "output_per_1m": ref["output_per_1m"],
                    "currency":      old.get("currency", "USD"),
                    "source":        ref["source"],
                    "last_updated":  now_iso,
                    "note":          old.get("note", ""),
                }
                updated.append({
                    "provider": prov_name,
                    "model":    model_id,
                    "input_per_1m":  ref["input_per_1m"],
                    "output_per_1m": ref["output_per_1m"],
                })
            else:
                skipped.append({"provider": prov_name, "model": model_id, "reason": "not_in_known_pricing"})
    cfg["providers"] = providers
    write_json(settings.models_json, cfg)
    return {
        "ok": True,
        "updated_count": len(updated),
        "skipped_count": len(skipped),
        "updated": updated,
        "skipped": skipped,
        "refreshed_at": now_iso,
    }


@router.post("/pricing/update")
async def update_pricing(req: PricingUpdateRequest, _user: str = Depends(require_auth)) -> dict:
    """Manuelles Override pro Provider/Modell (z.B. bei Sonderkonditionen)."""
    cfg = read_json(settings.models_json, {}) or {}
    providers = cfg.get("providers", {}) or {}
    if req.provider not in providers:
        raise HTTPException(404, f"Provider '{req.provider}' nicht gefunden")
    prov = providers[req.provider]
    pricing_map = prov.setdefault("pricing", {})
    key = req.model_id or "default"
    pricing_map[key] = {
        "input_per_1m":  req.input_per_1m,
        "output_per_1m": req.output_per_1m,
        "currency":      "USD",
        "source":        "manual",
        "last_updated":  datetime.now().isoformat(timespec="seconds"),
        "note":          req.note or "",
    }
    cfg["providers"] = providers
    write_json(settings.models_json, cfg)
    return {
        "ok": True,
        "provider": req.provider,
        "model":    key,
        "input_per_1m":  req.input_per_1m,
        "output_per_1m": req.output_per_1m,
    }


# ─── Provider-Management (Custom Provider hinzufügen / löschen / testen) ─────────

class ProviderCreateRequest(BaseModel):
    name: str  # z.B. "anthropic", "openai", "mein-eigener"
    api: str = "openai-completions"  # API-Typ
    base_url: str = ""
    api_key: str = ""
    auth_header: str = ""  # z.B. "x-api-key" statt Authorization
    models: list[dict] = []  # [{"id": "...", "contextWindow": 100000, ...}]


class ProviderUpdateRequest(BaseModel):
    api: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    auth_header: str | None = None
    models: list[dict] | None = None


@router.post("/providers")
async def add_provider(req: ProviderCreateRequest, _user: str = Depends(require_auth)) -> dict:
    """Custom-Provider zur models.json hinzufügen."""
    import re as _re
    name = req.name.strip()
    if not name or not _re.match(r"^[a-zA-Z0-9_-]+$", name):
        raise HTTPException(400, "Provider-Name muss alphanumerisch sein (a-z, 0-9, -, _)")
    cfg = read_json(settings.models_json, {}) or {}
    providers = cfg.get("providers", {}) or {}
    if name in providers:
        raise HTTPException(409, f"Provider '{name}' existiert bereits")
    new_prov: dict = {"api": req.api}
    if req.base_url:
        new_prov["baseUrl"] = req.base_url
    if req.api_key:
        new_prov["apiKey"] = req.api_key
    if req.auth_header:
        new_prov["authHeader"] = req.auth_header
    if req.models:
        new_prov["models"] = req.models
    providers[name] = new_prov
    cfg["providers"] = providers
    write_json(settings.models_json, cfg)
    return {"ok": True, "provider": name, "model_count": len(req.models)}


@router.put("/providers/{name}")
async def update_provider(name: str, req: ProviderUpdateRequest, _user: str = Depends(require_auth)) -> dict:
    """Provider bearbeiten (z.B. API-Key ändern)."""
    cfg = read_json(settings.models_json, {}) or {}
    providers = cfg.get("providers", {}) or {}
    if name not in providers:
        raise HTTPException(404, f"Provider '{name}' nicht gefunden")
    prov = providers[name]
    if req.api is not None:
        prov["api"] = req.api
    if req.base_url is not None:
        if req.base_url:
            prov["baseUrl"] = req.base_url
        else:
            prov.pop("baseUrl", None)
    if req.api_key is not None:
        if req.api_key:
            prov["apiKey"] = req.api_key
        else:
            prov.pop("apiKey", None)
    if req.auth_header is not None:
        if req.auth_header:
            prov["authHeader"] = req.auth_header
        else:
            prov.pop("authHeader", None)
    if req.models is not None:
        prov["models"] = req.models
    providers[name] = prov
    cfg["providers"] = providers
    write_json(settings.models_json, cfg)
    return {"ok": True, "provider": name}


@router.delete("/providers/{name}")
async def delete_provider(name: str, _user: str = Depends(require_auth)) -> dict:
    """Provider löschen. Geschützte Provider (ollama, minimax-direct) können nicht gelöscht werden."""
    PROTECTED = {"ollama", "minimax-direct"}
    if name in PROTECTED:
        raise HTTPException(400, f"Provider '{name}' ist geschützt und kann nicht gelöscht werden. "
                                 f"Verwende PUT um ihn zu bearbeiten.")
    cfg = read_json(settings.models_json, {}) or {}
    providers = cfg.get("providers", {}) or {}
    if name not in providers:
        raise HTTPException(404, f"Provider '{name}' nicht gefunden")
    del providers[name]
    cfg["providers"] = providers
    write_json(settings.models_json, cfg)
    # Auch aus enabledModels entfernen
    s = read_json(settings.settings_json, {}) or {}
    enabled = [e for e in (s.get("enabledModels") or []) if not e.startswith(f"{name}/")]
    s["enabledModels"] = enabled
    if s.get("defaultProvider") == name:
        s["defaultProvider"] = ""
        s["defaultModel"] = ""
    write_json(settings.settings_json, s)
    return {"ok": True, "deleted": name}


@router.post("/providers/{name}/test")
async def test_provider_connection(name: str, _user: str = Depends(require_auth)) -> dict:
    """Testet die Verbindung zu einem Provider durch Aufruf von /v1/models oder /models."""
    import httpx
    cfg = read_json(settings.models_json, {}) or {}
    providers = cfg.get("providers", {}) or {}
    if name not in providers:
        raise HTTPException(404, f"Provider '{name}' nicht gefunden")
    prov = providers[name]
    base_url = prov.get("baseUrl", "").rstrip("/")
    if not base_url:
        return {"ok": False, "error": "Keine baseUrl konfiguriert"}
    api_key = prov.get("apiKey", "")
    auth_header = prov.get("authHeader", "Authorization")
    # Versuche /v1/models (OpenAI-kompatibel) oder /models
    test_urls = []
    if base_url.endswith("/v1"):
        test_urls.append(f"{base_url}/models")
    else:
        test_urls.append(f"{base_url}/v1/models")
        test_urls.append(f"{base_url}/models")
    headers = {"Content-Type": "application/json"}
    if auth_header and api_key:
        if auth_header.lower() == "authorization":
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            headers[auth_header] = api_key
    last_error = None
    for url in test_urls:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(url, headers=headers)
            if r.status_code == 200:
                return {"ok": True, "url": url, "status": r.status_code, "provider": name}
            elif r.status_code == 401:
                return {"ok": False, "error": "401 Unauthorized - API-Key ungültig oder fehlt", "url": url, "status": r.status_code}
            else:
                last_error = f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            last_error = f"{type(e).__name__}: {str(e)[:200]}"
    return {"ok": False, "error": last_error or "Keine Verbindung möglich", "provider": name}


@router.post("/quick-switch")
async def quick_switch_provider(req: dict, _user: str = Depends(require_auth)) -> dict:
    """Schneller Wechsel zwischen bekannten Providern/Modellen.
    Body: {"target": "ollama-gemma4" | "minimax-m3" | "minimax-m2.7" | ...}
    """
    target = req.get("target", "").strip()
    PRESETS = {
        "ollama-gemma4": ("ollama", "gemma4:12b"),
        "ollama-gemma3-4b": ("ollama", "gemma3:4b"),
        "ollama-gemma4-long": ("ollama", "gemma4-long:latest"),
        "minimax-m3": ("minimax-direct", "minimax-m3"),
        "minimax-m2.7": ("minimax-direct", "minimax-m2.7"),
    }
    if target not in PRESETS:
        raise HTTPException(400, f"Unbekanntes Target. Verfügbar: {list(PRESETS.keys())}")
    prov, model = PRESETS[target]
    full_id = f"{prov}/{model}"
    s = read_json(settings.settings_json, {}) or {}
    s["defaultModel"] = full_id
    s["defaultProvider"] = prov
    enabled = set(s.get("enabledModels", []) or [])
    enabled.add(full_id)
    s["enabledModels"] = sorted(enabled)
    write_json(settings.settings_json, s)
    return {"ok": True, "defaultModel": full_id, "switched_to": target}
