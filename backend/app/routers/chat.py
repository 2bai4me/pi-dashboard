"""Chat: SSE-basierter Chat mit dem PI-Agent (alternativ zu PTY)."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..auth import require_auth
from ..config import settings

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatSession(BaseModel):
    id: str
    name: str | None = None
    created_at: str | None = None
    message_count: int = 0
    model: str | None = None


class SendMessage(BaseModel):
    session_id: str | None = None
    prompt: str
    model: str | None = None
    provider: str | None = None
    thinking_level: str | None = None


@router.get("/sessions", response_model=list[ChatSession])
async def list_chat_sessions(_user: str = Depends(require_auth)) -> list[ChatSession]:
    """Letzte Sessions im Chat-Format."""
    from .sessions import list_sessions
    raw = await list_sessions(_user=_user, limit=20, sort="modified")
    return [
        ChatSession(
            id=s.id,
            name=s.name or s.first_user_message or s.id[:16],
            created_at=s.created_at,
            message_count=s.message_count,
            model=s.model,
        )
        for s in raw
    ]


@router.post("/stream")
async def chat_stream(
    req: SendMessage,
    _user: str = Depends(require_auth),
):
    """SSE-Stream einer PI-Agent-Antwort."""
    return StreamingResponse(
        _stream_chat(req, _user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _stream_chat(req: SendMessage, _user: str) -> str:
    """Streamt PI-Agent-Antwort via pi -p ..."""

    # Session-Dir für diesen Chat
    session_dir = settings.sessions_dir
    session_dir.mkdir(parents=True, exist_ok=True)

    pi_args = [
        "-p", req.prompt,
        "--mode", "json",
    ]
    if req.model:
        if req.provider:
            pi_args.extend(["--provider", req.provider])
        pi_args.extend(["--model", req.model])
    if req.thinking_level:
        pi_args.extend(["--thinking", req.thinking_level])
    if req.session_id:
        pi_args.extend(["--session", req.session_id])

    is_win = os.name == "nt"
    cmd = f"{settings.PI_BIN} {' '.join(pi_args)}" if is_win else [settings.PI_BIN, *pi_args]

    yield f"data: {json.dumps({'type': 'start', 'ts': datetime.now().isoformat()})}\n\n"

    try:
        proc = await asyncio.create_subprocess_exec(
            *([cmd] if is_win else cmd) if not is_win else cmd.split(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PI_OFFLINE": "1", "NO_COLOR": "1"},
            shell=is_win,
        )

        # Stream stdout
        async def _read_stream(stream, stream_name: str):
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip("\n\r")
                if text:
                    yield f"data: {json.dumps({'type': stream_name, 'text': text})}\n\n"

        async def _read_stderr(stream):
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip("\n\r")
                if text:
                    yield f"data: {json.dumps({'type': 'stderr', 'text': text})}\n\n"

        # Process stdout in chunks
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip("\n\r")
            if text:
                yield f"data: {json.dumps({'type': 'response', 'text': text})}\n\n"

        exit_code = await proc.wait()

        # Check stderr for errors
        stderr_text = (await proc.stderr.read()).decode("utf-8", errors="replace").strip()
        if stderr_text and exit_code != 0:
            yield f"data: {json.dumps({'type': 'error', 'text': stderr_text[:500]})}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'exitCode': exit_code})}\n\n"

    except FileNotFoundError:
        yield f"data: {json.dumps({'type': 'error', 'text': f'pi binary not found: {settings.PI_BIN}'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'text': str(e)[:300]})}\n\n"
