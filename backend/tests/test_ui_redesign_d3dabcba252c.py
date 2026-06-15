"""Tests fuer Task d3dabcba252c (UI-Redesign Board-Kacheln: Phase-Tracking).

Diese Tests validieren die Backend-Erweiterungen fuer das neue Kachel-Layout:
- Phase-Tracking via phase_started_at Feld
- _set_task_status schreibt phase_completed History-Eintrag mit duration_seconds
- list_tasks migriert Legacy-Tasks (phase_started_at = created_at)
- create_task setzt phase_started_at initial

Diese Tests laufen ohne Auth (default AUTH_ENABLED=False) und mit isoliertem
TASKS_FILE-Override, damit keine echten Daten beschaedigt werden.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path


def _make_task(task_id: str, status: str = "triage", **overrides) -> dict:
    """Erstellt ein Test-Task-Dict (kollidiert nicht mit Production-Daten)."""
    base = {
        "id": task_id,
        "project_id": "TEST_UI_REDESIGN",
        "title": f"Test Task {task_id}",
        "description": "Test description for UI redesign tests",
        "status": status,
        "priority": 50,
        "assigned_role": "pi-coder",
        "success_criteria": [],
        "parent_id": None,
        "child_ids": [],
        "references": [],
        "requirement_ref": None,
        "tags": [],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "order": 0,
        "iteration_count": 0,
        "history": [],
    }
    base.update(overrides)
    return base


def _save_tasks(tasks_file: Path, tasks: list[dict]) -> None:
    """Schreibt tasks in die isolierte tasks.json."""
    tasks_file.write_text(
        json.dumps(tasks, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ===================================================================
# Phase-Tracking: phase_started_at + phase_completed History
# ===================================================================

class TestPhaseStartedAt:
    """UI-Redesign: phase_started_at wird bei Status-Wechsel aktualisiert."""

    def test_create_task_sets_phase_started_at(self, client, tasks_file):
        """Neue Tasks haben phase_started_at = created_at (initiale Phase)."""
        resp = client.post(
            "/api/kanban/tasks",
            json={
                "project_id": "TEST_UI_REDESIGN",
                "title": "Neuer Task",
                "description": "Test",
                "priority": 50,
                "assigned_role": "pi-coder",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "phase_started_at" in data, "phase_started_at fehlt im Response"
        assert data["phase_started_at"] is not None, "phase_started_at ist None"
        # Sollte ungefaehr jetzt sein
        phase_dt = datetime.fromisoformat(data["phase_started_at"])
        delta = abs((datetime.now() - phase_dt).total_seconds())
        assert delta < 5, f"phase_started_at zu weit von now() entfernt: {delta}s"

    def test_status_change_updates_phase_started_at(self, client, tasks_file):
        """Bei Status-Wechsel wird phase_started_at aktualisiert."""
        task = _make_task("phase_test_001", status="triage")
        task["phase_started_at"] = "2026-06-15T10:00:00"
        _save_tasks(tasks_file, [task])

        resp = client.put(
            "/api/kanban/tasks/phase_test_001/status",
            json={"status": "in_progress"},
        )
        assert resp.status_code == 200, resp.text
        # Lade Task-State aus tasks.json
        tasks = json.loads(tasks_file.read_text(encoding="utf-8"))
        t = tasks[0]
        # phase_started_at muss aktualisiert worden sein
        assert t["phase_started_at"] != "2026-06-15T10:00:00", "phase_started_at wurde nicht aktualisiert"
        phase_dt = datetime.fromisoformat(t["phase_started_at"])
        delta = abs((datetime.now() - phase_dt).total_seconds())
        assert delta < 5, f"phase_started_at nicht aktualisiert auf now(): {delta}s"

    def test_phase_started_at_unchanged_on_idempotent_status(self, client, tasks_file):
        """Wenn Status gleich bleibt (idempotent), bleibt phase_started_at unveraendert."""
        original_phase = "2026-06-15T10:00:00"
        task = _make_task("phase_test_002", status="in_progress")
        task["phase_started_at"] = original_phase
        _save_tasks(tasks_file, [task])

        # PATCH dispatch sollte idempotent sein und phase_started_at NICHT aendern
        resp = client.put(
            "/api/kanban/tasks/phase_test_002/status",
            json={"status": "in_progress"},
        )
        assert resp.status_code == 200, resp.text
        # Lade Task-State
        tasks = json.loads(tasks_file.read_text(encoding="utf-8"))
        t = tasks[0]
        # Status ist unveraendert -> phase_started_at auch unveraendert
        assert t["phase_started_at"] == original_phase, "phase_started_at wurde bei idempotentem PUT geaendert"


class TestPhaseCompletedHistory:
    """UI-Redesign: phase_completed History-Eintrag mit duration_seconds."""

    def test_status_change_writes_phase_completed_entry(self, client, tasks_file):
        """Bei Status-Wechsel wird phase_completed mit duration_seconds geschrieben."""
        # Phase startete vor 2 Stunden
        phase_start = (datetime.now() - timedelta(hours=2)).isoformat()
        task = _make_task("phase_test_003", status="in_progress")
        task["phase_started_at"] = phase_start
        _save_tasks(tasks_file, [task])

        resp = client.put(
            "/api/kanban/tasks/phase_test_003/status",
            json={"status": "review"},
        )
        assert resp.status_code == 200, resp.text

        # Lade Task-State aus tasks.json
        tasks = json.loads(tasks_file.read_text(encoding="utf-8"))
        t = tasks[0]

        # Suche phase_completed Eintrag in der History
        history = t.get("history", [])
        phase_entries = [h for h in history if h.get("event") == "phase_completed"]
        assert len(phase_entries) >= 1, "Kein phase_completed History-Eintrag geschrieben"

        entry = phase_entries[-1]  # letzter Eintrag
        details = entry.get("details", entry)  # Backend kann 'details' wrapper haben
        # duration_seconds sollte ~7200 (2h) sein, mit Toleranz
        duration = details.get("duration_seconds")
        assert duration is not None, "duration_seconds fehlt im phase_completed Eintrag"
        assert 7100 <= duration <= 7300, f"duration_seconds unerwartet: {duration} (erwartet ~7200)"

        # from_status / to_status muessen gesetzt sein
        assert details.get("from_status") == "in_progress", f"from_status falsch: {details.get('from_status')}"
        assert details.get("to_status") == "review", f"to_status falsch: {details.get('to_status')}"

        # duration_human sollte "2h 0min" oder "2h Xmin" sein
        human = details.get("duration_human")
        assert human and "h" in human, f"duration_human fehlt oder unerwartet: {human}"

    def test_phase_completed_writes_warning_state(self, client, tasks_file):
        """Bei > 1h wird duration_human korrekt mit 'h' markiert."""
        phase_start = (datetime.now() - timedelta(hours=1, minutes=15)).isoformat()
        task = _make_task("phase_test_004", status="in_progress")
        task["phase_started_at"] = phase_start
        _save_tasks(tasks_file, [task])

        resp = client.put(
            "/api/kanban/tasks/phase_test_004/status",
            json={"status": "review"},
        )
        assert resp.status_code == 200
        tasks = json.loads(tasks_file.read_text(encoding="utf-8"))
        t = tasks[0]
        history = t.get("history", [])
        phase_entries = [h for h in history if h.get("event") == "phase_completed"]
        assert len(phase_entries) >= 1
        details = phase_entries[-1].get("details", phase_entries[-1])
        human = details.get("duration_human", "")
        # 1h 15min = 4500s, sollte "1h 15min" sein
        assert "h" in human, f"duration_human sollte 'h' enthalten: {human}"
        assert "1h" in human, f"duration_human sollte '1h' enthalten: {human}"

    def test_phase_completed_short_duration_minutes(self, client, tasks_file):
        """Bei < 1h wird duration_human als 'Xmin' formatiert."""
        phase_start = (datetime.now() - timedelta(minutes=23)).isoformat()
        task = _make_task("phase_test_005", status="in_progress")
        task["phase_started_at"] = phase_start
        _save_tasks(tasks_file, [task])

        resp = client.put(
            "/api/kanban/tasks/phase_test_005/status",
            json={"status": "review"},
        )
        assert resp.status_code == 200
        tasks = json.loads(tasks_file.read_text(encoding="utf-8"))
        t = tasks[0]
        history = t.get("history", [])
        phase_entries = [h for h in history if h.get("event") == "phase_completed"]
        assert len(phase_entries) >= 1
        details = phase_entries[-1].get("details", phase_entries[-1])
        human = details.get("duration_human", "")
        assert "min" in human and "h" not in human, f"duration_human unerwartet: {human}"


class TestPhaseMigration:
    """UI-Redesign: list_tasks migriert Legacy-Tasks (ohne phase_started_at)."""

    def test_list_tasks_migrates_legacy_phase_started(self, client, tasks_file):
        """Bestehende Tasks ohne phase_started_at bekommen Fallback = created_at."""
        created = "2026-06-10T08:00:00"
        task = _make_task("legacy_phase_001", status="in_progress")
        task["created_at"] = created
        task["updated_at"] = created
        # phase_started_at fehlt absichtlich
        task.pop("phase_started_at", None)
        _save_tasks(tasks_file, [task])

        resp = client.get("/api/kanban/tasks", params={"project_id": "TEST_UI_REDESIGN"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        migrated = data[0]
        assert migrated["phase_started_at"] == created, (
            f"Migration fehlgeschlagen: phase_started_at={migrated['phase_started_at']}, "
            f"erwartet={created}"
        )

    def test_list_tasks_preserves_existing_phase_started(self, client, tasks_file):
        """Bestehende phase_started_at Werte werden nicht ueberschrieben."""
        existing_phase = "2026-06-12T14:30:00"
        task = _make_task("legacy_phase_002", status="review")
        task["phase_started_at"] = existing_phase
        _save_tasks(tasks_file, [task])

        resp = client.get("/api/kanban/tasks", params={"project_id": "TEST_UI_REDESIGN"})
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["phase_started_at"] == existing_phase

    def test_list_tasks_migrates_multiple_legacy_tasks(self, client, tasks_file):
        """Migration funktioniert fuer mehrere Legacy-Tasks gleichzeitig."""
        tasks = []
        for i in range(5):
            t = _make_task(f"legacy_phase_multi_{i}", status="todo")
            t["created_at"] = f"2026-06-0{i+1}T08:00:00"
            t.pop("phase_started_at", None)
            tasks.append(t)
        _save_tasks(tasks_file, tasks)

        resp = client.get("/api/kanban/tasks", params={"project_id": "TEST_UI_REDESIGN"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 5
        for i, t in enumerate(data):
            expected = f"2026-06-0{i+1}T08:00:00"
            assert t["phase_started_at"] == expected, (
                f"Task {t['id']}: phase_started_at={t['phase_started_at']}, erwartet={expected}"
            )


class TestPhaseIntegration:
    """UI-Redesign: Integration Tests fuer End-to-End Phase-Tracking."""

    def test_full_workflow_with_phase_tracking(self, client, tasks_file):
        """Task durchlaeuft mehrere Phasen, jede mit korrektem phase_started_at."""
        # 1. Task anlegen
        resp = client.post(
            "/api/kanban/tasks",
            json={
                "project_id": "TEST_UI_REDESIGN",
                "title": "E2E Test",
                "description": "Full workflow test",
                "priority": 50,
            },
        )
        assert resp.status_code == 200
        task_id = resp.json()["id"]

        # Lade Task-State direkt aus tasks.json
        def _load():
            return json.loads(tasks_file.read_text(encoding="utf-8"))[0]

        initial_phase = _load()["phase_started_at"]
        assert initial_phase is not None

        # 2. triage -> in_progress (kurz warten, damit Dauer messbar)
        import time
        time.sleep(0.5)
        resp = client.put(f"/api/kanban/tasks/{task_id}/status", json={"status": "in_progress"})
        assert resp.status_code == 200
        phase_after_claim = _load()["phase_started_at"]
        assert phase_after_claim != initial_phase, "phase_started_at nach Claim unveraendert"

        # 3. in_progress -> review
        time.sleep(0.5)
        resp = client.put(f"/api/kanban/tasks/{task_id}/status", json={"status": "review"})
        assert resp.status_code == 200
        phase_after_review = _load()["phase_started_at"]
        assert phase_after_review != phase_after_claim

        # 4. History muss phase_completed Eintraege haben
        history = _load().get("history", [])
        phase_entries = [h for h in history if h.get("event") == "phase_completed"]
        # Mindestens 1 Eintrag fuer triage->in_progress, optional einer fuer in_progress->review
        # (je nachdem ob das erste PUT idempotent war)
        assert len(phase_entries) >= 1, "Kein phase_completed Eintrag im Full-Workflow"
