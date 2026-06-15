# TASK: Status "Warten" (Waiting) im Kanban einführen

**Projekt:** Pi Dashboard (id: `19f766e9b8bd`)
**Erstellt:** 15.06.2026
**Anforderer:** uwean
**Priority:** 70 (hoch)
**Status:** triage
**Assigned Role:** pi-coder (Implementation) + CIO-Review
**Tags:** feature, kanban, workflow, waiting, ceo-integration, watchdog
**Geschätzter Aufwand (PERT):** opt=4h, ml=8h, pess=16h, expected=8.67h, std_dev=2h

---

## Beschreibung

Im Kanban-System wird ein neuer Status **"Warten"** (waiting) eingeführt. Ein Task wechselt in diesen Status, wenn er **blockiert** ist durch externe Bedingungen, die er nicht selbst auflösen kann.

### Use Case 1: Aggregations-Warten (Sub-Task-Gate)
Wenn ein Task **N Sub-Tasks** hat und der nächste Schritt (z.B. Review) erst gestartet werden kann, wenn **alle Sub-Tasks `done`** sind, dann geht der Parent-Task automatisch in Status `Warten`.

**Beispiel:** Task "Migration durchführen" hat 10 Sub-Tasks (alle `in_progress`). Der Review kann erst starten, wenn alle 10 done sind → Parent geht in `Warten` und wechselt automatisch zurück nach `review` sobald alle Children `done` sind.

### Use Case 2: Input-Anforderung (CEO-Consultation)
Wenn ein Task **Input vom CEO oder CEO-digital** braucht (z.B. eine strategische Entscheidung, Freigabe, oder eine Klärungsfrage), dann:

1. Der Task erstellt **selbstständig einen Sub-Task** mit:
   - `assigned_role: "CEO-digital"`
   - Titel: "[INPUT NEEDED] Klärungsfrage zum Parent-Task: ..."
   - Description: Die konkrete Frage + Kontext
   - Status: `todo`
   - Prio: erbt vom Parent (oder 100 wenn dringend)
2. Der **Parent-Task geht in Status `Warten`**
3. Sobald der CEO-Sub-Task `done` ist, geht der Parent automatisch zurück nach `in_progress` (oder `review`, je nach Kontext)
4. Die Antwort des CEO wird als Comment/Antwort im Parent-Task sichtbar

---

## Success Criteria

### Funktionale Anforderungen

- [ ] **Status-Definition**: `"waiting"` ist ein gültiger Status in `Task`-Model
- [ ] **UI-Anzeige**: Board-Spalte "Warten" ist sichtbar (analog zu Block/Done)
- [ ] **Farbcode**: Eindeutige Farbe für "Warten" (z.B. lila/violett — `var(--color-hermes-purple)`)
- [ ] **Emoji-Indikator**: ⏸ oder ⏳ in Badges
- [ ] **Auto-Transitionen**:
  - [ ] Wenn alle Children `done` → Parent von `Warten` → `review` (oder konfigurierbar)
  - [ ] Wenn CEO-Sub-Task `done` → Parent von `Warten` → `in_progress`
  - [ ] Wenn Parent von `in_progress` → `Warten` wenn Sub-Task erstellt wird
- [ ] **Drag & Drop**: Tasks können manuell in "Warten" gezogen werden
- [ ] **Filter**: Status-Filter enthält "Warten" als Option
- [ ] **Bulk-Triage**: Bulk-Triage setzt auch "Warten"-Tasks zurück

### CEO-Integration

- [ ] **API-Endpoint**: `POST /api/kanban/tasks/{id}/request-input` mit Body `{question, urgency, target_role}`
- [ ] **Auto-Sub-Task-Erstellung**: System erstellt automatisch Sub-Task für CEO/CEO-digital
- [ ] **Link zum CEO-Sub-Task**: Im Parent-Task-Sidebar sichtbar
- [ ] **Notification**: Toast "Frage an CEO-digital gestellt" beim Erstellen
- [ ] **Reverse-Link**: Im CEO-Sub-Task ist der Parent verlinkt
- [ ] **Answer-Back**: CEO-Antwort wird im Parent als Comment + in `last_review`-Feld gespeichert

### Aggregations-Logik

- [ ] **Backend-Hook**: Bei `POST /tasks/{id}/aggregate` (existing) prüfen: wenn Parent in `Warten` war und alle Children `done` → Parent → `review`
- [ ] **Polling/Refetch**: UI refresht automatisch nach Status-Change
- [ ] **PER-Timer**: Anzeige "Wartet seit X Minuten/Stunden" im Badge

### Tests

- [ ] **Unit-Tests** für Auto-Transition-Logik
- [ ] **Integration-Test**: 10 Sub-Tasks durchspielen, Parent geht automatisch in Warten → nach Done zurück
- [ ] **UI-Test**: Drag & Drop in Warten-Spalte funktioniert
- [ ] **CEO-Integration-Test**: Frage erstellen → CEO-Task in Todo → Done → Parent zurück

---

## Anwendungs-Beispiele

### Beispiel 1: Warten auf Sub-Tasks
```
Task: "Deployment-Pipeline bauen" (Prio 75)
  Status: in_progress
  Sub-Tasks: 10
    - [in_progress] Docker-Setup
    - [in_progress] CI-Config
    - [todo] Tests
    - ...

→ User klickt "Submit Review" (zu früh!)
→ System erkennt: 10 Sub-Tasks nicht alle done
→ Task geht in Warten
→ UI zeigt: "⏸ Warten auf 10 Sub-Tasks (3 done, 7 in_progress)"
→ Sobald alle done: Auto-Transition zu "review"
```

### Beispiel 2: CEO-Consultation
```
Task: "Sicherheits-Architektur entwerfen" (Prio 80)
  Status: in_progress
  Worker: pi-coder

→ pi-coder braucht Entscheidung: "OAuth2 vs. SAML?"
→ System erstellt automatisch:
    Sub-Task: "[INPUT] OAuth2 vs. SAML — welche Auth-Strategie?"
      assigned_role: "CEO-digital"
      priority: 80
      status: todo
  → Parent-Task geht in Warten

→ CEO-digital bearbeitet Sub-Task, setzt Antwort: "OAuth2"
→ Sub-Task → done, Parent → in_progress (mit Antwort im Context)
```

---

## Implementation-Hinweise

### Backend (`kanban.py`)

1. **Status-Whitelist** erweitern:
   ```python
   valid_statuses = ("triage", "todo", "in_progress", "review", "block", "done", "waiting")
   ```

2. **Neue Endpoints**:
   - `POST /api/kanban/tasks/{id}/request-input` — CEO-Consultation triggern
   - `POST /api/kanban/tasks/{id}/check-waiting` — manueller Check (für Sub-Task-Done-Events)

3. **Helper-Funktionen**:
   ```python
   def _auto_wait_for_subtasks(task, all_tasks) -> bool:
       """Prüft ob alle Children done sind."""
   def _auto_resume_from_waiting(task) -> str:
       """Bestimmt Ziel-Status nach Waiting."""
   def _create_input_request_task(parent, question, target_role) -> dict:
       """Erstellt Sub-Task für CEO-Input."""
   ```

4. **Watchdog-Erweiterung**: `_kanban_operator_auto_claim` um Waiting-Logik erweitern (nur done-Tasks überspringen, waiting-Tasks respektieren)

5. **Sub-Task-Aggregation**: `aggregate_subtasks` um Waiting-Transitions erweitern

### Frontend (`Kanban.tsx`)

1. **Status-Liste** erweitern in `ALL_STATUSES` (Filter-UI)
2. **Board-Spalten**: Neue Spalte "Warten" einfügen (zwischen Block und Done)
3. **Farbcode**: Lila/Violett definieren (`--color-hermes-purple`)
4. **Prio-100 + Waiting**: Watchdog-Logik respektiert Waiting (Notfall-Claim funktioniert auch für Waiting-Tasks)
5. **Sidebar**: Neuer Bereich "⏸ Warten auf..." mit Liste der blockierenden Sub-Tasks
6. **Input-Request-Button**: Neuer Button "💬 Frage an CEO stellen" in der Sidebar
7. **Modal**: InputRequestModal mit Frage-Textarea + Urgency-Selector

### Dokumentation

- [ ] **RETRO_ENGINEERING.md** aktualisieren (Abschnitt 4.3 Workflow-Status-Machine)
- [ ] **README.md** mit neuer Spalte und Use-Cases ergänzen

---

## Abhängigkeiten

- Vorher: Prio-System (✅ implementiert)
- Vorher: Notfall-Watchdog (✅ implementiert)
- Vorher: Sub-Task-System (✅ implementiert)
- Vorher: Auto-Review-Pipeline (✅ implementiert)
- Vorher: 2-Stufen-Validation-Wizard (✅ implementiert)

→ **Alle Voraussetzungen erfüllt** — keine Blocker

---

## Acceptance-Test (für den Worker)

```python
# 1. Erstelle Task mit 3 Sub-Tasks
parent = create_task({title: "Test", status: "in_progress", priority: 50})
for i in range(3):
    create_task({title: f"Sub {i}", parent_id: parent.id, status: "in_progress"})

# 2. Versuche "Submit Review"
response = request_review(parent.id)
assert parent.status == "waiting"  # Auto-Transition
assert response.message == "⏸ Warten auf 3 Sub-Tasks"

# 3. Setze alle Sub-Tasks auf done
for child in parent.children:
    update_status(child.id, "done")

# 4. Trigger aggregation
aggregate(parent.id)
assert parent.status == "review"  # Auto-Resume

# 5. CEO-Input-Test
parent2 = create_task({title: "Brauche Entscheidung", status: "in_progress"})
request_input(parent2.id, question="OAuth2 oder SAML?", target_role="CEO-digital")
assert parent2.status == "waiting"
ceo_task = [t for t in all_tasks if t.parent_id == parent2.id][0]
assert ceo_task.assigned_role == "CEO-digital"
assert ceo_task.status == "todo"

# 6. CEO antwortet
update_status(ceo_task.id, "done", comment="OAuth2")
aggregate(parent2.id)
assert parent2.status == "in_progress"
assert "CEO-Antwort" in parent2.last_review.summary
```

---

**Verwendung dieses Dokuments:**
1. Öffne Pi Dashboard → Projekt "Pi Dashboard"
2. **Diese Datei** im Brainstorming-Tab einfügen + ggf. erweitern
3. Im Requirements-Tab die **Success Criteria** als Anforderungen generieren
4. **Task** über "Re-generate Tasks" erstellen
5. **CIO-Review** → **Implementation-Plan** → 3 Phasen durchlaufen
6. **Standardprozess** (pi-coder → pi-tester → pi-reviewer → pi-fixer)
