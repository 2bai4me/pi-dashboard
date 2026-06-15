"""Pytest-Konfiguration fuer Backend-Tests.

KRITISCH: PI_AGENT_DIR muss VOR dem Import der App gesetzt werden,
weil `settings.PI_AGENT_DIR` als Path-Objekt beim Modul-Import berechnet wird.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# ── VOR allen Imports: Isolierte Test-Umgebung einrichten ──
_TEST_PI_AGENT_DIR = Path(tempfile.mkdtemp(prefix="pi_dashboard_test_"))
os.environ["PI_AGENT_DIR"] = str(_TEST_PI_AGENT_DIR)
os.environ["PI_DASHBOARD_AUTH_ENABLED"] = "false"
(_TEST_PI_AGENT_DIR / "kanban").mkdir(parents=True, exist_ok=True)
_TASKS_FILE = _TEST_PI_AGENT_DIR / "kanban" / "tasks.json"
_TASKS_FILE.write_text("[]", encoding="utf-8")

# Backend-Pfad in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


import pytest  # noqa: E402


@pytest.fixture
def tasks_file():
    """Liefert den Pfad zur isolierten tasks.json und resettet sie vor jedem Test."""
    _TASKS_FILE.write_text("[]", encoding="utf-8")
    yield _TASKS_FILE


@pytest.fixture
def client():
    """FastAPI TestClient mit dem echten kanban-Router."""
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)
