"""PTY Chat: WebSocket-basierte Terminal-Emulation (xterm.js)."""
from __future__ import annotations

import asyncio
import json
import os
import signal

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..auth import decode_token
from ..config import settings

router = APIRouter()

ACTIVE_TERMINALS: dict[str, dict] = {}


@router.websocket("/api/pty")
async def pty_websocket(ws: WebSocket):
    """WebSocket-Endpoint fuer xterm.js PTY (spawnt `pi` als Subprozess)."""
    await ws.accept()

    # Auth via Query-Parameter
    token = ws.query_params.get("token")
    if not token or not decode_token(token):
        await ws.send_json({"type": "error", "text": "Unauthorized"})
        await ws.close(code=4001)
        return

    user = decode_token(token).get("sub", "unknown")
    terminal_id = ws.query_params.get("id", f"term-{id(ws)}")
    model = ws.query_params.get("model", "")

    await ws.send_json({"type": "info", "text": f"Pi Terminal ({user}) — starting..."})

    # Build pi command
    is_win = os.name == "nt"
    pi_args = ["--no-session"]
    if model:
        pi_args.extend(["--model", model])

    if is_win:
        cmd = f"{settings.PI_BIN} {' '.join(pi_args)}"
    else:
        cmd = [settings.PI_BIN, *pi_args]

    try:
        proc = await asyncio.create_subprocess_exec(
            *([cmd] if is_win else cmd) if not is_win else cmd.split(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, "PI_OFFLINE": "1", "TERM": "xterm-256color"},
            shell=is_win,
        )
    except FileNotFoundError:
        await ws.send_json({"type": "error", "text": f"pi not found: {settings.PI_BIN}"})
        await ws.close()
        return

    ACTIVE_TERMINALS[terminal_id] = {"proc": proc, "user": user}

    # Reader: stdout → WebSocket
    async def reader():
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace")
                await ws.send_text(json.dumps({"type": "output", "text": text}))
        except Exception:
            pass
        finally:
            try:
                await ws.send_json({"type": "exit", "code": await proc.wait()})
            except:
                pass

    # Writer: WebSocket → stdin
    async def writer():
        try:
            while True:
                data = await ws.receive_text()
                msg = json.loads(data)
                if msg.get("type") == "input":
                    proc.stdin.write(msg["text"].encode("utf-8"))
                    await proc.stdin.drain()
                elif msg.get("type") == "resize":
                    pass  # Windows/Unix PTY resize nicht trivial
                elif msg.get("type") == "sigint":
                    if is_win:
                        proc.stdin.write(b"\x03")
                        await proc.stdin.drain()
                    else:
                        proc.send_signal(signal.SIGINT)
        except (WebSocketDisconnect, Exception):
            pass

    tasks = [asyncio.create_task(reader()), asyncio.create_task(writer())]

    try:
        await asyncio.gather(*tasks)
    except Exception:
        pass
    finally:
        # Cleanup
        if terminal_id in ACTIVE_TERMINALS:
            del ACTIVE_TERMINALS[terminal_id]
        try:
            proc.kill()
        except:
            pass
        try:
            await ws.close()
        except:
            pass


@router.get("/api/pty/terminals")
async def list_terminals() -> list[dict]:
    """Liste aktiver Terminals."""
    return [
        {"id": tid, "user": info.get("user", "?"), "alive": info["proc"].returncode is None}
        for tid, info in ACTIVE_TERMINALS.items()
    ]
