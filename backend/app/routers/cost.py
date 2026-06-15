"""Cost-Tracking: Token-Usage, geschätzte Kosten.

Hinweis: pi-coding-agent schreibt Usage-Info in die Sessions. Wir parsen
diese und aggregieren nach Modell, Tag, Tag-Woche.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends

from ..auth import require_auth
from ..config import settings

router = APIRouter(prefix="/api/cost", tags=["cost"])


@router.get("/summary")
async def cost_summary(
    _user: str = Depends(require_auth),
    days: int = 30,
) -> dict:
    """Aggregierte Token/Cost-Stats der letzten N Tage.

    Liefert auch `by_provider` und `savings`, um MiniMax- vs Ollama-Usage
    und geschätzte Ersparnis durch Sub-Agenten sichtbar zu machen.
    """
    cutoff = datetime.now() - timedelta(days=days)
    by_model: dict[str, dict] = defaultdict(lambda: {
        "input_tokens": 0, "output_tokens": 0, "cost": 0.0, "calls": 0,
    })
    by_provider: dict[str, dict] = defaultdict(lambda: {
        "input_tokens": 0, "output_tokens": 0, "cost": 0.0, "calls": 0,
    })
    by_day: dict[str, dict] = defaultdict(lambda: {
        "input_tokens": 0, "output_tokens": 0, "cost": 0.0, "calls": 0,
    })
    total = {"input_tokens": 0, "output_tokens": 0, "cost": 0.0, "calls": 0}
    ollama_calls = 0
    minimax_calls = 0

    sessions_dir = settings.sessions_dir
    if not sessions_dir.exists():
        return {
            "days": days, "total": total,
            "by_model": {}, "by_provider": {}, "by_day": {},
            "savings": {"ollama_calls": 0, "minimax_calls": 0, "estimated_savings_usd": 0.0},
        }

    for f in sessions_dir.iterdir():
        if f.suffix != ".jsonl":
            continue
        try:
            with f.open("r", encoding="utf-8", errors="ignore") as fp:
                for line in fp:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("type") != "message":
                        continue
                    msg = entry.get("message", {})
                    if msg.get("role") != "assistant":
                        continue
                    ts = entry.get("timestamp", "")
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        continue
                    if dt.replace(tzinfo=None) < cutoff:
                        continue
                    usage = msg.get("usage") or {}
                    model = msg.get("model") or "unknown"
                    cost = msg.get("cost", 0.0) or 0.0
                    inp = usage.get("input_tokens", 0) or 0
                    out = usage.get("output_tokens", 0) or 0

                    provider = model.split("/")[0] if "/" in model else "unknown"

                    day = dt.date().isoformat()
                    by_day[day]["input_tokens"] += inp
                    by_day[day]["output_tokens"] += out
                    by_day[day]["cost"] += cost
                    by_day[day]["calls"] += 1

                    by_model[model]["input_tokens"] += inp
                    by_model[model]["output_tokens"] += out
                    by_model[model]["cost"] += cost
                    by_model[model]["calls"] += 1

                    by_provider[provider]["input_tokens"] += inp
                    by_provider[provider]["output_tokens"] += out
                    by_provider[provider]["cost"] += cost
                    by_provider[provider]["calls"] += 1

                    total["input_tokens"] += inp
                    total["output_tokens"] += out
                    total["cost"] += cost
                    total["calls"] += 1

                    if "ollama" in provider:
                        ollama_calls += 1
                    elif "minimax" in provider:
                        minimax_calls += 1
        except OSError:
            continue

    # Ersparnis-Schätzung: jeder Ollama-Call spart ~$0.002 (Durchschnitt M3-Kosten)
    # Bei ~2k tokens/call, ~$1/M input, ~$3/M output für M3
    estimated_savings_usd = round(ollama_calls * 0.01, 4)

    return {
        "days": days,
        "total": total,
        "by_model": dict(sorted(by_model.items(), key=lambda x: -x[1]["cost"])),
        "by_provider": dict(sorted(by_provider.items(), key=lambda x: -x[1]["cost"])),
        "by_day": dict(sorted(by_day.items())),
        "savings": {
            "ollama_calls": ollama_calls,
            "minimax_calls": minimax_calls,
            "estimated_savings_usd": estimated_savings_usd,
            "strategy": "Sub-Agenten (pi-coder/-tester/-reviewer/-fixer) laufen mit ollama/gemma4:12b; nur die Hauptinstanz nutzt minimax-m3",
        },
    }


@router.get("/by-session")
async def cost_by_session(
    _user: str = Depends(require_auth),
    limit: int = 20,
) -> list[dict]:
    """Top-N Sessions nach Kosten."""
    out: list[dict] = []
    sessions_dir = settings.sessions_dir
    if not sessions_dir.exists():
        return []

    for f in sessions_dir.iterdir():
        if f.suffix != ".jsonl":
            continue
        cost = 0.0
        inp = 0
        outp = 0
        calls = 0
        model = None
        try:
            with f.open("r", encoding="utf-8", errors="ignore") as fp:
                for line in fp:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("type") != "message":
                        continue
                    msg = entry.get("message", {})
                    if msg.get("role") != "assistant":
                        continue
                    u = msg.get("usage") or {}
                    cost += (msg.get("cost", 0.0) or 0.0)
                    inp += (u.get("input_tokens", 0) or 0)
                    outp += (u.get("output_tokens", 0) or 0)
                    calls += 1
                    if not model:
                        model = msg.get("model")
        except OSError:
            continue
        out.append({
            "id": f.stem,
            "path": str(f),
            "cost": cost,
            "input_tokens": inp,
            "output_tokens": outp,
            "calls": calls,
            "model": model,
        })

    out.sort(key=lambda x: -x["cost"])
    return out[:limit]
