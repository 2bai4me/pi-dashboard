import { useState, useRef, useEffect, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, FileText, ListChecks, ChevronRight, ChevronDown, GitBranch, Target, Zap, BarChart3, BrainCircuit, Rocket, Search, X, ArrowUp, ArrowDown, Sliders, Send } from "lucide-react";
import { api, getToken } from "../api";
import { useTTSContext } from "../TTSContext";
import { DynamicTextarea } from "../TTSControl";

const COLORS = {
  todo: "var(--color-hermes-text-secondary)", in_progress: "var(--color-hermes-accent-orange)",
  review: "var(--color-hermes-accent)", done: "var(--color-hermes-accent-blue)", blocked: "var(--color-hermes-danger)",
};
const ROLE_EMOJI: Record<string, string> = {
  "CEO-digital": "👑", CIO: "🏗️", CMO: "📢", CFO: "💰",
  "pi-coder": "💻", "pi-tester": "🧪", "pi-reviewer": "👁️", "pi-fixer": "🔧",
};

// === Task-ID-Badge (klickbar, kopiert in Zwischenablage) ===
// Zeigt eine 12-stellige Task-ID als Monospace-Badge. Klick kopiert sie in
// die Zwischenablage + kurzer "Kopiert!" Hinweis (per Inline-Style).
// Props:
//   id            - die Task-ID (12-stellige Hex)
//   truncate      - falls true: zeigt nur die ersten 6 Zeichen + "..."
//   variant       - "default" | "prominent" | "board" | "child"
//   prefix        - optionales Prefix-Element (z.B. "→ " fuer Children)
function IdBadge({ id, truncate, variant, prefix }: { id: string; truncate?: boolean; variant?: "default" | "prominent" | "board" | "child"; prefix?: string }) {
  const [copied, setCopied] = useState(false);
  if (!id) return null;
  const display = truncate && id.length > 6 ? `${id.slice(0, 6)}…` : id;
  const variantClass = variant === "prominent" ? " id-badge-prominent" : variant === "board" ? " id-badge-board" : variant === "child" ? " id-badge-child" : "";
  const handleClick = (e: any) => {
    e.stopPropagation();
    e.preventDefault();
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(id).then(
        () => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        },
        () => {
          // Fallback: ueber temporaeres textarea
          try {
            const ta = document.createElement("textarea");
            ta.value = id;
            ta.style.position = "fixed";
            ta.style.opacity = "0";
            document.body.appendChild(ta);
            ta.select();
            document.execCommand("copy");
            document.body.removeChild(ta);
            setCopied(true);
            setTimeout(() => setCopied(false), 1200);
          } catch {
            /* clipboard nicht verfuegbar */
          }
        }
      );
    }
  };
  return (
    <span
      className={`id-badge${variantClass}${copied ? " id-badge-copied" : ""}`}
      title={truncate && id.length > 6 ? `Task-ID: ${id} (Klick = kopieren)` : `Task-ID kopieren: ${id}`}
      onClick={handleClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") handleClick(e as any); }}
    >
      {prefix && <span style={{ opacity: 0.7 }}>{prefix}</span>}
      {copied ? "✓ Kopiert!" : display}
    </span>
  );
}

// === Top-Level Helpers (fuer TaskSidebar ausserhalb der Komponente) ===
// Prio-Farbcode (0..100): rot (kritisch), orange (hoch), blau (mittel), grau (niedrig)
function prioColor(prio: number): { bg: string; fg: string; label: string } {
  if (prio >= 75) return { bg: "rgba(248,81,73,0.18)", fg: "var(--color-hermes-danger)", label: "kritisch" };
  if (prio >= 50) return { bg: "rgba(255,166,43,0.18)", fg: "var(--color-hermes-accent-orange)", label: "hoch" };
  if (prio >= 25) return { bg: "rgba(88,166,255,0.18)", fg: "var(--color-hermes-accent-blue)", label: "mittel" };
  return { bg: "var(--color-hermes-muted)", fg: "var(--color-hermes-text-secondary)", label: "niedrig" };
}
// Task-Prio robust parsen (kann String, Number, undefined sein)
function getTaskPrio(task: any): number {
  if (!task) return 0;
  const p = task.priority;
  if (typeof p === "number" && !isNaN(p)) return Math.max(0, Math.min(100, p));
  if (typeof p === "string") {
    const parsed = parseInt(p, 10);
    return isNaN(parsed) ? 0 : Math.max(0, Math.min(100, parsed));
  }
  return 0;
}
// HTML-Sonderzeichen escapen (XSS-Schutz fuer dangerouslySetInnerHTML)
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
// Highlighting: markiert alle Vorkommen der Suchbegriffe im Text (XSS-sicher)
function highlight(text: string, query: string): { highlighted: string; matches: boolean } {
  const q = (query || "").trim();
  if (!q || !text) return { highlighted: escapeHtml(text || ""), matches: false };
  const terms = q.split(/\s+/).filter((t) => t.length > 0);
  let result = escapeHtml(String(text));
  let totalMatches = 0;
  for (const term of terms) {
    const escapedTerm = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp(`(${escapedTerm})`, "gi");
    const before = result;
    result = result.replace(re, "\u0001$1\u0002");
    if (result !== before) totalMatches++;
  }
  const segments = result.split(/(\u0001[^\u0002]*\u0002)/g);
  const jsx = segments.map((seg) => {
    if (seg.startsWith("\u0001") && seg.endsWith("\u0002")) {
      const content = seg.slice(1, -1);
      return `<mark style="background:rgba(255,213,79,0.4);color:inherit;padding:0 2px;border-radius:2px;">${content}</mark>`;
    }
    return seg;
  }).join("");
  return { highlighted: jsx, matches: totalMatches > 0 };
}

// ─── Task Detail Sidebar ─────────────────────────────────────
function TaskSidebar({ task, onClose, allTasks, onCreateSubtasks, onAggregate, searchQuery, onUpdatePrio }: { task: any; onClose: () => void; allTasks: any[]; onCreateSubtasks?: (taskId: string) => void; onAggregate?: (taskId: string) => void; searchQuery?: string; onUpdatePrio?: (taskId: string, prio: number) => void }) {
  const prio = typeof task.priority === "number" ? task.priority : 0;
  const prioInfo = prioColor(prio);
  const children = allTasks.filter((t: any) => t.parent_id === task.id);
  const parent = allTasks.find((t: any) => t.id === task.parent_id);
  const refs = (task.references || []).map((rid: string) => allTasks.find((t: any) => t.id === rid)).filter(Boolean);

  return (
    <div style={{
      width: 400, minWidth: 400, maxWidth: 400, flexShrink: 0,
      borderLeft: "2px solid var(--color-hermes-accent-blue)",
      background: "var(--color-hermes-surface)", overflow: "auto", padding: 16,
      display: "flex", flexDirection: "column", gap: 12,
      position: "sticky", top: 0, alignSelf: "flex-start", maxHeight: "100vh",
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <span className={`badge ${task.status === "done" ? "badge-green" : task.status === "in_progress" ? "badge-orange" : task.status === "triage" ? "badge-orange" : task.status === "block" ? "badge-red" : task.status === "review" ? "badge-blue" : "badge-blue"}`} style={{ fontSize: 10 }}>
            {task.status}
          </span>
          <span
            title={prio === 100 ? `🚨 NOTFALL (Prio ${prio}) — Watchdog hat Auto-Claim ausgeloest` : `Prio: ${prio} (${prioInfo.label})`}
            style={{
              display: "inline-flex", alignItems: "center", gap: 3, fontSize: 10, fontWeight: 600, marginLeft: 4, padding: "1px 6px", borderRadius: 3,
              background: prio === 100 ? "var(--color-hermes-danger)" : prioInfo.bg,
              color: prio === 100 ? "white" : prioInfo.fg,
              animation: prio === 100 ? "pulse-emergency 1.5s ease-in-out infinite" : undefined,
              boxShadow: prio === 100 ? "0 0 8px rgba(248,81,73,0.5)" : undefined,
            }}
          >
            {prio === 100 ? "🚨" : "🔥"} {prio}
          </span>
        </div>
        <button className="btn" style={{ padding: "2px 8px", fontSize: 11 }} onClick={onClose}>✕</button>
      </div>

      <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>{task.title}</h2>

      {/* Task-ID prominent im Header (klickbar -> kopieren) */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <IdBadge id={task.id} variant="prominent" />
        <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>Task-ID · Klick zum Kopieren</span>
      </div>

      {/* Meta */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", fontSize: 12 }}>
        <span>{ROLE_EMOJI[task.assigned_role] || "🤖"} {task.assigned_role}</span>
        {task.tools?.length > 0 && <span>🔧 {task.tools.join(", ")}</span>}
        {task.iteration_count > 0 && <span style={{ color: "var(--color-hermes-accent-orange)" }}>🔄 {task.iteration_count}x iterated</span>}
        {task.review_model && <span style={{ color: "var(--color-hermes-accent-blue)" }}>📋 {task.review_model}</span>}
      </div>

      {/* Prio-Edit (mit Notfall-Watchdog) */}
      {onUpdatePrio && (
        <div style={{ padding: 8, background: prio === 100 ? "rgba(248,81,73,0.08)" : "var(--color-hermes-muted)", borderRadius: 4, border: prio === 100 ? "1px solid var(--color-hermes-danger)" : "1px solid transparent" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-hermes-text-secondary)" }}>
              🔥 Prioritaet: <span style={{ color: prioInfo.fg, fontWeight: 700 }}>{prio}</span> <span style={{ fontSize: 10 }}>({prioInfo.label})</span>
            </div>
            {prio === 100 && (
              <span style={{ fontSize: 10, fontWeight: 700, color: "var(--color-hermes-danger)", animation: "pulse-emergency 1.5s ease-in-out infinite" }}>🚨 NOTFALL</span>
            )}
          </div>
          <input
            type="range" min={0} max={100} value={prio}
            onChange={(e) => {
              const newPrio = parseInt(e.target.value);
              if (newPrio === 100 && prio !== 100) {
                if (confirm("🚨 NOTFALLUMSETZUNG starten?\n\nPrio 100 loest den Watchdog aus:\n• Task wird SOFORT uebernommen\n• Status -> in_progress\n• Worker bearbeitet Task unverzueglich\n\nWirklich auf Prio 100 setzen?")) {
                  onUpdatePrio(task.id, newPrio);
                }
                // Wenn Cancel: Slider bleibt auf altem Wert (React controlled -> kein setState noetig)
              } else {
                onUpdatePrio(task.id, newPrio);
              }
            }}
            style={{ width: "100%", cursor: "pointer", accentColor: prio === 100 ? "var(--color-hermes-danger)" : "var(--color-hermes-accent-blue)" }}
            title="Prio setzen (100 = Notfall, loest Watchdog aus)"
          />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "var(--color-hermes-text-secondary)", marginTop: 2 }}>
            <span>0 niedrig</span>
            <span>50 mittel</span>
            <span>75 hoch</span>
            <span style={{ color: prio === 100 ? "var(--color-hermes-danger)" : "var(--color-hermes-text-secondary)", fontWeight: prio === 100 ? 700 : 400 }}>100 🚨 NOTFALL</span>
          </div>
          {task.emergency && (
            <div style={{ marginTop: 4, fontSize: 10, color: "var(--color-hermes-danger)" }}>
              🚨 Notfall aktiv seit {task.emergency_at ? new Date(task.emergency_at).toLocaleString() : "—"}
              {task.assigned_role && <> · Worker: <strong>{task.assigned_role}</strong></>}
            </div>
          )}
        </div>
      )}

      {/* Description */}
      <div>
        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4, color: "var(--color-hermes-text-secondary)" }}>Description</div>
        {searchQuery && searchQuery.trim() ? (
          <pre
            style={{ fontFamily: "var(--font-mono)", fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-word", margin: 0, color: "var(--color-hermes-text)", lineHeight: 1.5, maxHeight: 200, overflow: "auto", background: "var(--color-hermes-muted)", padding: 8, borderRadius: 4 }}
            dangerouslySetInnerHTML={{ __html: highlight(task.description || "No description", searchQuery).highlighted }}
          />
        ) : (
          <pre style={{ fontFamily: "var(--font-mono)", fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-word", margin: 0, color: "var(--color-hermes-text)", lineHeight: 1.5, maxHeight: 200, overflow: "auto", background: "var(--color-hermes-muted)", padding: 8, borderRadius: 4 }}>
            {task.description || "No description"}
          </pre>
        )}
      </div>

      {/* Success Criteria */}
      {task.success_criteria?.length > 0 && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4, color: "var(--color-hermes-text-secondary)" }}>✅ Success Criteria</div>
          {task.success_criteria.map((sc: string, i: number) => (
            <div key={i} style={{ fontSize: 12, padding: "4px 8px", background: "var(--color-hermes-muted)", borderRadius: 4, marginBottom: 2 }}>
              ✓ {sc}
            </div>
          ))}
        </div>
      )}

      {/* Parent */}
      {parent && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4, color: "var(--color-hermes-text-secondary)" }}>⬆ Parent Task</div>
          <div style={{ fontSize: 12, padding: "6px 8px", background: "var(--color-hermes-muted)", borderRadius: 4 }}>
            {parent.title} <span className="badge badge-blue" style={{ fontSize: 9 }}>{parent.status}</span>
          </div>
        </div>
      )}

      {/* Children (Sub-Tasks) */}
      {children.length > 0 && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--color-hermes-text-secondary)" }}>⬇ Sub-Tasks ({children.length})</div>
            {onAggregate && (
              <button className="btn" style={{ fontSize: 9, padding: "1px 6px" }} onClick={() => onAggregate(task.id)} title="Sub-Task-Status zum Parent aggregieren">
                🔄 Aggregieren
              </button>
            )}
          </div>
          {children.map((c: any) => (
            <div key={c.id} style={{ fontSize: 12, padding: "6px 8px", background: "var(--color-hermes-muted)", borderRadius: 4, marginBottom: 2, display: "flex", justifyContent: "space-between" }}>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.title}</span>
              <span style={{ display: "flex", gap: 4, alignItems: "center" }}>
                {c.assigned_role && <span style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)" }}>{ROLE_EMOJI[c.assigned_role] || "🤖"}</span>}
                <span className={`badge ${c.status === "done" ? "badge-green" : c.status === "in_progress" ? "badge-orange" : c.status === "block" ? "badge-red" : "badge-blue"}`} style={{ fontSize: 9 }}>{c.status}</span>
              </span>
            </div>
          ))}
        </div>
      )}

      {/* References */}
      {refs.length > 0 && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4, color: "var(--color-hermes-text-secondary)" }}>🔗 References</div>
          {refs.map((r: any) => (
            <div key={r.id} style={{ fontSize: 12, color: "var(--color-hermes-accent-blue)", padding: "2px 0" }}>↳ {r.title}</div>
          ))}
        </div>
      )}

      {/* Tags */}
      {task.tags?.length > 0 && (
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {task.tags.map((t: string) => <span key={t} className="badge badge-orange" style={{ fontSize: 9 }}>{t}</span>)}
        </div>
      )}

      {/* Workflow-Informationen */}
      {(task.iteration_count > 0 || task.last_review || task.cio_approved || task.block_reason || task.cio_reject_reason || task.requirement_ref) && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4, color: "var(--color-hermes-text-secondary)" }}>🔄 Workflow-Status</div>
          {task.requirement_ref && (
            <div style={{ fontSize: 11, marginBottom: 4 }}>📎 Requirement-Ref: <span className="badge badge-blue" style={{ fontSize: 9 }}>{task.requirement_ref}</span></div>
          )}
          {task.iteration_count > 0 && (
            <div style={{ fontSize: 11, color: "var(--color-hermes-accent-orange)", marginBottom: 4 }}>🔄 {task.iteration_count}x iterated (Auto-Review durchgelaufen)</div>
          )}
          {task.last_review && (
            <div style={{ fontSize: 10, padding: 6, background: task.last_review.ok ? "rgba(46,160,67,0.1)" : "rgba(248,81,73,0.1)", borderRadius: 4, marginBottom: 4 }}>
              <strong>{task.last_review.ok ? "✅ Letzter Auto-Review: bestanden" : "❌ Letzter Auto-Review: fehlgeschlagen"}</strong>
              {task.last_review.reviewed_at && <div style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)" }}>am {new Date(task.last_review.reviewed_at).toLocaleString()}</div>}
              {task.last_review.issues?.length > 0 && (
                <ul style={{ margin: "4px 0 0 16px", fontSize: 10 }}>
                  {task.last_review.issues.slice(0, 5).map((iss: any, i: number) => (
                    <li key={i} style={{ marginBottom: 2 }}>[{iss.severity}] <strong>{iss.category}:</strong> {iss.message}</li>
                  ))}
                  {task.last_review.issues.length > 5 && <li style={{ fontStyle: "italic" }}>... und {task.last_review.issues.length - 5} weitere</li>}
                </ul>
              )}
              {task.last_review.suggestions?.length > 0 && (
                <details style={{ marginTop: 4 }}>
                  <summary style={{ fontSize: 9, cursor: "pointer", color: "var(--color-hermes-text-secondary)" }}>💡 {task.last_review.suggestions.length} Vorschlaege anzeigen</summary>
                  <ul style={{ margin: "4px 0 0 16px", fontSize: 10 }}>
                    {task.last_review.suggestions.map((s: any, i: number) => (
                      <li key={i}>{s.message}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}
          {task.cio_approved && (
            <div style={{ fontSize: 11, color: "var(--color-hermes-accent)", marginBottom: 4 }}>✅ CIO approved {task.cio_approved_at && `am ${new Date(task.cio_approved_at).toLocaleString()}`}</div>
          )}
          {task.cio_reject_reason && (
            <div style={{ fontSize: 11, color: "var(--color-hermes-danger)", marginBottom: 4 }}>❌ CIO-Reject: {task.cio_reject_reason}</div>
          )}
          {task.block_reason && (
            <div style={{ fontSize: 11, color: "var(--color-hermes-danger)", marginBottom: 4 }}>🚧 Blockiert: {task.block_reason}</div>
          )}
        </div>
      )}

      {/* Sub-Task Action */}
      {onCreateSubtasks && (
        <button
          className="btn"
          style={{ fontSize: 11, padding: "4px 8px", width: "100%" }}
          onClick={() => onCreateSubtasks(task.id)}
        >
          ➕ Sub-Tasks erstellen (PI-Worker kann gro\u00dfe Tasks aufteilen)
        </button>
      )}

      {/* Timestamps */}
      <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", borderTop: "1px solid var(--color-hermes-border)", paddingTop: 8 }}>
        Created: {task.created_at ? new Date(task.created_at).toLocaleString() : "—"}<br />
        Updated: {task.updated_at ? new Date(task.updated_at).toLocaleString() : "—"}<br />
        ID: {task.id}
      </div>
    </div>
  );
}

export default function KanbanAdvanced() {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<"projects" | "brainstorm" | "requirements" | "tasks" | "board" | "kpis" | "brain-dev">("projects");
  const [activeProject, setActiveProject] = useState<string | null>(null);
  const [showNewProject, setShowNewProject] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [projectDesc, setProjectDesc] = useState("");
  const [brainstormInput, setBrainstormInput] = useState("");
  const [brainstormLog, setBrainstormLog] = useState<any[]>([]);
  const [canGenerate, setCanGenerate] = useState(false);
  const [requirementsText, setRequirementsText] = useState("");
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());
  // === Global Search (Volltextsuche ueber alle Tasks) ===
  const [searchQuery, setSearchQuery] = useState("");
  // === Filter & Sort (Prio, Status, Assigned-Role) ===
  const [prioMin, setPrioMin] = useState<number>(0);
  const [prioMax, setPrioMax] = useState<number>(100);
  const [statusFilters, setStatusFilters] = useState<Set<string>>(new Set());  // leer = alle
  const [roleFilters, setRoleFilters] = useState<Set<string>>(new Set());  // leer = alle
  const [activeMode, setActiveMode] = useState<boolean>(false);  // blendet leere + Done aus
  type SortBy = "prio" | "role" | "title" | "status" | "created";
  const [sortBy, setSortBy] = useState<SortBy>("prio");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [showFilters, setShowFilters] = useState(false);
  const [selectedTask, setSelectedTask] = useState<any>(null);
  const brainstormRef = useRef<HTMLDivElement | null>(null);
  const tts = useTTSContext();

  const { data: projects, isLoading: loadProjects } = useQuery({
    queryKey: ["kanban-projects"],
    queryFn: () => api.get("/kanban/projects"),
    refetchInterval: 5000,
  });

  const activeProjectData = (projects || []).find((p: any) => p.id === activeProject);

  // Live-MD-Generator: Strukturiert das Brainstorming als Fragenkatalog
  // - Entfernt **Fett**-Markdown, reiner Text
  // - Jeder Satz mit Satzzeichen (. ! ?), auch Überschriften
  // - Konversationale Fragenliste (muss mit Backend sync sein)
  // - User-Inputs werden chronologisch auf die Fragen gemappt
  // - Redundante AI-Antworten komprimieren

  // CEO-Geschaeftsfragen
  const CONVERSATION_QUESTIONS = [
    "Wer ist die Zielgruppe beziehungsweise der Nutzer dieser Loesung?",
    "Welches konkrete Problem soll geloest werden?",
    "Welche zeitlichen oder budgetaeren Vorgaben gibt es?",
    "Wie messen Sie den Erfolg?",
    "Welche Abhaengigkeiten zu anderen Systemen gibt es?",
  ];

  // CIO-Entwicklungsthemen (mit Empfehlungen)
  // keywords: Heuristik, ob das Thema in User-Inputs/Description schon vorkommt
  const CIO_CHECKS = [
    { topic: "Architektur", keywords: ["architektur","architecture","monolith","microservice","soa","service-orient","modular","serverless","lambda"], recommendation: "Empfehlung des CIO: Starten Sie mit einem Modular Monolith, falls Team < 5 Entwickler. Skaliert besser als Microservices." },
    { topic: "Tech-Stack", keywords: ["python","javascript","typescript","react","vue","angular","node","java","go","golang","rust","php","ruby","framework","fastapi","django","flask","express","spring","next.js","nuxt"], recommendation: "Empfehlung des CIO: Python + FastAPI (Backend) + React + TypeScript (Frontend) ist eine moderne, gut dokumentierte Wahl." },
    { topic: "Datenbank", keywords: ["datenbank","database","sql","postgres","postgresql","mysql","mariadb","mongo","mongodb","redis","sqlite","neo4j","dynamo","cassandra","elasticsearch"], recommendation: "Empfehlung des CIO: Starten Sie mit PostgreSQL. Wenn NoSQL noetig: MongoDB. Vermeiden Sie Polyglot-Persistence zu Beginn." },
    { topic: "Deployment & Hosting", keywords: ["deployment","deploy","hosting","cloud","aws","azure","gcp","google cloud","hetzner","ionos","on-premise","self-hosted","docker","kubernetes","k8s","container","vserver"], recommendation: "Empfehlung des CIO: Docker-Container + Reverse Proxy. Kubernetes erst ab ~10 Services noetig." },
    { topic: "Authentifizierung", keywords: ["authentifizierung","authentication","auth","login","oauth","sso","saml","openid","mfa","2fa","totp","jwt","session","authentik","keycloak","auth0","clerk"], recommendation: "Empfehlung des CIO: Authentik oder Keycloak statt eigenem Auth-Code. Multi-Faktor (TOTP) als Standard." },
    { topic: "Sicherheit", keywords: ["sicherheit","security","dsgvo","gdpr","verschl","encrypt","tls","ssl","https","audit","penetration","pentest","cve","owasp","rate-limit"], recommendation: "Empfehlung des CIO: HTTPS ueberall, verschluesselte Passwoerter (argon2id), Audit-Log, Rate-Limiting, regelmaessige Dependency-Updates." },
    { topic: "Skalierung & Last", keywords: ["skalier","scale","scaling","last","concurrent","gleichzeitig","user","nutzer","million","tausend","anfragen","qps","rps","durchsatz","performance","load"], recommendation: "Empfehlung des CIO: < 1000 User: Single-Server. 1000-10000: 2-3 Server mit Load-Balancer. Vermeiden Sie Premature Optimization." },
    { topic: "Testing & Qualitaet", keywords: ["test","testing","pytest","unittest","jest","ci/cd","pipeline","coverage","e2e","end-to-end","integration","unit-test","qualitaet","qa"], recommendation: "Empfehlung des CIO: Mindestens 70% Test-Coverage, davon 90% bei Geschaeftslogik. CI/CD mit GitHub Actions." },
    { topic: "Backup & Recovery", keywords: ["backup","recovery","snapshot","disaster","restore","rpo","rto","dr","archiv","wiederherstell"], recommendation: "Empfehlung des CIO: 3-2-1-Regel. Recovery regelmaessig testen (DR-Drill quartalsweise). RPO < 24h, RTO < 4h." },
  ];

  // Helper: Markdown-Formatierung entfernen + Satzzeichen sicherstellen
  const cleanText = (raw: string, forcePunctuation: boolean = true): string => {
    if (!raw) return "";
    let t = raw;
    // **Bold** -> plain
    t = t.replace(/\*\*([^*]+)\*\*/g, "$1");
    // *Italic* -> plain
    t = t.replace(/\*([^*]+)\*/g, "$1");
    // `Code` -> plain
    t = t.replace(/`([^`]+)`/g, "$1");
    // Mehrfache Leerzeichen -> eins
    t = t.replace(/  +/g, " ");
    // Trim
    t = t.trim();
    if (!t) return "";
    if (forcePunctuation) {
      const last = t.slice(-1);
      // Wenn letztes Zeichen kein Satzzeichen, hänge einen Punkt an
      if (!/[.!?:;]/.test(last)) {
        t = t + ".";
      }
    }
    return t;
  };

  const buildBrainstormDoc = (log: any[], project: any): string => {
    const lines: string[] = [];
    lines.push(cleanText(`# ${project?.name || "Projekt"}`));
    lines.push("");
    if (project?.description) {
      lines.push(`> ${cleanText(project.description)}`);
      lines.push("");
    }
    if (!log || log.length === 0) {
      lines.push("_Brainstorming starten, um Inhalte zu sammeln..._");
      return lines.join("\n");
    }
    // Konversationaler Fragenkatalog: Im Backend definiert, hier dupliziert
    // Bestimmt die Reihenfolge der Fragen — unabhängig vom AI-Text
    const allQuestions = CONVERSATION_QUESTIONS;

    // Sammle alle User-Texte (Description + User-Inputs) fuer CIO-Heuristik
    const projectDesc = project?.description || "";
    const allUserText = (
      [projectDesc, ...(log.filter((e: any) => e.role === "user").map((e: any) => e.text))]
        .join(" ")
    ).toLowerCase();
    const addressedCioTopics: string[] = [];
    for (const check of CIO_CHECKS) {
      for (const kw of check.keywords) {
        if (allUserText.includes(kw)) {
          addressedCioTopics.push(check.topic);
          break;
        }
      }
    }
    // Offene CIO-Checks (nicht adressiert)
    const openCioChecks = CIO_CHECKS.filter((c) => !addressedCioTopics.includes(c.topic));

    const lastAIResponse: string[] = [];
    for (const entry of log) {
      if (entry.role === "assistant") {
        lastAIResponse.length = 0;
        lastAIResponse.push(entry.text || "");
      }
    }
    // User-Inputs in Reihenfolge
    const userInputs: { turn: number; text: string }[] = [];
    log.forEach((e: any, i: number) => {
      if (e.role === "user") userInputs.push({ turn: i + 1, text: e.text });
    });
    // === Vision (nur der erste, ursprüngliche Input) ===
    if (userInputs.length > 0) {
      lines.push(cleanText("## 🎯 Ursprüngliche Vision"));
      lines.push("");
      lines.push(`> ${cleanText(userInputs[0].text)}`);
      lines.push("");
    }
    // === Fragenkatalog (Kern des Dokuments) ===
    if (allQuestions.length > 0) {
      lines.push(cleanText("## ❓ CEO-Fragenkatalog (Geschaeftsseite)"));
      lines.push("");
      // Mappe User-Inputs auf Fragen: jeder User-Input (außer der erste Vision-Input) beantwortet idealerweise die nächste offene Frage
      const answerableInputs = userInputs.slice(1); // alle nach der ursprünglichen Vision
      allQuestions.forEach((q: string, i: number) => {
        const answer = answerableInputs[i];
        if (answer) {
          lines.push(cleanText(`### ✅ CEO-Frage ${i + 1}: ${q}`));
          lines.push("");
          lines.push(`> ${cleanText(answer.text)}`);
          lines.push("");
        } else {
          lines.push(cleanText(`### ⏳ CEO-Frage ${i + 1}: ${q}`));
          lines.push("");
          lines.push("_Noch nicht beantwortet._");
          lines.push("");
        }
      });
    }
    // === CIO-Themenkatalog (Entwicklungsseite) ===
    if (CIO_CHECKS.length > 0) {
      lines.push(cleanText("## 🏗️ CIO-Themenkatalog (Entwicklungsseite)"));
      lines.push("");
      lines.push(cleanText(`_Hinweis: ${addressedCioTopics.length} von ${CIO_CHECKS.length} Themen wurden bereits durch die Projekt-Beschreibung abgedeckt und uebersprungen._`));
      lines.push("");
      // Sammle CIO-User-Antworten (alle User-Inputs nach den 5 CEO-Antworten)
      const cioAnswers = userInputs.slice(1 + allQuestions.length);
      CIO_CHECKS.forEach((check, i) => {
        const addressed = addressedCioTopics.includes(check.topic);
        const answer = cioAnswers[i];
        if (addressed) {
          lines.push(cleanText(`### ✅ CIO-Thema ${i + 1}: ${check.topic} (abgedeckt durch Projektbeschreibung)`));
          lines.push("");
          lines.push(`> ${cleanText(projectDesc || "Bereits in der Projektvision erwaehnt.")}`);
          lines.push("");
        } else if (answer) {
          lines.push(cleanText(`### ✅ CIO-Thema ${i + 1}: ${check.topic}`));
          lines.push("");
          lines.push(`> ${cleanText(answer.text)}`);
          lines.push("");
          lines.push(cleanText(`_💡 ${check.recommendation}_`));
          lines.push("");
        } else {
          lines.push(cleanText(`### ⏳ CIO-Thema ${i + 1}: ${check.topic}`));
          lines.push("");
          lines.push(cleanText(`_Vom CIO vorgeschlagene Frage: Erklaerung der Vorgaben._`));
          lines.push("");
          lines.push(cleanText(`_💡 ${check.recommendation}_`));
          lines.push("");
        }
      });
    } else if (userInputs.length > 0) {
      // Keine nummerierten Fragen gefunden — zeige Inputs als freie Sammlung
      lines.push(cleanText("## 📝 Gesammelte Inputs"));
      lines.push("");
      userInputs.forEach((u, i) => {
        lines.push(cleanText(`### Input ${i + 1}`));
        lines.push("");
        lines.push(cleanText(u.text));
        lines.push("");
      });
    }
    // === Zusätzliche User-Inputs (falls mehr Antworten als Fragen) ===
    if (userInputs.length > 1 && allQuestions.length > 0) {
      const extraInputs = userInputs.slice(1 + allQuestions.length);
      if (extraInputs.length > 0) {
        lines.push(cleanText("## 💡 Weitere Erkenntnisse"));
        lines.push("");
        extraInputs.forEach((u) => {
          lines.push(`- ${cleanText(u.text)}`);
          lines.push("");
        });
      }
    }
    // === Aktuelle KI-Zusammenfassung (letzte Antwort, ent-redundanzt) ===
    if (lastAIResponse.length > 0 && lastAIResponse[0]) {
      const last = lastAIResponse[0];
      // Entferne redundante Header-Zeilen, die in jeder AI-Antwort wiederholt werden
      const cleaned = last
        .split("\n")
        .filter((line) => {
          const t = line.trim();
          // Entferne "Ich habe folgende Ziele erfasst:" Boilerplate
          if (t.startsWith("Ich habe folgende Ziele erfasst")) return false;
          // Entferne "Projekt: ... | Ihre Eingabe: ..." wenn schon oben gezeigt
          if (t.startsWith("**Projekt:**") || t.startsWith("**Ihre Eingabe:**")) return false;
          // Entferne "**Verständnisfragen:**" (wurde schon als H3 extrahiert)
          if (t.startsWith("**Verständnisfragen")) return false;
          return true;
        })
        .map((l) => cleanText(l)) // ** raus, Satzzeichen rein
        .join("\n")
        .trim();
      if (cleaned) {
        lines.push("---");
        lines.push("");
        lines.push(cleanText("## 🤖 Aktuelle KI-Analyse (komprimiert)"));
        lines.push("");
        lines.push(cleaned);
        lines.push("");
      }
    }
    return lines.join("\n");
  };
  const brainstormDoc = useMemo(
    () => buildBrainstormDoc(brainstormLog, activeProjectData),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [brainstormLog, activeProjectData]
  );

  // Review-State
  const [reviewResult, setReviewResult] = useState<any | null>(null);
  const [showReviewModal, setShowReviewModal] = useState(false);
  const reviewMut = useMutation({
    mutationFn: (md: string) => api.post(`/kanban/requirements/review/${activeProject}`, { md_content: md }),
    onSuccess: async (data: any) => {
      setReviewResult(data);
      // Wenn Quality-Rückfragen da sind, speichere sie persistent
      if (data.needs_clarification && data.needs_clarification.length > 0) {
        try {
          await api.saveQualityClarifications(activeProject!, data.needs_clarification);
          qc.invalidateQueries({ queryKey: ["quality", activeProject] });
        } catch (e) { /* ignore */ }
      }
      setShowReviewModal(true);
    },
  });
  // === CIO-Review + Implementation-Start (Basissystem + erste App) ===
  const [cioReviewResult, setCioReviewResult] = useState<any | null>(null);
  const [implementationResult, setImplementationResult] = useState<any | null>(null);
  const [showCioReviewModal, setShowCioReviewModal] = useState(false);
  const [showImplementationModal, setShowImplementationModal] = useState(false);
  const cioReviewMut = useMutation({
    mutationFn: () => api.cioReviewImplementation(activeProject!),
    onSuccess: (data: any) => {
      setCioReviewResult(data);
      setShowCioReviewModal(true);
    },
  });
  const startImplMut = useMutation({
    mutationFn: () => api.startImplementation(activeProject!),
    onSuccess: (data: any) => {
      setImplementationResult(data);
      setShowCioReviewModal(false);
      setShowImplementationModal(true);
    },
  });
  const markStepDoneMut = useMutation({
    mutationFn: (stepId: string) => api.markStepDone(activeProject!, stepId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["implementation", activeProject] }),
  });

  // === Drag & Drop im Board (Task-Status aendern) ===
  const [draggedTaskId, setDraggedTaskId] = useState<string | null>(null);
  const [dragOverColumn, setDragOverColumn] = useState<string | null>(null);
  const updateTaskStatusMut = useMutation({
    mutationFn: ({ taskId, status }: { taskId: string; status: string }) =>
      api.updateTaskStatus(taskId, status),
    onMutate: async ({ taskId, status }) => {
      // Optimistisches Update: Task sofort in neue Spalte verschieben
      await qc.cancelQueries({ queryKey: ["kanban-tasks", activeProject] });
      const prev = qc.getQueryData<any[]>(["kanban-tasks", activeProject]);
      qc.setQueryData<any[]>(["kanban-tasks", activeProject], (old: any[] | undefined) =>
        (old || []).map((t: any) => t.id === taskId ? { ...t, status, updated_at: new Date().toISOString() } : t)
      );
      return { prev };
    },
    onError: (_e, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(["kanban-tasks", activeProject], ctx.prev);
    },
    onSuccess: (data: any) => {
      // Kanban-Operator Auto-Claim anzeigen
      if (data.auto_action?.auto_action === "auto_claim") {
        setWorkflowNotification({ message: data.auto_action.message, ok: true, action: "auto_claim", ts: Date.now() });
        setTimeout(() => setWorkflowNotification(null), 4000);
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["kanban-tasks", activeProject] });
      setDraggedTaskId(null);
      setDragOverColumn(null);
    },
  });
  // === Prio-Update (mit Notfall-Watchdog-Handling) ===
  const updateTaskPrioMut = useMutation({
    mutationFn: ({ taskId, priority }: { taskId: string; priority: number }) =>
      api.updateTaskPriority(taskId, priority),
    onMutate: async ({ taskId, priority }) => {
      // Optimistisches Update
      await qc.cancelQueries({ queryKey: ["kanban-tasks", activeProject] });
      const prev = qc.getQueryData<any[]>(["kanban-tasks", activeProject]);
      qc.setQueryData<any[]>(["kanban-tasks", activeProject], (old: any[] | undefined) =>
        (old || []).map((t: any) => t.id === taskId ? { ...t, priority, updated_at: new Date().toISOString() } : t)
      );
      return { prev };
    },
    onError: (_e, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(["kanban-tasks", activeProject], ctx.prev);
    },
    onSuccess: (data: any) => {
      // Watchdog-Trigger anzeigen
      if (data.auto_action?.auto_action === "emergency_claim") {
        setWorkflowNotification({ message: data.auto_action.message, ok: true, action: "emergency_claim", ts: Date.now() });
        setTimeout(() => setWorkflowNotification(null), 6000);
      }
      // Prio-Badge in der Sidebar aktualisieren (selectedTask folgt)
      if (selectedTask && data.task_id === selectedTask.id) {
        setSelectedTask((prev: any) => prev ? { ...prev, priority: data.priority, status: data.status, emergency: data.emergency } : prev);
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["kanban-tasks", activeProject] });
    },
  });
  // Sub-Task-Erstellung
  const createSubtasksMut = useMutation({
    mutationFn: ({ taskId, subtasks }: { taskId: string; subtasks: any[] }) =>
      api.createSubtasks(taskId, subtasks),
    onSuccess: (data: any) => {
      qc.invalidateQueries({ queryKey: ["kanban-tasks", activeProject] });
      setShowSubtaskModal(null);
      setWorkflowNotification({ message: `${data.created} Sub-Tasks erstellt.`, ok: true, action: "subtask", ts: Date.now() });
      setTimeout(() => setWorkflowNotification(null), 4000);
    },
  });
  const aggregateMut = useMutation({
    mutationFn: (taskId: string) => api.aggregateSubtasks(taskId),
    onSuccess: (data: any) => {
      qc.invalidateQueries({ queryKey: ["kanban-tasks", activeProject] });
      setWorkflowNotification({ message: `Parent aggregiert: ${data.old_status} → ${data.new_status}`, ok: data.new_status === "done", action: "aggregate", ts: Date.now() });
      setTimeout(() => setWorkflowNotification(null), 4000);
    },
  });
  const [showSubtaskModal, setShowSubtaskModal] = useState<string | null>(null);
  const bulkTriageMut = useMutation({
    mutationFn: () => api.bulkSetTasksTriage(activeProject!),
    onSuccess: (data: any) => {
      qc.invalidateQueries({ queryKey: ["kanban-tasks", activeProject] });
      alert(`✅ ${data.updated} Tasks zurueck in Triage verschoben.`);
    },
  });
  // === Task-Workflow-Actions (CIO + PI-Worker) ===
  const workflowMut = useMutation({
    mutationFn: ({ taskId, action, extra }: { taskId: string; action: string; extra?: any }) =>
      api.taskWorkflow(taskId, action, extra),
    onSuccess: (data: any) => {
      qc.invalidateQueries({ queryKey: ["kanban-tasks", activeProject] });
      const r = data.result || {};
      // Workflow-Ergebnis als kleine Notification
      const msg = r.message || `${r.action} ausgefuehrt`;
      const ok = r.review_ok !== false;
      setWorkflowNotification({ message: msg, ok, action: r.action, ts: Date.now() });
      setTimeout(() => setWorkflowNotification(null), 4000);
    },
  });
  const [workflowNotification, setWorkflowNotification] = useState<any | null>(null);
  // === Quality-Rückfragen Query (fuer Brainstorming-Tab) ===
  const qualityQuery = useQuery({
    queryKey: ["quality", activeProject],
    queryFn: () => api.getQuality(activeProject!),
    enabled: !!activeProject,
    retry: false,
    refetchOnWindowFocus: true,
  });
  const answerQualityMut = useMutation({
    mutationFn: ({ id, text }: { id: string; text: string }) =>
      api.answerQuality(activeProject!, id, text),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["quality", activeProject] });
      qc.invalidateQueries({ queryKey: ["kanban-brainstorm", activeProject] }); // Log wurde ergänzt
    },
  });

  // === 2-STUFIGER REVIEW (Vollstaendigkeit zuerst, dann Qualitaet) ===
  type ReviewPhase = "idle" | "completeness" | "completeness-clarify" | "quality" | "quality-clarify" | "done";
  const [reviewPhase, setReviewPhase] = useState<ReviewPhase>("idle");
  const [completenessResult, setCompletenessResult] = useState<any | null>(null);
  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, string>>({});
  const completenessMut = useMutation({
    mutationFn: () => api.completenessCheck(activeProject!),
    onSuccess: (data: any) => {
      setCompletenessResult(data);
      if (data.is_complete) {
        // Direkt zur Qualitaetspruefung
        reviewMut.mutate(brainstormDoc);
        setReviewPhase("quality");
      } else {
        setReviewPhase("completeness-clarify");
        setShowReviewModal(true);
      }
    },
  });

  // === Klaerungsfragen-Status (fuer Brainstorming-Tab) ===
  const completenessQuery = useQuery({
    queryKey: ["completeness", activeProject],
    queryFn: () => api.getCompleteness(activeProject!),
    enabled: !!activeProject,
    retry: false,
    refetchOnWindowFocus: true,
  });
  const answerCompletenessMut = useMutation({
    mutationFn: ({ id, text }: { id: string; text: string }) =>
      api.answerCompleteness(activeProject!, id, text),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["completeness", activeProject] }),
  });
  const [inlineAnswers, setInlineAnswers] = useState<Record<string, string>>({});

  // === 9-Schritt-Review-Pipeline (NEU) ===
  const [pipelineResult, setPipelineResult] = useState<any | null>(null);
  const [showPipelineModal, setShowPipelineModal] = useState(false);
  const pipelineMut = useMutation({
    mutationFn: () => api.runReviewPipeline(activeProject!),
    onSuccess: (data: any) => {
      setPipelineResult(data);
      setShowPipelineModal(true);
      qc.invalidateQueries({ queryKey: ["review-pipeline", activeProject] });
    },
  });
  const pipelineQuery = useQuery({
    queryKey: ["review-pipeline", activeProject],
    queryFn: () => api.getReviewPipeline(activeProject!),
    enabled: !!activeProject,
    retry: false,
  });

  // OpenBrain-Validierung (Legacy-Endpunkte, falls direkt aufgerufen)
  const [validationResult, setValidationResult] = useState<any | null>(null);
  const validationQuery = useQuery({
    queryKey: ["kanban-validation", activeProject],
    queryFn: () => api.get(`/kanban/validation/${activeProject}`),
    enabled: !!activeProject,
    retry: false,
  });
  const startValidationMut = useMutation({
    mutationFn: () => api.post(`/kanban/validation/${activeProject}/start`),
    onSuccess: (data: any) => {
      setValidationResult(data);
      qc.invalidateQueries({ queryKey: ["kanban-validation", activeProject] });
    },
  });
  const answerClarificationMut = useMutation({
    mutationFn: ({ id, text }: { id: string; text: string }) =>
      api.post(`/kanban/validation/${activeProject}/answer`, { clarification_id: id, answer: text }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["kanban-validation", activeProject] });
    },
  });

  // Tasks
  const { data: allTasks } = useQuery({
    queryKey: ["kanban-tasks", activeProject],
    queryFn: () => api.get(`/kanban/tasks?project_id=${activeProject}`),
    enabled: !!activeProject,
    refetchInterval: 5000,
  });

  // === SSE Echtzeit-Updates (Task-01eff3c3ebeb) ===
  // Abonniert Task-Events fuer das aktive Projekt.
  // Bei Event: invalidateQueries("kanban-tasks") -> sofortiges Re-Render (<1s).
  const [sseConnected, setSseConnected] = useState(false);
  useEffect(() => {
    if (!activeProject) return;
    const token = getToken();
    const url = `/api/kanban/events/${activeProject}${token ? `?token=${token}` : ""}`;
    const es = new EventSource(url);
    es.onopen = () => setSseConnected(true);
    es.onerror = () => setSseConnected(false);
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type && data.type !== "connected") {
          // Invalidate Task-Query -> automatischer Re-Fetch
          qc.invalidateQueries({ queryKey: ["kanban-tasks", activeProject] });
        }
      } catch {
        /* ignore parse errors */
      }
    };
    return () => { es.close(); setSseConnected(false); };
  }, [activeProject, qc]);

  // KPIs
  const { data: kpiData } = useQuery({
    queryKey: ["kanban-kpis", activeProject],
    queryFn: () => api.get(`/kanban/kpis/${activeProject}`),
    enabled: !!activeProject,
    refetchInterval: 10000,
  });

  const createProject = useMutation({
    mutationFn: (d: any) => api.post("/kanban/projects", d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["kanban-projects"] }); setShowNewProject(false); setProjectName(""); setProjectDesc(""); },
  });

  const brainstormMut = useMutation({
    mutationFn: ({ id, text }: { id: string; text: string }) => api.post(`/kanban/brainstorm/${id}`, { text }),
    onSuccess: (data: any) => {
      setBrainstormLog((prev) => [...prev, { role: "user", text: brainstormInput }, { role: "assistant", text: data.assistant_text }]);
      setCanGenerate(data.can_generate_requirements);
      setBrainstormInput("");
      // Auto-scroll to bottom
      setTimeout(() => {
        if (brainstormRef.current) {
          brainstormRef.current.scrollTop = brainstormRef.current.scrollHeight;
        }
      }, 100);
    },
  });

  const generateReqMut = useMutation({
    mutationFn: (id: string) => api.post(`/kanban/requirements/generate/${id}`),
    onSuccess: (data: any) => {
      setRequirementsText(data.content);
      setActiveTab("requirements");
    },
  });

  const reqToTasksMut = useMutation({
    mutationFn: (id: string) => api.post(`/kanban/requirements-to-tasks/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["kanban-tasks"] });
      setActiveTab("tasks");
    },
  });

  const processTriageMut = useMutation({
    mutationFn: (id: string) => api.post(`/kanban/triage/${id}/process`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["kanban-tasks"] }); },
  });

  const { data: brainDev } = useQuery({
    queryKey: ["brain-dev"],
    queryFn: () => api.get("/kanban/brain-dev"),
  });

  function selectProject(id: string) {
    setActiveProject(id);
    setBrainstormLog([]);
    setCanGenerate(false);
    setRequirementsText("");
    setActiveTab("board");
    // Load existing brainstorm log from server
    api.get(`/kanban/brainstorm/${id}/log`).then((log: any) => {
      const entries = log || [];
      setBrainstormLog(entries);
      if (entries.length >= 4) setCanGenerate(true);
    }).catch(() => {});
  }

  // === Search Helpers ===
  // Liste aller durchsuchbaren Felder einer Task (Volltext)
  const TASK_SEARCH_FIELDS = [
    "title", "description", "assigned_role", "status", "priority",
    "requirement_ref", "block_reason", "cio_reject_reason",
    "requirement_id", "claim_message", "sub_agent",
  ];
  // Sammelt alle durchsuchbaren Strings einer Task (inkl. success_criteria, tags, refs, pert)
  function getTaskSearchableText(task: any): string {
    if (!task) return "";
    const parts: string[] = [];
    for (const f of TASK_SEARCH_FIELDS) {
      const v = task[f];
      if (v != null) parts.push(String(v));
    }
    if (Array.isArray(task.success_criteria)) parts.push(task.success_criteria.join(" "));
    if (Array.isArray(task.tags)) parts.push(task.tags.join(" "));
    if (Array.isArray(task.references)) parts.push(task.references.join(" "));
    if (Array.isArray(task.tools)) parts.push(task.tools.join(" "));
    if (task.pert) {
      parts.push(`opt ${task.pert.opt} ml ${task.pert.ml} pess ${task.pert.pess} expected ${task.pert.expected} std ${task.pert.std_dev}`);
    }
    if (task.pert_rollup) {
      parts.push(`total ${task.pert_rollup.total_expected_hours} std ${task.pert_rollup.total_std_hours} ci ${task.pert_rollup.ci_95_low_hours}-${task.pert_rollup.ci_95_high_hours}`);
    }
    if (task.last_review) {
      if (task.last_review.issues) {
        for (const iss of task.last_review.issues) {
          if (iss) parts.push(`${iss.category || ""} ${iss.message || ""} ${iss.severity || ""}`);
        }
      }
      if (task.last_review.suggestions) {
        for (const s of task.last_review.suggestions) {
          if (s) parts.push(s.message || "");
        }
      }
    }
    return parts.join(" ").toLowerCase();
  }
  // Prueft, ob alle Suchbegriffe (Whitespace-getrennt) im Task-Volltext vorkommen (AND-Logik)
  function taskMatchesQuery(task: any, query: string): boolean {
    const q = (query || "").trim().toLowerCase();
    if (!q) return true;
    const text = getTaskSearchableText(task);
    return q.split(/\s+/).every((term) => text.includes(term));
  }
  // Prueft, ob ein Projekt zur Suche passt: Name, Description, oder irgendeine seiner Tasks
  function projectMatchesQuery(project: any, query: string, tasks: any[]): boolean {
    const q = (query || "").trim().toLowerCase();
    if (!q) return true;
    const projectText = [project?.name || "", project?.description || "", project?.status || ""].join(" ").toLowerCase();
    const terms = q.split(/\s+/);
    // Wenn alle Termine im Projekt-Text vorkommen, passt es
    if (terms.every((t) => projectText.includes(t))) return true;
    // Sonst pruefe, ob irgendeine Task passt
    return (tasks || []).some((t: any) => taskMatchesQuery(t, q));
  }
  // Highlighting: siehe Top-Level-Funktion oben
  // HTML-Sonderzeichen escapen (XSS-Schutz fuer dangerouslySetInnerHTML) — siehe Top-Level
  // === Filter- & Sort-Logik ===
  // Prio-Farbcode & getTaskPrio sind als Top-Level definiert (siehe oben)
  // Status-Filter pruefen
  function taskMatchesStatusFilters(task: any): boolean {
    if (statusFilters.size === 0) return true;
    return statusFilters.has(task.status);
  }
  // Role-Filter pruefen
  function taskMatchesRoleFilters(task: any): boolean {
    if (roleFilters.size === 0) return true;
    return roleFilters.has(task.assigned_role || "");
  }
  // Prio-Filter pruefen
  function taskMatchesPrioFilter(task: any): boolean {
    const p = getTaskPrio(task);
    return p >= prioMin && p <= prioMax;
  }
  // Combined-Filter (sucht zusaetzlich zu Such-Query)
  function taskMatchesAllFilters(task: any): boolean {
    if (!taskMatchesQuery(task, searchQuery)) return false;
    if (!taskMatchesPrioFilter(task)) return false;
    if (!taskMatchesStatusFilters(task)) return false;
    if (!taskMatchesRoleFilters(task)) return false;
    return true;
  }
  // Sortier-Comparator
  function compareTasks(a: any, b: any): number {
    let cmp = 0;
    switch (sortBy) {
      case "prio":
        cmp = getTaskPrio(a) - getTaskPrio(b);
        break;
      case "role":
        cmp = (a.assigned_role || "").localeCompare(b.assigned_role || "");
        break;
      case "title":
        cmp = (a.title || "").localeCompare(b.title || "");
        break;
      case "status":
        cmp = (a.status || "").localeCompare(b.status || "");
        break;
      case "created":
        cmp = (a.created_at || "").localeCompare(b.created_at || "");
        break;
    }
    if (cmp === 0) cmp = (a.id || "").localeCompare(b.id || "");  // stabil
    return sortDir === "asc" ? cmp : -cmp;
  }
  // Filter-Filter zuruecksetzen
  function resetFilters() {
    setPrioMin(0);
    setPrioMax(100);
    setStatusFilters(new Set());
    setRoleFilters(new Set());
  }
  // Verfuegbare Status (fuer Filter-UI)
  const ALL_STATUSES = [
    { id: "triage", label: "Triage", color: "var(--color-hermes-accent-orange)" },
    { id: "todo", label: "To Do", color: "var(--color-hermes-text-secondary)" },
    { id: "in_progress", label: "In Progress", color: "var(--color-hermes-accent)" },
    { id: "review", label: "Review", color: "var(--color-hermes-accent-blue)" },
    { id: "block", label: "Block", color: "var(--color-hermes-danger)" },
    { id: "done", label: "Done", color: "var(--color-hermes-accent)" },
  ];
  // Verfuegbare Rollen (aus allTasks ableiten)
  const availableRoles = useMemo(() => {
    const set = new Set<string>();
    for (const t of (allTasks || [])) {
      if (t.assigned_role) set.add(t.assigned_role);
    }
    return Array.from(set).sort();
  }, [allTasks]);
  const isFilterActive = prioMin > 0 || prioMax < 100 || statusFilters.size > 0 || roleFilters.size > 0;
  // Filtered Tasks (global) — beruecksichtigt searchQuery + Filter (Prio/Status/Role)
  const filteredTasks = useMemo(() => {
    if (!searchQuery.trim() && !isFilterActive) return [...(allTasks || [])].sort(compareTasks);
    const result = (allTasks || []).filter((t: any) => taskMatchesAllFilters(t));
    return result.sort(compareTasks);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allTasks, searchQuery, prioMin, prioMax, statusFilters, roleFilters, sortBy, sortDir]);
  const parentTasks = (allTasks || []).filter((t: any) => !t.parent_id);
  const childTasks = (allTasks || []).filter((t: any) => t.parent_id);
  // Sortierte Parent-Tasks (mit Filter)
  const filteredParentTasks = useMemo(() => {
    let result = parentTasks;
    if (searchQuery.trim() || isFilterActive) {
      result = result.filter((p: any) => {
        // Parent muss selbst matchen ODER ein matchendes Child haben
        if (taskMatchesAllFilters(p)) return true;
        return childTasks.some((c: any) => c.parent_id === p.id && taskMatchesAllFilters(c));
      });
    }
    return [...result].sort(compareTasks);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parentTasks, childTasks, searchQuery, prioMin, prioMax, statusFilters, roleFilters, sortBy, sortDir]);
  // Sortierte Children (mit Filter)
  const filteredChildTasks = useMemo(() => {
    let result = childTasks;
    if (searchQuery.trim() || isFilterActive) {
      result = result.filter((c: any) => taskMatchesAllFilters(c));
    }
    return [...result].sort(compareTasks);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [childTasks, searchQuery, prioMin, prioMax, statusFilters, roleFilters, sortBy, sortDir]);

  function toggleTask(id: string) {
    const next = new Set(expandedTasks);
    next.has(id) ? next.delete(id) : next.add(id);
    setExpandedTasks(next);
  }

  return (
    <div>
      {/* Tab Navigation */}
      <div className="page-header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <ListChecks size={20} color="var(--color-hermes-accent-blue)" />
          Projekte
          {activeProjectData && (
            <span style={{ fontSize: 14, fontWeight: 400, color: "var(--color-hermes-text-secondary)", marginLeft: 8 }}>
              / {activeProjectData.name}
            </span>
          )}
        </h1>
        <p>Projekt-Management mit Brainstorming, Anforderungen, Tasks & Board</p>
        </div>
      </div>

      {/* Project Selector + Tabs */}
      {activeProject && (
        <div style={{ display: "flex", gap: 4, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
          {(["brainstorm", "requirements", "tasks", "board", "kpis", "brain-dev"] as const).map((tab) => (
            <button key={tab} className="btn" style={{
              background: activeTab === tab ? "var(--color-hermes-surface-2)" : "transparent",
              borderBottom: activeTab === tab ? "2px solid var(--color-hermes-accent-blue)" : "2px solid transparent",
            }} onClick={() => setActiveTab(tab)}>
              {tab === "brainstorm" && <BrainCircuit size={14} />}
              {tab === "requirements" && <FileText size={14} />}
              {tab === "tasks" && <ListChecks size={14} />}
              {tab === "kpis" && <BarChart3 size={14} />}
              {tab === "brain-dev" && <FileText size={14} />}
              {tab === "board" ? "Board" : tab === "brain-dev" ? "Brain DEV" : tab === "kpis" ? "KPIs" : tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
          <div style={{ flex: 1 }} />
          {/* === Volltext-Suche (sichtbar in Projects / Board / Tasks) === */}
          {(activeTab === "projects" || activeTab === "board" || activeTab === "tasks") && (
            <div style={{ display: "flex", alignItems: "center", gap: 6, position: "relative" }}>
              <div style={{
                display: "flex", alignItems: "center", gap: 6,
                background: "var(--color-hermes-surface)", border: "1px solid var(--color-hermes-border)",
                borderRadius: 6, padding: "4px 8px", minWidth: 280,
              }}>
                <Search size={13} color="var(--color-hermes-text-secondary)" />
                <input
                  type="text"
                  placeholder={activeTab === "projects" ? "Projekte + Tasks durchsuchen…" : "Volltextsuche ueber alle Tasks…"}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Escape") setSearchQuery(""); }}
                  style={{
                    background: "transparent", border: "none", outline: "none",
                    color: "var(--color-hermes-text)", fontSize: 12, flex: 1, minWidth: 0,
                  }}
                />
                {searchQuery && (
                  <>
                    <span className="badge badge-blue" style={{ fontSize: 9 }}>
                      {activeTab === "projects"
                        ? `${(projects || []).filter((p: any) => projectMatchesQuery(p, searchQuery, (allTasks || []).filter((t: any) => t.project_id === p.id))).length}/${(projects || []).length}`
                        : `${filteredTasks.length}/${(allTasks || []).length}`}
                    </span>
                    <button
                      className="btn"
                      style={{ padding: "0 4px", fontSize: 11, background: "transparent" }}
                      onClick={() => setSearchQuery("")}
                      title="Suche loeschen (Esc)"
                    >
                      <X size={12} />
                    </button>
                  </>
                )}
              </div>
            </div>
          )}
          {/* === Filter & Sort (sichtbar in Board / Tasks) === */}
          {(activeTab === "board" || activeTab === "tasks") && (
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              {/* Sort-Dropdown */}
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as any)}
                title="Sortieren nach"
                style={{ background: "var(--color-hermes-surface)", border: "1px solid var(--color-hermes-border)", borderRadius: 6, padding: "4px 6px", color: "var(--color-hermes-text)", fontSize: 12, cursor: "pointer" }}
              >
                <option value="prio">↕ Prio</option>
                <option value="role">↕ Verantwortlich</option>
                <option value="title">↕ Titel</option>
                <option value="status">↕ Status</option>
                <option value="created">↕ Erstellt</option>
              </select>
              <button
                className="btn"
                style={{ padding: "4px 6px", fontSize: 11 }}
                onClick={() => setSortDir((d) => d === "asc" ? "desc" : "asc")}
                title={sortDir === "asc" ? "Aufsteigend (klicken fuer absteigend)" : "Absteigend (klicken fuer aufsteigend)"}
              >
                {sortDir === "asc" ? <ArrowUp size={12} /> : <ArrowDown size={12} />}
              </button>
              {/* Filter-Toggle */}
              <button
                className="btn"
                style={{ padding: "4px 8px", fontSize: 11, background: (showFilters || isFilterActive) ? "var(--color-hermes-surface-2)" : undefined, borderBottom: isFilterActive ? "2px solid var(--color-hermes-accent-orange)" : undefined }}
                onClick={() => setShowFilters((v) => !v)}
                title="Filter ein-/ausblenden"
              >
                <Sliders size={12} /> Filter
                {isFilterActive && <span className="badge badge-orange" style={{ fontSize: 9, marginLeft: 4 }}>aktiv</span>}
              </button>
            </div>
          )}
          <span className="badge badge-blue">{activeProjectData?.name}</span>
        </div>
      )}

      {/* === Filter-Panel (aufklappbar unter den Tabs) === */}
      {activeProject && showFilters && (activeTab === "board" || activeTab === "tasks") && (
        <div className="card" style={{ marginBottom: 12, padding: 10 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "flex-start" }}>
            {/* Prio-Range */}
            <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 220 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-hermes-text-secondary)" }}>
                <Sliders size={11} style={{ marginRight: 4 }} />Prio-Bereich
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <input
                  type="number" min={0} max={100} value={prioMin}
                  onChange={(e) => setPrioMax(Math.max(prioMin, Math.min(100, parseInt(e.target.value) || 0)))}
                  style={{ width: 60, background: "var(--color-hermes-surface)", border: "1px solid var(--color-hermes-border)", borderRadius: 4, padding: "3px 6px", color: "var(--color-hermes-text)", fontSize: 12 }}
                />
                <span style={{ color: "var(--color-hermes-text-secondary)" }}>–</span>
                <input
                  type="number" min={0} max={100} value={prioMax}
                  onChange={(e) => setPrioMin(Math.min(prioMax, Math.max(0, parseInt(e.target.value) || 100)))}
                  style={{ width: 60, background: "var(--color-hermes-surface)", border: "1px solid var(--color-hermes-border)", borderRadius: 4, padding: "3px 6px", color: "var(--color-hermes-text)", fontSize: 12 }}
                />
              </div>
              {/* Slider-Track (zwei Range-Slider ueberlagert) */}
              <div style={{ position: "relative", height: 24, marginTop: 4 }}>
                <div style={{ position: "absolute", top: 10, left: 0, right: 0, height: 4, background: "var(--color-hermes-muted)", borderRadius: 2 }} />
                <div style={{ position: "absolute", top: 10, left: `${prioMin}%`, right: `${100 - prioMax}%`, height: 4, background: "var(--color-hermes-accent-blue)", borderRadius: 2 }} />
                <input type="range" min={0} max={100} value={prioMin} onChange={(e) => setPrioMin(Math.min(prioMax, parseInt(e.target.value)))} style={{ position: "absolute", top: 0, left: 0, right: 0, width: "100%", background: "transparent", pointerEvents: "auto" }} />
                <input type="range" min={0} max={100} value={prioMax} onChange={(e) => setPrioMax(Math.max(prioMin, parseInt(e.target.value)))} style={{ position: "absolute", top: 0, left: 0, right: 0, width: "100%", background: "transparent", pointerEvents: "auto" }} />
              </div>
              <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginTop: 2 }}>
                {prioMin === 0 && prioMax === 100 ? "Alle Prioritaeten" : `${prioMin} – ${prioMax}`}
              </div>
            </div>
            {/* Status-Filter */}
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-hermes-text-secondary)" }}>Status</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {ALL_STATUSES.map((s) => {
                  const active = statusFilters.has(s.id);
                  return (
                    <button
                      key={s.id}
                      className="btn"
                      style={{
                        fontSize: 10, padding: "2px 8px",
                        background: active ? s.color : "var(--color-hermes-surface)",
                        color: active ? "white" : "var(--color-hermes-text)",
                        border: `1px solid ${s.color}`,
                      }}
                      onClick={() => {
                        const next = new Set(statusFilters);
                        if (active) next.delete(s.id); else next.add(s.id);
                        setStatusFilters(next);
                      }}
                    >
                      {active ? "✓ " : ""}{s.label}
                    </button>
                  );
                })}
              </div>
            </div>
            {/* Role-Filter */}
            {availableRoles.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-hermes-text-secondary)" }}>Verantwortlich</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {availableRoles.map((r) => {
                    const active = roleFilters.has(r);
                    return (
                      <button
                        key={r}
                        className="btn"
                        style={{
                          fontSize: 10, padding: "2px 8px",
                          background: active ? "var(--color-hermes-accent-blue)" : "var(--color-hermes-surface)",
                          color: active ? "white" : "var(--color-hermes-text)",
                          border: `1px solid ${active ? "var(--color-hermes-accent-blue)" : "var(--color-hermes-border)"}`,
                        }}
                        onClick={() => {
                          const next = new Set(roleFilters);
                          if (active) next.delete(r); else next.add(r);
                          setRoleFilters(next);
                        }}
                      >
                        {ROLE_EMOJI[r] || "🤖"} {active ? "✓ " : ""}{r}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
            {/* Reset-Button */}
            {isFilterActive && (
              <div style={{ display: "flex", alignItems: "flex-end" }}>
                <button className="btn" style={{ fontSize: 11, padding: "4px 8px" }} onClick={resetFilters} title="Alle Filter zuruecksetzen">
                  <X size={11} /> Filter zuruecksetzen
                </button>
              </div>
            )}
          </div>
          {/* Live-Counter: zeigt gefilterte vs. total */}
          <div style={{ marginTop: 8, fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
            🔍 {filteredTasks.length} von {(allTasks || []).length} Tasks sichtbar
            {isFilterActive && (
              <span className="badge badge-orange" style={{ fontSize: 9, marginLeft: 6 }}>
                Prio {prioMin}–{prioMax}
                {statusFilters.size > 0 && ` · ${statusFilters.size} Status`}
                {roleFilters.size > 0 && ` · ${roleFilters.size} Rollen`}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Content */}
      {activeTab === "projects" && (
        <div>
          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <button className="btn btn-primary" onClick={() => setShowNewProject(!showNewProject)}>
              <Plus size={14} /> {showNewProject ? "Cancel" : "New Project"}
            </button>
          </div>
          {showNewProject && (
            <div className="card" style={{ marginBottom: 12 }}>
              <input className="input" placeholder="Project name" value={projectName} onChange={(e) => setProjectName(e.target.value)} autoFocus />
              <textarea className="input" style={{ marginTop: 8, minHeight: 60 }} placeholder="What do you want to achieve?" value={projectDesc} onChange={(e) => setProjectDesc(e.target.value)} />
              <button className="btn btn-primary" style={{ marginTop: 8 }} onClick={() => createProject.mutate({ name: projectName, description: projectDesc })} disabled={!projectName}>
                ✨ Create & Start Brainstorming
              </button>
            </div>
          )}
          <div className="card-grid">
            {(projects || [])
              .filter((p: any) => projectMatchesQuery(p, searchQuery, (allTasks || []).filter((t: any) => t.project_id === p.id)))
              .map((p: any) => {
                const projectTasks = (allTasks || []).filter((t: any) => t.project_id === p.id);
                const matchingTaskCount = searchQuery.trim()
                  ? projectTasks.filter((t: any) => taskMatchesQuery(t, searchQuery)).length
                  : 0;
                const nameHl = highlight(p.name || "", searchQuery);
                const descHl = highlight((p.description || "").slice(0, 100), searchQuery);
                return (
                <div key={p.id} className="card" style={{ cursor: "pointer", borderLeft: `3px solid ${p.status === "active" ? "var(--color-hermes-accent)" : "var(--color-hermes-text-secondary)"}` }} onClick={() => selectProject(p.id)}>
                  <div style={{ fontWeight: 600, fontSize: 15 }} dangerouslySetInnerHTML={{ __html: nameHl.highlighted }} />
                  <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", marginTop: 4 }} dangerouslySetInnerHTML={{ __html: descHl.highlighted }} />
                  <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginTop: 6 }}>
                    {p.brainstorm_log?.length || 0} brainstorming turns · {p.requirements_file ? "✓ requirements" : "—"}
                    {searchQuery.trim() && matchingTaskCount > 0 && (
                      <span className="badge badge-orange" style={{ fontSize: 9, marginLeft: 4 }}>{matchingTaskCount} Task-Treffer</span>
                    )}
                    <br />Created: {p.created_at ? new Date(p.created_at).toLocaleDateString() : "—"}
                  </div>
                </div>
              );
              })}
          </div>
          {searchQuery.trim() && (projects || []).filter((p: any) => projectMatchesQuery(p, searchQuery, (allTasks || []).filter((t: any) => t.project_id === p.id))).length === 0 && (
            <div className="card" style={{ textAlign: "center", padding: 24, marginTop: 12 }}>
              <p style={{ color: "var(--color-hermes-text-secondary)", margin: 0, fontSize: 13 }}>
                Keine Projekte gefunden fuer „<strong>{searchQuery}</strong>".
              </p>
            </div>
          )}
        </div>
      )}

      {/* Brainstorming */}
      {activeTab === "brainstorm" && activeProject && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <div style={{ fontSize: 13, fontWeight: 500 }}>🧠 Brainstorming</div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
                TTS: {tts.mode === "click" ? "👆 Klick" : tts.mode === "auto" ? "🔊 Auto" : "🔇 Aus"}
              </span>
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, alignItems: "start" }}>
            {/* LINKS: Chat */}
            <div>
              <div ref={brainstormRef} className="card" style={{ marginBottom: 12, maxHeight: 500, overflow: "auto", minHeight: 400 }}>
                {brainstormLog.length === 0 && <div style={{ color: "var(--color-hermes-text-secondary)", textAlign: "center", padding: 20 }}>Beschreibe dein Projektziel, um mit dem Brainstorming zu beginnen.</div>}
                {brainstormLog.map((entry: any, i: number) => {
                  return (
                  <div key={i}
                    style={{ marginBottom: 8, padding: "8px 12px", borderRadius: 8, background: entry.role === "user" ? "rgba(88,166,255,0.08)" : "rgba(46,160,67,0.08)", borderLeft: `3px solid ${entry.role === "user" ? "var(--color-hermes-accent-blue)" : "var(--color-hermes-accent)"}` }}
                  >
                    <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>{entry.role === "user" ? "🗣️ You" : "🤖 AI"}</div>
                    <div style={{ fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                      {(() => {
                        const fullText = entry.text || "";
                        // Split by sentence endings for hover-highlight
                        const parts = fullText.split(/(?<=[.!?])\s+|(?<=[.!?])(?=\S)/);
                        let charOffset = 0;
                        return parts.map((part: string, j: number) => {
                          const startOffset = charOffset;
                          charOffset += part.length;
                          return (
                            <span key={`${i}-${j}`}
                              className={`tts-part-${i}-${j}`}
                              onMouseEnter={() => {
                                if (tts.mode === "click") {
                                  document.querySelectorAll(`[class^="tts-part-${i}-"]`).forEach(el => {
                                    const idx = parseInt((el.className.match(/tts-part-\d+-\d+/)?.[0] || "").split("-").pop() || "0");
                                    if (idx >= j) {
                                      (el as HTMLElement).style.backgroundColor = "#ffd700";
                                      (el as HTMLElement).style.color = "#000";
                                      (el as HTMLElement).style.fontWeight = "bold";
                                    }
                                  });
                                }
                              }}
                              onMouseLeave={() => {
                                if (tts.mode === "click") {
                                  document.querySelectorAll(`[class^="tts-part-${i}-"]`).forEach(el => {
                                    (el as HTMLElement).style.backgroundColor = "transparent";
                                    (el as HTMLElement).style.color = "";
                                    (el as HTMLElement).style.fontWeight = "normal";
                                  });
                                }
                              }}
                              onClick={() => {
                                if (tts.mode === "click") {
                                  // Berechne Zeichen-Position im gesamten Text
                                  let globalCharPos = 0;
                                  for (let ei = 0; ei < i; ei++) {
                                    globalCharPos += (brainstormLog[ei].text || "").length;
                                  }
                                  globalCharPos += startOffset;
                                  const fullAllText = brainstormLog.map((e: any) => e.text || "").join("\n");
                                  tts.speakFrom(fullAllText, globalCharPos);
                                  // Highlight all parts from here across all entries
                                  document.querySelectorAll(`[class^="tts-part-"]`).forEach(el => {
                                    const cls = el.className.match(/tts-part-(\d+)-(\d+)/);
                                    if (cls) {
                                      const ei = parseInt(cls[1]);
                                      const pj = parseInt(cls[2]);
                                      if (ei > i || (ei === i && pj >= j)) {
                                        (el as HTMLElement).style.backgroundColor = "#ffd700";
                                        (el as HTMLElement).style.color = "#000";
                                        (el as HTMLElement).style.fontWeight = "bold";
                                      }
                                    }
                                  });
                                }
                              }}
                              style={{ cursor: tts.mode === "click" ? "pointer" : "default", borderRadius: 3, padding: "1px 0", transition: "all 0.15s", backgroundColor: "transparent", fontWeight: "normal" }}
                            >{part} </span>
                          );
                        });
                      })()}
                    </div>
                  </div>
                  );
                })}
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <DynamicTextarea placeholder={canGenerate ? "Any refinements?" : "Describe your vision..."} value={brainstormInput} onChange={(e: any) => setBrainstormInput(e.target.value)} onKeyDown={(e: any) => e.key === "Enter" && !e.shiftKey && brainstormInput.trim() && brainstormMut.mutate({ id: activeProject, text: brainstormInput })} style={{ fontFamily: "var(--font-mono)" }} />
                <button className="btn" onClick={() => brainstormMut.mutate({ id: activeProject, text: brainstormInput })} disabled={!brainstormInput.trim() || brainstormMut.isPending}>
                  <Send size={14} /> Send
                </button>
                <button className="btn" onClick={() => { setShowPipelineModal(false); pipelineMut.mutate(); }} disabled={pipelineMut.isPending || brainstormLog.length === 0} title="9-Schritte-Review-Pipeline: zeigt Verarbeitungs-Dialog mit Live-Progress">
                  {pipelineMut.isPending ? "..." : "🔍 Review"}
                </button>
                <button className="btn" onClick={() => { setActiveTab("brainstorm"); }} title="Zeigt offene Fragen direkt in der Brainstorming-Ansicht">
                  📋 Offene Fragen
                </button>
                {canGenerate && (
                  <button className="btn btn-primary" onClick={() => generateReqMut.mutate(activeProject)}>
                    <FileText size={14} /> Generate Requirements
                  </button>
                )}
              </div>
              {/* === KLÄRUNGSFRAGEN-SECTION (persistent, in normaler Brainstorming-UI) === */}
              <ClarificationSection
                completenessQuery={completenessQuery}
                inlineAnswers={inlineAnswers}
                setInlineAnswers={setInlineAnswers}
                answerMut={answerCompletenessMut}
                onStartReview={() => { setReviewPhase("completeness"); completenessMut.mutate(); }}
              />
              {/* === QUALITY-RÜCKFRAGEN-SECTION (aus NALABS-Review) === */}
              <QualityClarificationSection
                qualityQuery={qualityQuery}
                answerMut={answerQualityMut}
                onStartReview={() => { setReviewPhase("quality"); reviewMut.mutate(brainstormDoc); }}
              />
            </div>
            {/* RECHTS: Live-MD-Dokument */}
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <div style={{ fontSize: 12, fontWeight: 500 }}>📄 Live-MD-Dokument (Roh-Material)</div>
                <div style={{ display: "flex", gap: 4 }}>
                  <button className="btn" style={{ fontSize: 10, padding: "2px 6px" }} onClick={() => navigator.clipboard.writeText(brainstormDoc)} title="In Zwischenablage kopieren">
                    📋 Copy
                  </button>
                  <button className="btn" style={{ fontSize: 10, padding: "2px 6px" }} onClick={() => {
                    const blob = new Blob([brainstormDoc], { type: "text/markdown" });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `${activeProjectData?.name || "brainstorm"}.md`;
                    a.click();
                    URL.revokeObjectURL(url);
                  }} title="Als .md-Datei herunterladen">
                    💾 Download
                  </button>
                </div>
              </div>
              <pre className="card" style={{
                maxHeight: 540, overflow: "auto", padding: 12,
                fontFamily: "var(--font-mono)", fontSize: 12,
                whiteSpace: "pre-wrap", wordBreak: "break-word",
                lineHeight: 1.5, background: "var(--color-hermes-muted)",
                margin: 0,
              }}>
                {brainstormDoc}
              </pre>
              <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginTop: 4 }}>
                Wird im Requirements-Schritt zu sauberem Text weiterverarbeitet. ({brainstormDoc.length} Zeichen)
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Requirements */}
      {activeTab === "requirements" && activeProject && (
        <RequirementsTab
          projectId={activeProject}
          activeProjectData={activeProjectData}
          requirementsText={requirementsText}
          generateReqMut={generateReqMut}
          reqToTasksMut={reqToTasksMut}
        />
      )}

      {/* Board View — Kanban Columns */}
      {activeTab === "board" && activeProject && (<div>
          {/* Workflow-Notification (Toast) */}
          {workflowNotification && (
            <div
              style={{
                position: "fixed", top: 20, right: 20, zIndex: 1100,
                padding: "10px 14px", borderRadius: 6, maxWidth: 400,
                background: workflowNotification.ok ? "rgba(46,160,67,0.95)" : "rgba(248,81,73,0.95)",
                color: "white", fontSize: 13, fontWeight: 500,
                boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
              }}
            >
              {workflowNotification.ok ? "✅" : "🔄"} {workflowNotification.message}
            </div>
          )}
          {/* Triage Info Bar */}
          <div className="card" style={{ marginBottom: 12, padding: "8px 12px", display: "flex", alignItems: "center", gap: 12, borderLeft: "3px solid var(--color-hermes-accent-orange)" }}>
            <span style={{ fontSize: 13, fontWeight: 500 }}>📋 Triage</span>
            <span style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
              {searchQuery.trim()
                ? (filteredTasks || []).filter((t: any) => t.status === "triage").length
                : (allTasks || []).filter((t: any) => t.status === "triage").length
              } tasks waiting
            </span>
            {searchQuery.trim() && (
              <span className="badge badge-orange" style={{ fontSize: 10 }}>
                🔍 {filteredTasks.length} von {(allTasks || []).length} Tasks matchen
              </span>
            )}
            <button className="btn btn-primary" style={{ padding: "4px 10px", fontSize: 11 }} onClick={() => processTriageMut.mutate(activeProject)} disabled={processTriageMut.isPending}>
              <Zap size={12} /> Process Triage
            </button>
            {/* SSE Live-Indikator */}
            {activeProject && (
              <span title={sseConnected ? "Echtzeit-Updates aktiv" : "Echtzeit-Updates getrennt - Fallback Polling (5s)"} style={{
                display: "inline-flex", alignItems: "center", gap: 4,
                fontSize: 10, fontWeight: 600, padding: "2px 6px", borderRadius: 3,
                background: sseConnected ? "rgba(46,160,67,0.15)" : "var(--color-hermes-muted)",
                color: sseConnected ? "var(--color-hermes-accent)" : "var(--color-hermes-text-secondary)",
              }}>
                <span style={{
                  display: "inline-block", width: 6, height: 6, borderRadius: "50%",
                  background: sseConnected ? "var(--color-hermes-accent)" : "var(--color-hermes-text-secondary)",
                  boxShadow: sseConnected ? "0 0 4px var(--color-hermes-accent)" : "none",
                }} />
                {sseConnected ? "LIVE" : "POLL"}
              </span>
            )}
            <button className="btn" style={{ padding: "4px 10px", fontSize: 11 }} onClick={async () => {
              const title = prompt("New task title:");
              if (!title) return;
              const desc = prompt("Description (optional):") || "";
              await api.post("/kanban/tasks", { project_id: activeProject, title, description: desc, status: "triage" });
              qc.invalidateQueries({ queryKey: ["kanban-tasks"] });
            }}>
              <Plus size={12} /> New Task
            </button>
            <button
              className="btn"
              title="Aktiv-Modus: Blendet leere Spalten + Done-Spalte IMMER aus"
              style={{
                padding: "4px 10px", fontSize: 11,
                background: activeMode ? "var(--color-hermes-accent-orange)" : undefined,
                color: activeMode ? "white" : undefined,
                border: activeMode ? "1px solid var(--color-hermes-accent-orange)" : "1px solid var(--color-hermes-border)",
              }}
              onClick={() => setActiveMode((v) => !v)}
            >
              {activeMode ? "\u2713 Aktiv" : "Aktiv"}
            </button>
            <div style={{ flex: 1 }} />
            <button
              className="btn"
              style={{ padding: "4px 10px", fontSize: 11 }}
              onClick={() => {
                if (confirm("Alle Tasks dieses Projekts zurueck in Triage verschieben?")) {
                  bulkTriageMut.mutate();
                }
              }}
              disabled={bulkTriageMut.isPending || (allTasks?.length || 0) === 0}
              title="Alle Tasks dieses Projekts zurueck in Triage"
            >
              ↩︎ Alle zu Triage
            </button>
            <button
              className="btn btn-primary"
              style={{ padding: "4px 10px", fontSize: 11 }}
              onClick={() => cioReviewMut.mutate()}
              disabled={cioReviewMut.isPending || (allTasks?.length || 0) === 0}
              title="CIO prüft alle Tasks und startet dann die Implementation"
            >
              <Rocket size={12} /> Implementierung starten
            </button>
          </div>
          <div style={{ display: "flex", gap: 0, minHeight: "calc(100vh - 300px)" }}>
          <div style={{ flex: 1, display: "flex", gap: 12, overflowX: "auto", paddingBottom: 8 }}>
          {[ 
            { id: "triage", label: "Triage", color: "var(--color-hermes-accent-orange)" },
            { id: "todo", label: "To Do", color: "var(--color-hermes-text-secondary)" },
            { id: "in_progress", label: "In Progress", color: "var(--color-hermes-accent)" },
            { id: "review", label: "Review", color: "var(--color-hermes-accent-blue)" },
            { id: "block", label: "Block", color: "var(--color-hermes-danger)" },
            { id: "done", label: "Done", color: "var(--color-hermes-accent)" },
          ].map((col) => {
            // Aktiv-Modus: Done IMMER ausblenden
            if (activeMode && col.id === "done") return null;
            let colTasks = (filteredTasks || []).filter((t: any) => t.status === col.id);
            // Aktiv-Modus: leere Spalten ausblenden
            if (activeMode && colTasks.length === 0) return null;
            const isDropTarget = dragOverColumn === col.id;
            return (
              <div
                key={col.id}
                className="card"
                onDragOver={(e) => { e.preventDefault(); setDragOverColumn(col.id); }}
                onDragLeave={() => { if (dragOverColumn === col.id) setDragOverColumn(null); }}
                onDrop={(e) => {
                  e.preventDefault();
                  const taskId = e.dataTransfer.getData("text/task-id");
                  if (taskId) {
                    updateTaskStatusMut.mutate({ taskId, status: col.id });
                  } else {
                    setDragOverColumn(null);
                  }
                }}
                style={{
                  padding: 8,
                  display: "flex",
                  flexDirection: "column",
                  gap: 6,
                  minHeight: 200,
                  minWidth: 280,
                  flexShrink: 0,
                  flex: "0 0 280px",
                  background: isDropTarget ? "rgba(88,166,255,0.08)" : undefined,
                  border: isDropTarget ? "2px dashed var(--color-hermes-accent-blue)" : undefined,
                  transition: "all 0.15s",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 8px", borderBottom: `2px solid ${col.color}`, marginBottom: 4 }}>
                  <span style={{ fontWeight: 600, fontSize: 13, textTransform: "uppercase" }}>{col.label}</span>
                  <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>{colTasks.length}</span>
                </div>
                {colTasks.map((task: any) => (
                  <div
                    key={task.id}
                    className="card"
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData("text/task-id", task.id);
                      e.dataTransfer.effectAllowed = "move";
                      setDraggedTaskId(task.id);
                    }}
                    onDragEnd={() => { setDraggedTaskId(null); setDragOverColumn(null); }}
                    onClick={() => setSelectedTask(task)}
                    style={{
                      padding: "8px 10px",
                      fontSize: 13,
                      cursor: draggedTaskId === task.id ? "grabbing" : "grab",
                      borderLeft: `3px solid ${task.parent_id ? "var(--color-hermes-muted)" : "var(--color-hermes-accent-blue)"}`,
                      opacity: draggedTaskId === task.id ? 0.4 : 1,
                      transition: "opacity 0.1s",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                      <IdBadge id={task.id} variant="board" />
                      <span style={{ fontWeight: 500, flex: 1 }}>{task.title}</span>
                      {(() => {
                        const p = typeof task.priority === "number" ? task.priority : 0;
                        const isEmergency = p === 100 || task.emergency;
                        const info = isEmergency ? { bg: "var(--color-hermes-danger)", fg: "white" } : prioColor(p);
                        return (
                          <span
                            title={isEmergency ? "🚨 NOTFALL — Watchdog-Auto-Claim" : `Prio: ${p} (${prioColor(p).label})`}
                            style={{
                              fontSize: 9, fontWeight: 700, padding: "1px 5px", borderRadius: 3,
                              background: info.bg, color: info.fg,
                              animation: isEmergency ? "pulse-emergency 1.5s ease-in-out infinite" : undefined,
                              boxShadow: isEmergency ? "0 0 6px rgba(248,81,73,0.5)" : undefined,
                            }}
                          >
                            {isEmergency ? "🚨" : "🔥"} {p}
                          </span>
                        );
                      })()}
                    </div>
                    <div style={{ display: "flex", gap: 4, alignItems: "center", fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
                      {ROLE_EMOJI[task.assigned_role] || "🤖"} {task.assigned_role}
                      {!task.parent_id && <span className="badge badge-blue" style={{ fontSize: 9, marginLeft: 4 }}>Parent</span>}
                      {task.parent_id && <span style={{ fontSize: 9, marginLeft: 4 }}>↳ child</span>}
                      {task.emergency && <span style={{ fontSize: 9, color: "var(--color-hermes-danger)", fontWeight: 700, marginLeft: 4 }}>NOTFALL</span>}
                    </div>
                    {task.success_criteria?.length > 0 && (
                      <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginTop: 2 }}>
                        {task.success_criteria.slice(0, 2).map((sc: string, i: number) => (
                          <div key={i}>✓ {sc.slice(0, 40)}</div>
                        ))}
                      </div>
                    )}
                    {task.iteration_count > 0 && (
                      <div style={{ fontSize: 10, color: "var(--color-hermes-accent-orange)", marginTop: 2 }}>
                        🔄 {task.iteration_count}x iterated
                      </div>
                    )}
                    {task.last_review && !task.last_review.ok && task.status === "in_progress" && (
                      <div style={{ fontSize: 9, color: "var(--color-hermes-danger)", marginTop: 2 }} title={task.last_review.issues?.map((i:any) => i.message).join("; ")}>
                        ❌ Auto-Review: {task.last_review.issue_counts?.high || 0} kritisch
                      </div>
                    )}
                    {task.cio_approved && task.status === "done" && (
                      <div style={{ fontSize: 9, color: "var(--color-hermes-accent)", marginTop: 2 }}>
                        ✅ CIO approved
                      </div>
                    )}
                    {/* Workflow-Buttons je nach Status */}
                    {task.status === "triage" && (
                      <button className="btn" style={{ fontSize: 9, padding: "1px 6px", marginTop: 4 }} onClick={(e) => { e.stopPropagation(); workflowMut.mutate({ taskId: task.id, action: "claim" }); }} disabled={workflowMut.isPending}>
                        ▶️ Claim
                      </button>
                    )}
                    {task.status === "in_progress" && (
                      <button className="btn btn-primary" style={{ fontSize: 9, padding: "1px 6px", marginTop: 4 }} onClick={(e) => { e.stopPropagation(); workflowMut.mutate({ taskId: task.id, action: "submit_review" }); }} disabled={workflowMut.isPending}>
                        🔍 Submit Review
                      </button>
                    )}
                    {task.status === "done" && !task.cio_approved && (
                      <div style={{ display: "flex", gap: 3, marginTop: 4 }} onClick={(e) => e.stopPropagation()}>
                        <button className="btn btn-primary" style={{ fontSize: 9, padding: "1px 6px" }} onClick={() => workflowMut.mutate({ taskId: task.id, action: "cio_approve" })} disabled={workflowMut.isPending}>
                          ✅ CIO OK
                        </button>
                        <button className="btn" style={{ fontSize: 9, padding: "1px 6px" }} onClick={() => {
                          const target = prompt("Zurueck zu 'todo' oder 'in_progress'?", "todo") || "todo";
                          workflowMut.mutate({ taskId: task.id, action: "cio_reject", extra: { target, reason: "CIO-Reject (manuell)" } });
                        }} disabled={workflowMut.isPending}>
                          ❌ Reject
                        </button>
                      </div>
                    )}
                    {task.status === "block" && (
                      <button className="btn" style={{ fontSize: 9, padding: "1px 6px", marginTop: 4 }} onClick={(e) => { e.stopPropagation(); workflowMut.mutate({ taskId: task.id, action: "claim" }); }} disabled={workflowMut.isPending}>
                        🔓 Unblock
                      </button>
                    )}
                  </div>
                ))}
                {colTasks.length === 0 && (
                  <div style={{ padding: 16, textAlign: "center", color: "var(--color-hermes-text-secondary)", fontSize: 12, border: "1px dashed var(--color-hermes-border)", borderRadius: 6 }}>
                    {searchQuery.trim() ? `Keine Treffer in ${col.label}` : "Empty"}
                  </div>
                )}
              </div>
            );
          })}
        </div>
        {selectedTask && <TaskSidebar task={selectedTask} onClose={() => setSelectedTask(null)} allTasks={allTasks || []} searchQuery={searchQuery} onUpdatePrio={(id, p) => updateTaskPrioMut.mutate({ taskId: id, priority: p })} />}
      </div>
      </div>
      )}

      {/* BRAIN DEV — OpenBrain Development Knowledge */}
      {activeTab === "brain-dev" && (
        <div>
          <div className="page-header">
            <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>🧠 OpenBrain DEV</h2>
            <p>Entwicklungs-Wissen aus dem OpenBrain — SOA, Microservices, Code Standards</p>
          </div>
          {brainDev?.error && (
            <div className="card" style={{ marginBottom: 12, borderLeft: "3px solid var(--color-hermes-accent-orange)" }}>
              <p style={{ fontSize: 13, margin: 0, color: "var(--color-hermes-accent-orange)" }}>
                ⚠️ {brainDev.error}
              </p>
            </div>
          )}
          {brainDev?.thoughts?.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", marginBottom: 4 }}>
                {brainDev.total} thoughts found · Topics: {brainDev.query_topics?.join(", ")}
              </div>
              {brainDev.thoughts.map((t: any, i: number) => (
                <div key={i} className="card" style={{ padding: "10px 14px", borderLeft: "3px solid var(--color-hermes-accent-blue)" }}>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 4 }}>
                    <span className="badge badge-blue">{t.thought_type || t.type || "thought"}</span>
                    {(t.tags || []).map((tag: string) => (
                      <span key={tag} className="badge badge-orange" style={{ fontSize: 9 }}>{tag}</span>
                    ))}
                  </div>
                  <pre style={{ fontFamily: "var(--font-mono)", fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-word", margin: 0, color: "var(--color-hermes-text)", lineHeight: 1.5, maxHeight: 200, overflow: "auto" }}>
                    {t.content || JSON.stringify(t)}
                  </pre>
                </div>
              ))}
            </div>
          ) : (
            <div className="card" style={{ textAlign: "center", padding: 40 }}>
              <p style={{ color: "var(--color-hermes-text-secondary)", margin: 0 }}>
                {brainDev?.error ? "OpenBrain nicht konfiguriert." : "Keine Entwicklungsdaten gefunden."}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Tasks with Parent/Child */}
      {activeTab === "tasks" && activeProject && (
        <div style={{ display: "flex", gap: 0 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
            <button className="btn" onClick={() => reqToTasksMut.mutate(activeProject)} disabled={reqToTasksMut.isPending}>
              <Zap size={14} /> Re-generate Tasks
            </button>
            <span style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", alignSelf: "center" }}>
              {searchQuery.trim() ? (
                <>
                  {filteredParentTasks.length} von {parentTasks.length} parent · {filteredChildTasks.length} von {childTasks.length} children
                </>
              ) : (
                <>{allTasks?.length || 0} tasks · {parentTasks.length} parent · {childTasks.length} children</>
              )}
            </span>
            {searchQuery.trim() && (
              <span className="badge badge-orange" style={{ fontSize: 10 }}>
                🔍 {filteredTasks.length} Treffer
              </span>
            )}
          </div>

          {/* Task Tree */}
          {filteredParentTasks.map((parent: any) => {
            const allChildren = childTasks.filter((c: any) => c.parent_id === parent.id);
            // Bei Suche: zeige nur matchende Children
            const children = searchQuery.trim()
              ? allChildren.filter((c: any) => taskMatchesQuery(c, searchQuery))
              : allChildren;
            // Bei Suche: automatisch expandiert
            const isExpanded = searchQuery.trim() ? true : expandedTasks.has(parent.id);
            const parentTitleHl = highlight(parent.title || "", searchQuery);
            return (
              <div key={parent.id} className="card" style={{ marginBottom: 8, padding: "10px 14px" }}>
                {/* Parent */}
                <div style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }} onClick={() => { toggleTask(parent.id); setSelectedTask(parent); }}>
                  {allChildren.length > 0 ? (isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />) : <div style={{ width: 14 }} />}
                  <IdBadge id={parent.id} variant="board" />
                  <span style={{ fontWeight: 600, fontSize: 14, flex: 1 }} dangerouslySetInnerHTML={{ __html: parentTitleHl.highlighted }} />
                  {(() => {
                    const p = typeof parent.priority === "number" ? parent.priority : 0;
                    const isEmergency = p === 100 || parent.emergency;
                    const info = isEmergency ? { bg: "var(--color-hermes-danger)", fg: "white" } : prioColor(p);
                    return (
                      <span
                        title={isEmergency ? "🚨 NOTFALL — Watchdog-Auto-Claim" : `Prio: ${p} (${prioColor(p).label})`}
                        style={{
                          fontSize: 10, fontWeight: 700, padding: "1px 6px", borderRadius: 3,
                          background: info.bg, color: info.fg,
                          animation: isEmergency ? "pulse-emergency 1.5s ease-in-out infinite" : undefined,
                          boxShadow: isEmergency ? "0 0 6px rgba(248,81,73,0.5)" : undefined,
                        }}
                      >
                        {isEmergency ? "🚨" : "🔥"} {p}
                      </span>
                    );
                  })()}
                  <span className={`badge ${parent.status === "done" ? "badge-green" : parent.status === "in_progress" ? "badge-orange" : "badge-blue"}`}>{parent.status}</span>
                  <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>{ROLE_EMOJI[parent.assigned_role] || "🤖"} {parent.assigned_role}</span>
                  {parent.iteration_count > 0 && <span className="badge badge-orange" style={{ fontSize: 9 }}>{parent.iteration_count}x iterated</span>}
                  {parent.emergency && <span style={{ fontSize: 9, color: "var(--color-hermes-danger)", fontWeight: 700 }}>🚨 NOTFALL</span>}
                </div>
                {parent.success_criteria?.length > 0 && (
                  <div style={{ marginTop: 4, fontSize: 11, color: "var(--color-hermes-text-secondary)", paddingLeft: 22 }}>
                    <Target size={10} style={{ marginRight: 4 }} />
                    {parent.success_criteria.map((sc: string, i: number) => <span key={i} style={{ marginRight: 8 }}>✓ {sc}</span>)}
                  </div>
                )}
                {/* PERT-Rollup (Parent) */}
                {parent.pert_rollup && (
                  <div style={{ marginTop: 6, paddingLeft: 22, fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
                    <span className="badge badge-orange" style={{ fontSize: 9 }}>PERT</span>{" "}
                    Gesamt: <strong>{parent.pert_rollup.total_expected_hours}h</strong> (±{parent.pert_rollup.total_std_hours}h, 95% CI: {parent.pert_rollup.ci_95_low_hours}h–{parent.pert_rollup.ci_95_high_hours}h) · {parent.pert_rollup.task_count} Tasks
                  </div>
                )}

                {/* Children */}
                {isExpanded && children.length > 0 && (
                  <div style={{ marginTop: 8, marginLeft: 20, borderLeft: "2px solid var(--color-hermes-muted)", paddingLeft: 12, display: "flex", flexDirection: "column", gap: 6 }}>
                    {children.map((child: any) => {
                      const childTitleHl = highlight(child.title || "", searchQuery);
                      const childIsMatch = searchQuery.trim() ? taskMatchesQuery(child, searchQuery) : false;
                      return (
                      <div key={child.id} style={{ padding: "6px 10px", background: childIsMatch ? "rgba(255,213,79,0.1)" : "var(--color-hermes-muted)", borderRadius: 6, borderLeft: childIsMatch ? "2px solid var(--color-hermes-accent-orange)" : "none" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <GitBranch size={10} color="var(--color-hermes-text-secondary)" />
                          <IdBadge id={child.id} variant="child" />
                          <span style={{ fontWeight: 500, fontSize: 13 }} dangerouslySetInnerHTML={{ __html: childTitleHl.highlighted }} />
                          <span className={`badge ${child.status === "done" ? "badge-green" : child.status === "in_progress" ? "badge-orange" : "badge-blue"}`} style={{ fontSize: 9 }}>{child.status}</span>
                          <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>{ROLE_EMOJI[child.assigned_role] || "🤖"} {child.assigned_role}</span>
                          {child.iteration_count > 0 && <span style={{ fontSize: 9, color: "var(--color-hermes-accent-orange)" }}>iter: {child.iteration_count}x</span>}
                        </div>
                        <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginTop: 2 }}>
                          {child.success_criteria?.map((sc: string, i: number) => (
                            <span key={i} style={{ marginRight: 6, fontSize: 10 }}>✅ {sc}</span>
                          ))}
                          {child.requirement_ref && <span className="badge badge-blue" style={{ fontSize: 9, marginLeft: 6 }}>→ {child.requirement_ref}</span>}
                          {child.pert && (
                            <span style={{ marginLeft: 8, fontSize: 9, color: "var(--color-hermes-accent-orange)" }}>
                              ⏱ PERT: opt {child.pert.opt}h / ml {child.pert.ml}h / pess {child.pert.pess}h → <strong>{child.pert.expected}h</strong> (±{child.pert.std_dev}h)
                            </span>
                          )}
                        </div>
                        {child.description?.length > 80 && (
                          <details style={{ marginTop: 4 }}>
                            <summary style={{ fontSize: 10, color: "var(--color-hermes-accent-blue)", cursor: "pointer" }}>Description</summary>
                            <pre style={{ fontSize: 10, margin: "4px 0 0", whiteSpace: "pre-wrap", color: "var(--color-hermes-text-secondary)" }}>{child.description}</pre>
                          </details>
                        )}
                      </div>
                    );
                    })}
                  </div>
                )}

                {/* References */}
                {parent.references?.length > 0 && (
                  <div style={{ marginTop: 4, fontSize: 10, color: "var(--color-hermes-text-secondary)", paddingLeft: 22 }}>
                    References: {parent.references.join(", ")}
                  </div>
                )}
              </div>
            );
          })}
          {parentTasks.length === 0 && <div style={{ color: "var(--color-hermes-text-secondary)", textAlign: "center", padding: 20 }}>No tasks yet. Convert requirements to tasks first.</div>}
          {searchQuery.trim() && parentTasks.length > 0 && filteredParentTasks.length === 0 && (
            <div className="card" style={{ textAlign: "center", padding: 24 }}>
              <p style={{ color: "var(--color-hermes-text-secondary)", margin: 0, fontSize: 13 }}>
                Keine Tasks gefunden fuer „<strong>{searchQuery}</strong>“. Pruefe die Schreibweise oder loesche die Suche.
              </p>
            </div>
          )}
        </div>
        {selectedTask && <TaskSidebar task={selectedTask} onClose={() => setSelectedTask(null)} allTasks={allTasks || []} onCreateSubtasks={(id) => setShowSubtaskModal(id)} onAggregate={(id) => aggregateMut.mutate(id)} searchQuery={searchQuery} onUpdatePrio={(id, p) => updateTaskPrioMut.mutate({ taskId: id, priority: p })} />}
      </div>
      )}
      {activeTab === "kpis" && activeProject && (
        <div>
          <div className="card-grid" style={{ marginBottom: 24 }}>
            {(kpiData?.kpis || []).map((kpi: any) => {
              const pct = kpi.target > 0 ? (kpi.value / kpi.target) * 100 : 0;
              return (
                <div key={kpi.name} className="stat-card">
                  <div className="label">{kpi.name}</div>
                  <div className="value" style={{ color: pct >= 80 ? "var(--color-hermes-accent)" : pct >= 50 ? "var(--color-hermes-accent-orange)" : "var(--color-hermes-danger)" }}>
                    {kpi.value}{kpi.unit === "%" ? "%" : ""}
                    <span style={{ fontSize: 12, fontWeight: 400, marginLeft: 8, color: "var(--color-hermes-text-secondary)" }}>
                      / {kpi.target}{kpi.unit === "%" ? "%" : ""}
                    </span>
                  </div>
                  <div style={{ marginTop: 6, height: 4, background: "var(--color-hermes-muted)", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${Math.min(pct, 100)}%`, background: pct >= 80 ? "var(--color-hermes-accent)" : pct >= 50 ? "var(--color-hermes-accent-orange)" : "var(--color-hermes-danger)", borderRadius: 2 }} />
                  </div>
                  <div className="sublabel">{kpi.category}</div>
                </div>
              );
            })}
          </div>
          <div className="card">
            <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 8px" }}>💡 Efficiency Tips</h3>
            <ul style={{ margin: 0, padding: "0 0 0 16px", fontSize: 12, color: "var(--color-hermes-text-secondary)", lineHeight: 1.8 }}>
              {(kpiData?.kpis || []).filter((k: any) => k.value < k.target).map((kpi: any) => (
                <li key={kpi.name}>{kpi.name}: {kpi.value}/{kpi.target} — needs improvement. Consider assigning sub-agents.</li>
              ))}
              {(!kpiData?.kpis || kpiData.kpis.every((k: any) => k.value >= k.target)) && (
                <li>All KPIs are on target. Great job! Consider optimizing further for efficiency.</li>
              )}
            </ul>
          </div>
        </div>
      )}

      {/* No project selected */}
      {!activeProject && activeTab === "projects" && (projects || []).length === 0 && !showNewProject && (
        <div className="card" style={{ textAlign: "center", padding: 40 }}>
          <BrainCircuit size={40} style={{ color: "var(--color-hermes-text-secondary)", marginBottom: 12, opacity: 0.3 }} />
          <p style={{ color: "var(--color-hermes-text-secondary)" }}>Create a project to start brainstorming, defining requirements, and tracking tasks.</p>
        </div>
      )}

      {/* === CIO-REVIEW-MODAL === */}
      {showCioReviewModal && cioReviewResult && (
        <CioReviewModal
          result={cioReviewResult}
          onClose={() => setShowCioReviewModal(false)}
          onProceed={() => startImplMut.mutate()}
          isStarting={startImplMut.isPending}
        />
      )}

      {/* === IMPLEMENTATION-PLAN-MODAL === */}
      {showImplementationModal && implementationResult && (
        <ImplementationPlanModal
          result={implementationResult}
          onClose={() => setShowImplementationModal(false)}
          onMarkStepDone={(stepId) => markStepDoneMut.mutate(stepId)}
          isMarking={markStepDoneMut.isPending}
        />
      )}

      {/* === SUB-TASK-MODAL === */}
      {showSubtaskModal && (
        <SubTaskModal
          parentTask={(allTasks || []).find((t: any) => t.id === showSubtaskModal)}
          onClose={() => setShowSubtaskModal(null)}
          onSubmit={(subtasks) => createSubtasksMut.mutate({ taskId: showSubtaskModal, subtasks })}
          isLoading={createSubtasksMut.isPending}
        />
      )}

      {/* === 9-SCHRITTE-REVIEW-PIPELINE-MODAL === */}
      {showPipelineModal && (
        <ReviewPipelineModal
          result={pipelineResult}
          isRunning={pipelineMut.isPending}
          onClose={() => setShowPipelineModal(false)}
          onGoToBrainstorm={() => { setShowPipelineModal(false); setActiveTab("brainstorm"); }}
        />
      )}

      {/* === 2-STUFIGER REVIEW-MODAL === */}
      {showReviewModal && (
        reviewPhase === "completeness-clarify" && completenessResult ? (
          <TwoStageClarifyModal
            completenessResult={completenessResult}
            answers={clarificationAnswers}
            setAnswers={setClarificationAnswers}
            onClose={() => { setShowReviewModal(false); setReviewPhase("idle"); }}
            onSubmitAll={async () => {
              // Erst Vollständigkeitspruefung lokal (alle Fragen beantwortet?)
              const allAnswered = (completenessResult.clarifications || []).every((c: any) => (clarificationAnswers[c.id] || "").trim());
              if (!allAnswered) {
                alert("Bitte alle Klaerungsfragen beantworten.");
                return;
              }
              // Dann Phase 2: Quality-Check
              setReviewPhase("quality");
              reviewMut.mutate(brainstormDoc);
            }}
          />
        ) : reviewPhase === "quality" && reviewResult ? (
          <TwoStageQualityModal
            reviewResult={reviewResult}
            onClose={() => { setShowReviewModal(false); setReviewPhase("done"); }}
            onProceed={() => {
              setShowReviewModal(false);
              setReviewPhase("done");
              generateReqMut.mutate(activeProject);
            }}
            onReReview={() => reviewMut.mutate(brainstormDoc)}
            isReReviewing={reviewMut.isPending}
            canGenerate={canGenerate}
          />
        ) : null
      )}

      {/* === REVIEW-MODAL (Legacy, fuer manuellen Quality-Aufruf) === */}
      {showReviewModal && reviewResult && reviewPhase === "idle" && (
        <div
          onClick={() => setShowReviewModal(false)}
          style={{
            position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
            background: "rgba(0,0,0,0.55)", zIndex: 1000,
            display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="card"
            style={{
              maxWidth: 720, width: "100%", maxHeight: "85vh", overflow: "auto",
              padding: 20, display: "flex", flexDirection: "column", gap: 14,
            }}
          >
            {/* Header */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <h2 style={{ margin: 0, fontSize: 18, display: "flex", alignItems: "center", gap: 8 }}>
                  🔍 Quality Review
                </h2>
                <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", marginTop: 4 }}>
                  Prüfung auf Rechtschreibung, Zeichensetzung, Widersprüche & Vollständigkeit
                </div>
              </div>
              <button className="btn" style={{ padding: "4px 10px" }} onClick={() => setShowReviewModal(false)}>✕</button>
            </div>

            {/* Score-Banner */}
            {(() => {
              const counts = reviewResult.issue_counts || { high: 0, medium: 0, low: 0 };
              const score = reviewResult.score;
              const colorMap: Record<string, string> = {
                ok: "var(--color-hermes-accent)",
                minor: "var(--color-hermes-accent-blue)",
                review: "var(--color-hermes-accent-orange)",
                block: "var(--color-hermes-danger)",
              };
              const labelMap: Record<string, string> = {
                ok: "✅ Alles OK",
                minor: "🟦 Kleinere Hinweise",
                review: "🟧 Manuelle Prüfung empfohlen",
                block: "🟥 Kritische Issues — bitte zuerst beheben",
              };
              return (
                <div
                  style={{
                    padding: "10px 14px", borderRadius: 6,
                    background: colorMap[score] + "20",
                    borderLeft: `4px solid ${colorMap[score]}`,
                  }}
                >
                  <div style={{ fontSize: 14, fontWeight: 600, color: colorMap[score] }}>{labelMap[score]}</div>
                  <div style={{ fontSize: 11, marginTop: 2, color: "var(--color-hermes-text-secondary)" }}>
                    {counts.high} kritisch · {counts.medium} mittel · {counts.low} gering
                  </div>
                </div>
              );
            })()}

            {/* Stats */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
              {[
                { label: "Zeichen", value: reviewResult.stats?.total_chars || 0 },
                { label: "Zeilen", value: reviewResult.stats?.total_lines || 0 },
                { label: "Vollständigkeit", value: `${reviewResult.stats?.completeness_pct || 0}%` },
                { label: "Offene Fragen", value: reviewResult.stats?.open_questions || 0 },
              ].map((s, i) => (
                <div key={i} className="card" style={{ padding: "8px 10px", textAlign: "center" }}>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>{s.value}</div>
                  <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>{s.label}</div>
                </div>
              ))}
            </div>

            {/* Findings-Liste */}
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>📋 Findings ({(reviewResult.issues || []).length})</div>
              {(reviewResult.issues || []).length === 0 ? (
                <div className="card" style={{ textAlign: "center", padding: 16, color: "var(--color-hermes-text-secondary)" }}>
                  Keine Probleme gefunden — bereit für Requirements.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 280, overflow: "auto" }}>
                  {(reviewResult.issues || []).map((iss: any, i: number) => {
                    const sevColor = iss.severity === "high" ? "var(--color-hermes-danger)" : iss.severity === "medium" ? "var(--color-hermes-accent-orange)" : "var(--color-hermes-accent-blue)";
                    const catIcon: Record<string, string> = { completeness: "✅", punctuation: "⸮", spelling: "🔤", contradiction: "⚠️", redundancy: "🗂️" };
                    return (
                      <div key={i} className="card" style={{ padding: "8px 12px", borderLeft: `3px solid ${sevColor}` }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 }}>
                          <div style={{ fontSize: 12, fontWeight: 600 }}>
                            {catIcon[iss.category] || "•"} {iss.category.toUpperCase()}
                            <span style={{ marginLeft: 6, fontSize: 10, color: sevColor }}>[{iss.severity}]</span>
                          </div>
                          <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>{iss.location}</div>
                        </div>
                        <div style={{ fontSize: 12, color: "var(--color-hermes-text)", marginTop: 2 }}>{iss.message}</div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Action-Buttons */}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 4 }}>
              <button className="btn" onClick={() => setShowReviewModal(false)}>Schließen</button>
              <button
                className="btn"
                onClick={() => reviewMut.mutate(brainstormDoc)}
                disabled={reviewMut.isPending}
                title="Erneut prüfen (z.B. nach Edits)"
              >
                🔄 Re-Review
              </button>
              <button
                className="btn btn-primary"
                onClick={() => {
                  setShowReviewModal(false);
                  generateReqMut.mutate(activeProject);
                }}
                disabled={reviewResult.score === "block" || !canGenerate}
                title={reviewResult.score === "block" ? "Erst kritische Issues beheben" : "Übernimmt das geprüfte MD in Requirements"}
              >
                ✅ Übernehmen & Generieren
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// === REQUIREMENTS-TAB (mit Export, Versionen, Diff) ===
function RequirementsTab({ projectId, activeProjectData, requirementsText, generateReqMut, reqToTasksMut }: any) {
  const [showVersions, setShowVersions] = useState(false);
  const [showDiff, setShowDiff] = useState(false);
  const [versions, setVersions] = useState<any[]>([]);
  const [diffData, setDiffData] = useState<any | null>(null);
  const [exportResult, setExportResult] = useState<any | null>(null);

  const loadVersions = async () => {
    try {
      const v = await api.listRequirementVersions(projectId);
      setVersions(v);
      setShowVersions(true);
    } catch (e) {}
  };
  const loadDiff = async () => {
    try {
      const d = await api.diffRequirements(projectId);
      setDiffData(d);
      setShowDiff(true);
    } catch (e: any) {
      alert(`Diff nicht möglich: ${e.message || e}`);
    }
  };
  const doExport = async (format: string) => {
    try {
      const r = await api.exportRequirements(projectId, format);
      setExportResult(r);
    } catch (e: any) {
      alert(`Export fehlgeschlagen: ${e.message || e}`);
    }
  };

  return (
    <div>
      {/* Action-Bar */}
      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
        <button className="btn" onClick={() => { generateReqMut.mutate(projectId); }} disabled={generateReqMut.isPending}>
          <FileText size={14} /> Regenerate
        </button>
        <button className="btn btn-primary" onClick={() => reqToTasksMut.mutate(projectId)} disabled={reqToTasksMut.isPending}>
          <ListChecks size={14} /> Convert to Tasks
        </button>
        <div style={{ width: 1, height: 20, background: "var(--color-hermes-border)" }} />
        <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>Export:</span>
        {["md", "html", "json", "txt"].map((fmt) => (
          <button key={fmt} className="btn" style={{ fontSize: 11, padding: "2px 8px" }} onClick={() => doExport(fmt)}>
            {fmt.toUpperCase()}
          </button>
        ))}
        <div style={{ width: 1, height: 20, background: "var(--color-hermes-border)" }} />
        <button className="btn" style={{ fontSize: 11, padding: "2px 8px" }} onClick={loadVersions}>
          📚 Versionen
        </button>
        <button className="btn" style={{ fontSize: 11, padding: "2px 8px" }} onClick={loadDiff}>
          🔀 Diff
        </button>
      </div>

      {/* Export-Result */}
      {exportResult && (
        <div className="card" style={{ marginBottom: 12, padding: 12, borderLeft: "3px solid var(--color-hermes-accent)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>📥 Export: {exportResult.filename} ({exportResult.format.toUpperCase()}, {exportResult.content.length} Zeichen)</div>
            <button className="btn" style={{ padding: "2px 6px", fontSize: 10 }} onClick={() => setExportResult(null)}>✕</button>
          </div>
          <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
            <button className="btn" style={{ fontSize: 11, padding: "2px 8px" }} onClick={() => navigator.clipboard.writeText(exportResult.content)}>
              📋 Copy
            </button>
            <button className="btn" style={{ fontSize: 11, padding: "2px 8px" }} onClick={() => {
              const blob = new Blob([exportResult.content], { type: exportResult.mime });
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = exportResult.filename;
              a.click();
              URL.revokeObjectURL(url);
            }}>
              💾 Download {exportResult.filename}
            </button>
          </div>
          <pre style={{ maxHeight: 200, overflow: "auto", fontSize: 10, fontFamily: "var(--font-mono)", background: "var(--color-hermes-muted)", padding: 8, borderRadius: 4, whiteSpace: "pre-wrap" }}>
            {exportResult.content.slice(0, 2000)}{exportResult.content.length > 2000 ? "..." : ""}
          </pre>
        </div>
      )}

      {/* Versions-Modal */}
      {showVersions && (
        <div onClick={() => setShowVersions(false)} style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(0,0,0,0.55)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
          <div onClick={(e) => e.stopPropagation()} className="card" style={{ maxWidth: 720, width: "100%", maxHeight: "85vh", overflow: "auto", padding: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <h2 style={{ margin: 0, fontSize: 16 }}>📚 SRS-Versionen ({versions.length})</h2>
              <button className="btn" onClick={() => setShowVersions(false)}>✕</button>
            </div>
            {versions.length === 0 ? (
              <div style={{ color: "var(--color-hermes-text-secondary)", textAlign: "center", padding: 20 }}>Keine Versionen gefunden.</div>
            ) : (
              <table className="data-table">
                <thead><tr><th>Version</th><th>Datei</th><th>Größe</th><th>Geändert</th></tr></thead>
                <tbody>
                  {versions.map((v: any) => (
                    <tr key={v.path}>
                      <td><span className="badge badge-blue">v{v.version}</span></td>
                      <td style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>{v.file}</td>
                      <td>{v.size_bytes} B</td>
                      <td style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>{new Date(v.modified).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* Diff-Modal */}
      {showDiff && diffData && (
        <div onClick={() => setShowDiff(false)} style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(0,0,0,0.55)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
          <div onClick={(e) => e.stopPropagation()} className="card" style={{ maxWidth: 900, width: "100%", maxHeight: "85vh", overflow: "auto", padding: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <h2 style={{ margin: 0, fontSize: 16 }}>🔀 SRS-Diff: {diffData.from_lines} → {diffData.to_lines} Zeilen</h2>
              <button className="btn" onClick={() => setShowDiff(false)}>✕</button>
            </div>
            <div style={{ fontSize: 11, marginBottom: 8 }}>
              <span style={{ color: "var(--color-hermes-accent)" }}>+{diffData.added}</span> hinzugefügt ·{" "}
              <span style={{ color: "var(--color-hermes-danger)" }}>-{diffData.removed}</span> entfernt
            </div>
            <pre style={{ fontFamily: "var(--font-mono)", fontSize: 10, lineHeight: 1.4, maxHeight: 500, overflow: "auto", background: "var(--color-hermes-muted)", padding: 12, borderRadius: 4, whiteSpace: "pre-wrap" }}>
              {diffData.diff.split("\n").map((line: string, i: number) => {
                let bg = "transparent";
                let color = "var(--color-hermes-text)";
                if (line.startsWith("+") && !line.startsWith("+++")) { bg = "rgba(46,160,67,0.15)"; color = "var(--color-hermes-accent)"; }
                else if (line.startsWith("-") && !line.startsWith("---")) { bg = "rgba(248,81,73,0.15)"; color = "var(--color-hermes-danger)"; }
                else if (line.startsWith("@@")) { bg = "var(--color-hermes-surface-2)"; color = "var(--color-hermes-accent-blue)"; }
                return <div key={i} style={{ background: bg, color, padding: "0 4px" }}>{line}</div>;
              })}
            </pre>
          </div>
        </div>
      )}

      {/* SRS-Content */}
      <div className="card" style={{ fontFamily: "var(--font-mono)", fontSize: 12, lineHeight: 1.6, whiteSpace: "pre-wrap", overflow: "auto", maxHeight: "calc(100vh - 300px)" }}>
        {requirementsText || (activeProjectData?.requirements_file ? "Loading..." : "Generate requirements first.")}
      </div>
    </div>
  );
}

// === QUALITY-CLARIFICATION-SECTION (Brainstorming-Tab) ===
function QualityClarificationSection({ qualityQuery, answerMut, onStartReview }: any) {
  const data = qualityQuery.data;
  if (!data || !data.clarifications || data.clarifications.length === 0) return null;
  const clarifications = data.clarifications;
  const total = clarifications.length;
  const answered = clarifications.filter((c: any) => {
    const a = c.user_answer || data.answers?.[c.id];
    if (!a) return false;
    if (typeof a === "string") return a.trim().length > 0;
    if (typeof a === "object") return (a.text || "").trim().length > 0;
    return false;
  }).length;
  const open = total - answered;
  const isComplete = open === 0;
  if (isComplete) {
    return (
      <div className="card" style={{ marginTop: 12, padding: 10, background: "rgba(46,160,67,0.1)", borderLeft: "3px solid var(--color-hermes-accent)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
          <Check size={14} color="var(--color-hermes-accent)" />
          <span style={{ fontWeight: 600, color: "var(--color-hermes-accent)" }}>Quality-Rückfragen: alle {total} beantwortet</span>
        </div>
      </div>
    );
  }
  const openQuestions = clarifications.filter((c: any) => {
    const a = c.user_answer || data.answers?.[c.id];
    if (!a) return true;
    if (typeof a === "string") return a.trim().length === 0;
    if (typeof a === "object") return (a.text || "").trim().length === 0;
    return true;
  });
  return (
    <div className="card" style={{ marginTop: 12, padding: 10, borderLeft: `3px solid var(--color-hermes-accent-orange)` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: open > 0 ? 8 : 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 12, fontWeight: 600 }}>🧪 Quality-Rückfragen (NALABS)</span>
          <span className={`badge ${open === 0 ? "badge-green" : "badge-orange"}`} style={{ fontSize: 10 }}>
            {answered} / {total} beantwortet
          </span>
          {open > 0 && <span style={{ fontSize: 10, color: "var(--color-hermes-accent-orange)" }}>⏳ {open} offen</span>}
        </div>
        <button className="btn" style={{ fontSize: 10, padding: "2px 8px" }} onClick={onStartReview} title="Re-Review starten">
          🔄 Re-Review
        </button>
      </div>
      {open > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 240, overflow: "auto" }}>
          {openQuestions.map((c: any) => {
            const existing = c.user_answer || data.answers?.[c.id];
            const existingText = existing ? (typeof existing === "object" ? existing.text : existing) : "";
            return <QualityAnswerRow key={c.id} c={c} answerMut={answerMut} existingText={existingText} />;
          })}
        </div>
      )}
    </div>
  );
}

function QualityAnswerRow({ c, answerMut, existingText }: { c: any; answerMut: any; existingText: string }) {
  const [text, setText] = useState(existingText);
  return (
    <div className="card" style={{ padding: 8, background: "var(--color-hermes-surface-2)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
        <span className="badge badge-orange" style={{ fontSize: 9 }}>{c.category}</span>
        {c.issue_ref && <span style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)" }}>→ {c.issue_ref}</span>}
      </div>
      <div style={{ fontSize: 12, marginBottom: 4 }}>{c.question}</div>
      {c.context && <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", fontStyle: "italic", marginBottom: 4 }}>{c.context}</div>}
      <div style={{ display: "flex", gap: 4 }}>
        <input
          className="input"
          style={{ flex: 1, fontSize: 12, padding: "4px 8px" }}
          placeholder="Deine Antwort..."
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <button
          className="btn"
          style={{ fontSize: 11, padding: "2px 10px" }}
          onClick={() => {
            if (text.trim()) {
              answerMut.mutate({ id: c.id, text: text.trim() });
            }
          }}
          disabled={!text.trim() || answerMut.isPending}
        >
          ✓
        </button>
      </div>
    </div>
  );
}

// === INLINE-RÜCKFRAGEN-LISTE (im Quality-Modal) ===
function ClarificationAnswerList({ clarifications, inlineSave }: { clarifications: any[]; inlineSave: (id: string, text: string) => Promise<void> }) {
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  return (
    <div>
      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: "var(--color-hermes-accent-orange)" }}>
        🟧 Rückfragen an User ({clarifications.length}) — bitte unten beantworten
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 320, overflow: "auto" }}>
        {clarifications.map((c: any) => {
          const draft = drafts[c.id] ?? "";
          const isSaving = saving[c.id];
          return (
            <div key={c.id} className="card" style={{ padding: 8, borderLeft: "3px solid var(--color-hermes-accent-orange)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                <span className="badge badge-orange" style={{ fontSize: 9 }}>{c.category}</span>
                {c.issue_ref && <span style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)" }}>→ {c.issue_ref}</span>}
              </div>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>{c.question}</div>
              {c.context && <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginBottom: 4, fontStyle: "italic" }}>{c.context}</div>}
              <div style={{ display: "flex", gap: 4 }}>
                <input
                  className="input"
                  style={{ flex: 1, fontSize: 12, padding: "4px 8px" }}
                  placeholder="Deine Antwort..."
                  value={draft}
                  onChange={(e) => setDrafts({ ...drafts, [c.id]: e.target.value })}
                />
                <button
                  className="btn btn-primary"
                  style={{ fontSize: 11, padding: "2px 10px" }}
                  disabled={!draft.trim() || isSaving}
                  onClick={async () => {
                    setSaving({ ...saving, [c.id]: true });
                    try {
                      await inlineSave(c.id, draft.trim());
                      setDrafts({ ...drafts, [c.id]: "" });
                    } finally {
                      setSaving({ ...saving, [c.id]: false });
                    }
                  }}
                >
                  {isSaving ? "..." : "✓ Speichern"}
                </button>
              </div>
              <div style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)", marginTop: 4, fontStyle: "italic" }}>
                💡 Die Antwort wird automatisch ins Brainstorming-Log uebernommen und beim naechsten Review beruecksichtigt.
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// === KLÄRUNGSFRAGEN-SECTION (Brainstorming-UI) ===
function ClarificationSection({ completenessQuery, inlineAnswers, setInlineAnswers, answerMut, onStartReview }: any) {
  const data = completenessQuery.data;
  if (!data || !data.clarifications || data.clarifications.length === 0) return null;
  const clarifications = data.clarifications;
  const total = clarifications.length;
  const answered = clarifications.filter((c: any) => c.answered).length;
  const open = total - answered;
  const isComplete = data.is_complete;
  if (isComplete) {
    return (
      <div className="card" style={{ marginTop: 12, padding: 10, background: "rgba(46,160,67,0.1)", borderLeft: "3px solid var(--color-hermes-accent)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
          <Check size={14} color="var(--color-hermes-accent)" />
          <span style={{ fontWeight: 600, color: "var(--color-hermes-accent)" }}>Vollständig: alle {total} Klärungsfragen beantwortet</span>
        </div>
      </div>
    );
  }
  const openQuestions = clarifications.filter((c: any) => !c.answered);
  return (
    <div className="card" style={{ marginTop: 12, padding: 10, borderLeft: `3px solid ${open > 0 ? "var(--color-hermes-accent-orange)" : "var(--color-hermes-accent)"}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: open > 0 ? 8 : 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 12, fontWeight: 600 }}>📋 Klärungsfragen</span>
          <span className={`badge ${open === 0 ? "badge-green" : open > 0 ? "badge-orange" : "badge-blue"}`} style={{ fontSize: 10 }}>
            {answered} / {total} beantwortet
          </span>
          {open > 0 && <span style={{ fontSize: 10, color: "var(--color-hermes-accent-orange)" }}>⏳ {open} offen</span>}
        </div>
        <button className="btn" style={{ fontSize: 10, padding: "2px 8px" }} onClick={onStartReview} title="Vollständigkeit + Qualität prüfen">
          🔍 Review starten
        </button>
      </div>
      {open > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 280, overflow: "auto" }}>
          {openQuestions.map((c: any) => {
            const localAnswer = inlineAnswers[c.id] ?? (c.user_answer?.text || "");
            return (
              <div key={c.id} className="card" style={{ padding: 8, background: "var(--color-hermes-surface-2)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                  <span className="badge badge-blue" style={{ fontSize: 9 }}>{c.phase}</span>
                  <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>{c.category}</span>
                </div>
                <div style={{ fontSize: 12, marginBottom: 4 }}>{c.question}</div>
                {c.context && <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", fontStyle: "italic", marginBottom: 4 }}>{c.context}</div>}
                <div style={{ display: "flex", gap: 4 }}>
                  <input
                    className="input"
                    style={{ flex: 1, fontSize: 12, padding: "4px 8px" }}
                    placeholder="Deine Antwort..."
                    value={localAnswer}
                    onChange={(e) => setInlineAnswers({ ...inlineAnswers, [c.id]: e.target.value })}
                  />
                  <button
                    className="btn"
                    style={{ fontSize: 11, padding: "2px 10px" }}
                    onClick={() => {
                      if ((localAnswer || "").trim()) {
                        answerMut.mutate({ id: c.id, text: localAnswer.trim() });
                      }
                    }}
                    disabled={!localAnswer.trim() || answerMut.isPending}
                  >
                    ✓
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// === 9-SCHRITTE-REVIEW-PIPELINE MODAL ===
function ReviewPipelineModal({ result, isRunning, onClose, onGoToBrainstorm }: { result: any | null; isRunning: boolean; onClose: () => void; onGoToBrainstorm: () => void }) {
  // Wenn isRunning, zeige Progress (9 Schritte, alle "running")
  // Wenn result, zeige Ergebnisse strukturiert
  const steps = isRunning
    ? Array.from({ length: 9 }, (_, i) => ({
        step_id: `step_${i+1}`,
        step_label: ["Ziel-MD Dokument erstellen", "Redundanzen suchen + beheben", "Offene Themen erkennen", "Rechtschreibprüfung", "Zeichensetzung", "Satzaufbau", "Formales Layout", "Inhaltliche Widersprüche", "Offene Fragen (User)"][i],
        step_icon: ["📄", "🗂️", "📋", "🔤", "⸮", "✍️", "📐", "⚠️", "❓"][i],
        status: i === 0 ? "running" : "pending",
        step_index: i + 1,
      }))
    : (result?.steps || []);
  const step9 = result?.steps?.find((s: any) => s.step_id === "step_9_questions");
  const openQuestions = step9?.open_questions || [];
  return (
    <div onClick={onClose} style={{
      position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
      background: "rgba(0,0,0,0.55)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
    }}>
      <div onClick={(e) => e.stopPropagation()} className="card" style={{
        maxWidth: 780, width: "100%", maxHeight: "88vh", overflow: "auto",
        padding: 20, display: "flex", flexDirection: "column", gap: 12,
      }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 18, display: "flex", alignItems: "center", gap: 8 }}>
              {isRunning ? "⏳ Review-Pipeline läuft..." : "✅ Review abgeschlossen"}
            </h2>
            <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", marginTop: 4 }}>
              {isRunning
                ? "9 Verarbeitungs-Schritte (jeder ein eigener KI-Abruf)"
                : `${result?.steps?.filter((s: any) => s.status === "done").length || 0} von 9 Schritten abgeschlossen`}
            </div>
          </div>
          <button className="btn" style={{ padding: "4px 10px" }} onClick={onClose}>✕</button>
        </div>

        {/* Schritt-Liste */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 400, overflow: "auto" }}>
          {steps.map((s: any) => {
            const statusColor = s.status === "done" ? "var(--color-hermes-accent)" : s.status === "running" ? "var(--color-hermes-accent-blue)" : s.status === "error" ? "var(--color-hermes-danger)" : "var(--color-hermes-text-secondary)";
            const statusIcon = s.status === "done" ? "✅" : s.status === "running" ? "⏳" : s.status === "error" ? "❌" : "⏸️";
            return (
              <details key={s.step_id} className="card" style={{ padding: 8, borderLeft: `3px solid ${statusColor}` }} open={s.status === "done" || s.status === "error"}>
                <summary style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: 8, fontSize: 13, fontWeight: 600 }}>
                  <span style={{ fontSize: 16 }}>{statusIcon}</span>
                  <span>{s.step_icon}</span>
                  <span>Schritt {s.step_index}: {s.step_label}</span>
                  {s.status === "running" && <span style={{ marginLeft: "auto", fontSize: 11, color: statusColor }}>läuft...</span>}
                </summary>
                {s.status === "done" && (
                  <div style={{ marginTop: 6, fontSize: 12 }}>
                    {s.summary && <div style={{ marginBottom: 6, color: "var(--color-hermes-text-secondary)" }}>{s.summary}</div>}
                    {/* Schritt-spezifische Details */}
                    {s.redundancies_found > 0 && s.issues && (
                      <div style={{ fontSize: 11 }}>
                        <strong>Redundanzen:</strong>
                        <ul style={{ margin: "4px 0 0 16px" }}>
                          {s.issues.map((iss: any, i: number) => (
                            <li key={i}>{iss.type}: {iss.items?.join(", ") || iss.fix}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {s.open_topics && s.open_topics.length > 0 && (
                      <div style={{ fontSize: 11, marginTop: 4 }}>
                        <strong>Offene Themen:</strong> {s.open_topics.join(", ")}
                      </div>
                    )}
                    {s.addressed_themes && s.addressed_themes.length > 0 && (
                      <div style={{ fontSize: 11, marginTop: 4, color: "var(--color-hermes-accent)" }}>
                        ✓ Adressiert: {s.addressed_themes.join(", ")}
                      </div>
                    )}
                    {s.typos_found > 0 && s.typos && (
                      <div style={{ fontSize: 11, marginTop: 4 }}>
                        <strong>Tippfehler:</strong>
                        <ul style={{ margin: "4px 0 0 16px" }}>
                          {s.typos.map((t: any, i: number) => <li key={i}>"{t.term}": {t.message}</li>)}
                        </ul>
                      </div>
                    )}
                    {s.issues && s.step_id === "step_5_punctuation" && (
                      <div style={{ fontSize: 11, marginTop: 4 }}>
                        {s.issues.map((iss: any, i: number) => (
                          <div key={i}>• {iss.type}: {iss.count || iss.fix}</div>
                        ))}
                      </div>
                    )}
                    {s.flesch !== undefined && (
                      <div style={{ fontSize: 11, marginTop: 4 }}>
                        <strong>Flesch Reading Ease:</strong> {s.flesch} {s.flesch < 30 && "⚠️ (niedrig)"}
                      </div>
                    )}
                    {s.headings_total !== undefined && (
                      <div style={{ fontSize: 11, marginTop: 4 }}>
                        <strong>Headings:</strong> {s.headings_total}
                        {s.issues && s.issues.length > 0 && (
                          <span style={{ color: "var(--color-hermes-accent-orange)" }}> · {s.issues.length} Layout-Issue(s)</span>
                        )}
                      </div>
                    )}
                    {s.contradictions_found > 0 && s.contradictions && (
                      <div style={{ fontSize: 11, marginTop: 4 }}>
                        <strong>Widersprüche:</strong>
                        <ul style={{ margin: "4px 0 0 16px" }}>
                          {s.contradictions.map((c: any, i: number) => (
                            <li key={i}>{c.message || `${c.type}: ${c.values?.join(" vs. ")}`}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
                {s.status === "error" && (
                  <div style={{ marginTop: 6, fontSize: 12, color: "var(--color-hermes-danger)" }}>Fehler: {s.error}</div>
                )}
              </details>
            );
          })}
        </div>

        {/* Schritt 9: Offene Fragen */}
        {!isRunning && openQuestions.length > 0 && (
          <div className="card" style={{ padding: 12, borderLeft: "3px solid var(--color-hermes-accent-orange)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>❓ {openQuestions.length} offene Frage(n) — User muss beantworten</div>
              <button className="btn btn-primary" style={{ fontSize: 11, padding: "2px 10px" }} onClick={onGoToBrainstorm}>
                Zur Brainstorming-Ansicht →
              </button>
            </div>
            <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
              Klicke "Zur Brainstorming-Ansicht" um die Fragen direkt im Chat-Layout zu beantworten.
            </div>
          </div>
        )}

        {!isRunning && openQuestions.length === 0 && (
          <div className="card" style={{ padding: 12, background: "rgba(46,160,67,0.1)", borderLeft: "3px solid var(--color-hermes-accent)" }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--color-hermes-accent)" }}>✅ Keine offenen Fragen — alle Klarungen beantwortet</div>
          </div>
        )}

        {/* Actions */}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          {isRunning ? (
            <button className="btn" onClick={onClose} disabled>Bitte warten...</button>
          ) : (
            <>
              <button className="btn" onClick={onClose}>Schließen</button>
              {openQuestions.length > 0 && (
                <button className="btn btn-primary" onClick={onGoToBrainstorm}>
                  → Offene Fragen beantworten
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// === CIO-REVIEW-MODAL ===
function CioReviewModal({ result, onClose, onProceed, isStarting }: { result: any; onClose: () => void; onProceed: () => void; isStarting: boolean }) {
  const issues = result.issues || [];
  const warnings = result.warnings || [];
  const stats = result.stats || {};
  const ready = result.ready;
  return (
    <div onClick={onClose} style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(0,0,0,0.55)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <div onClick={(e) => e.stopPropagation()} className="card" style={{ maxWidth: 700, width: "100%", maxHeight: "85vh", overflow: "auto", padding: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>🏗️ CIO-Review: Implementation-Freigabe</h2>
          <button className="btn" onClick={onClose}>✕</button>
        </div>
        <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", marginBottom: 12 }}>
          Der CIO prüft alle Tasks auf Vollständigkeit (Titel, Description, Assignee, Success-Criteria, Priorität, Status) und gibt sie dann für die Entwicklung frei.
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, marginBottom: 12 }}>
          {[
            { label: "Tasks total", value: stats.total || 0 },
            { label: "Child-Tasks", value: stats.children || 0 },
            { label: "Issues", value: issues.length, color: issues.length > 0 ? "var(--color-hermes-danger)" : "var(--color-hermes-accent)" },
            { label: "Warnings", value: warnings.length, color: warnings.length > 0 ? "var(--color-hermes-accent-orange)" : "var(--color-hermes-accent)" },
          ].map((s, i) => (
            <div key={i} className="card" style={{ padding: "8px 10px", textAlign: "center" }}>
              <div style={{ fontSize: 16, fontWeight: 600, color: s.color }}>{s.value}</div>
              <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>{s.label}</div>
            </div>
          ))}
        </div>
        <div className="card" style={{ padding: 10, marginBottom: 12, background: ready ? "rgba(46,160,67,0.1)" : "rgba(248,81,73,0.1)", borderLeft: `3px solid ${ready ? "var(--color-hermes-accent)" : "var(--color-hermes-danger)"}` }}>
          {ready ? (
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--color-hermes-accent)" }}>✅ CIO hat die Tasks freigegeben. Implementation kann starten.</div>
          ) : (
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--color-hermes-danger)" }}>❌ {issues.length} kritische Issue(s) — erst beheben.</div>
          )}
        </div>
        {issues.length > 0 && (
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4, color: "var(--color-hermes-danger)" }}>🔴 Kritische Issues</div>
            <div style={{ maxHeight: 200, overflow: "auto" }}>
              {issues.map((iss: any, i: number) => (
                <div key={i} className="card" style={{ padding: 6, fontSize: 11, marginBottom: 4, borderLeft: "3px solid var(--color-hermes-danger)" }}>
                  <strong>{iss.type}:</strong> {iss.message}
                </div>
              ))}
            </div>
          </div>
        )}
        {warnings.length > 0 && (
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4, color: "var(--color-hermes-accent-orange)" }}>🟧 Warnungen</div>
            <div style={{ maxHeight: 150, overflow: "auto" }}>
              {warnings.map((w: any, i: number) => (
                <div key={i} className="card" style={{ padding: 6, fontSize: 11, marginBottom: 4, borderLeft: "3px solid var(--color-hermes-accent-orange)" }}>
                  <strong>{w.type}:</strong> {w.message}
                </div>
              ))}
            </div>
          </div>
        )}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className="btn" onClick={onClose}>Abbrechen</button>
          <button className="btn btn-primary" onClick={onProceed} disabled={!ready || isStarting}>
            {isStarting ? "..." : ready ? "🚀 Implementation starten" : "Erst Issues beheben"}
          </button>
        </div>
      </div>
    </div>
  );
}

// === IMPLEMENTATION-PLAN-MODAL ===
function ImplementationPlanModal({ result, onClose, onMarkStepDone, isMarking }: { result: any; onClose: () => void; onMarkStepDone: (stepId: string) => void; isMarking: boolean }) {
  const plan = result.plan;
  const phases = plan?.phases || [];
  return (
    <div onClick={onClose} style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(0,0,0,0.55)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <div onClick={(e) => e.stopPropagation()} className="card" style={{ maxWidth: 900, width: "100%", maxHeight: "88vh", overflow: "auto", padding: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>🚀 Implementation-Plan</h2>
          <button className="btn" onClick={onClose}>✕</button>
        </div>
        <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", marginBottom: 12 }}>
          Gestartet: {new Date(result.started_at).toLocaleString()} · {phases.length} Phasen · {phases.reduce((s: number, p: any) => s + p.steps.length, 0)} Steps total
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {phases.map((phase: any, pi: number) => (
            <div key={phase.phase_id} className="card" style={{ padding: 12, borderLeft: `3px solid ${phase.type === "baseline" ? "var(--color-hermes-accent-blue)" : phase.type === "first_app" ? "var(--color-hermes-accent-orange)" : "var(--color-hermes-accent)"}` }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>{phase.name}</div>
                  <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>{phase.description}</div>
                </div>
                <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
                  {phase.steps.filter((s: any) => s.status === "done").length}/{phase.steps.length} done
                </div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 8 }}>
                {phase.steps.map((step: any) => {
                  const isDone = step.status === "done";
                  return (
                    <div key={step.id} className="card" style={{ padding: 6, fontSize: 11, background: isDone ? "rgba(46,160,67,0.05)" : "var(--color-hermes-surface-2)", opacity: isDone ? 0.7 : 1 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        {isDone ? <Check size={12} color="var(--color-hermes-accent)" /> : <div style={{ width: 12, height: 12, border: "1px solid var(--color-hermes-text-secondary)", borderRadius: 3 }} />}
                        <strong style={{ flex: 1 }}>{step.title}</strong>
                        {step.requirement_ref && <span className="badge badge-blue" style={{ fontSize: 9 }}>{step.requirement_ref}</span>}
                        <span style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)" }}>~{step.estimated_h}h</span>
                        {!isDone && (
                          <button className="btn" style={{ padding: "1px 8px", fontSize: 10 }} onClick={() => onMarkStepDone(step.id)} disabled={isMarking}>
                            ✓ Done
                          </button>
                        )}
                      </div>
                      {step.description && <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginTop: 2, marginLeft: 18 }}>{step.description.slice(0, 150)}{step.description.length > 150 ? "..." : ""}</div>}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
          <button className="btn" onClick={onClose}>Schließen</button>
        </div>
      </div>
    </div>
  );
}

// === SUB-TASK MODAL (PI-Worker teilt grosse Tasks) ===
function SubTaskModal({ parentTask, onClose, onSubmit, isLoading }: { parentTask: any; onClose: () => void; onSubmit: (subtasks: any[]) => void; isLoading: boolean }) {
  const [rows, setRows] = useState<any[]>([
    { title: "", description: "", assigned_role: "pi-coder", success_criteria: "" },
  ]);
  const addRow = () => setRows([...rows, { title: "", description: "", assigned_role: "pi-coder", success_criteria: "" }]);
  const removeRow = (i: number) => setRows(rows.filter((_, idx) => idx !== i));
  const updateRow = (i: number, field: string, value: any) => {
    setRows(rows.map((r, idx) => idx === i ? { ...r, [field]: value } : r));
  };
  const handleSubmit = () => {
    const valid = rows.filter((r) => r.title?.trim());
    if (valid.length === 0) {
      alert("Mindestens 1 Sub-Task mit Titel noetig.");
      return;
    }
    onSubmit(valid.map((r) => ({
      title: r.title,
      description: r.description,
      assigned_role: r.assigned_role,
      success_criteria: r.success_criteria ? r.success_criteria.split("\n").filter((s: string) => s.trim()) : [],
    })));
  };
  return (
    <div onClick={onClose} style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(0,0,0,0.55)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <div onClick={(e) => e.stopPropagation()} className="card" style={{ maxWidth: 700, width: "100%", maxHeight: "85vh", overflow: "auto", padding: 20 }}>
        <h2 style={{ margin: "0 0 12px", fontSize: 18 }}>➕ Sub-Tasks erstellen</h2>
        <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", marginBottom: 12 }}>
          <strong>Parent-Task:</strong> {parentTask?.title}
          <br />
          PI-Worker kann diese gro\u00dfe Task in kleinere Sub-Tasks aufteilen und an Sub-Agents (pi-tester, pi-reviewer, etc.) delegieren.
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 400, overflow: "auto" }}>
          {rows.map((r, i) => (
            <div key={i} className="card" style={{ padding: 10, background: "var(--color-hermes-surface-2)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 11, fontWeight: 600 }}>Sub-Task {i + 1}</span>
                {rows.length > 1 && (
                  <button className="btn" style={{ fontSize: 9, padding: "1px 6px" }} onClick={() => removeRow(i)}>✕</button>
                )}
              </div>
              <input className="input" style={{ fontSize: 12, padding: "4px 8px", marginBottom: 4 }} placeholder="Titel der Sub-Task" value={r.title} onChange={(e) => updateRow(i, "title", e.target.value)} />
              <textarea className="input" style={{ fontSize: 11, padding: "4px 8px", marginBottom: 4, minHeight: 40 }} placeholder="Beschreibung" value={r.description} onChange={(e) => updateRow(i, "description", e.target.value)} />
              <div style={{ display: "flex", gap: 6, marginBottom: 4 }}>
                <select className="input" style={{ fontSize: 11, padding: "2px 6px", flex: 1 }} value={r.assigned_role} onChange={(e) => updateRow(i, "assigned_role", e.target.value)}>
                  <option value="pi-coder">💻 pi-coder (Implementierung)</option>
                  <option value="pi-tester">🧪 pi-tester (Tests)</option>
                  <option value="pi-reviewer">👁 pi-reviewer (Code-Review)</option>
                  <option value="pi-fixer">🔧 pi-fixer (Bug-Fix)</option>
                  <option value="CIO">🏗️ CIO (Architektur)</option>
                  <option value="CEO-digital">👑 CEO-digital (Strategie)</option>
                </select>
              </div>
              <textarea className="input" style={{ fontSize: 10, padding: "4px 8px", minHeight: 30 }} placeholder="Success-Criteria (1 pro Zeile)" value={r.success_criteria} onChange={(e) => updateRow(i, "success_criteria", e.target.value)} />
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <button className="btn" onClick={addRow}>+ Weitere Sub-Task</button>
          <div style={{ flex: 1 }} />
          <button className="btn" onClick={onClose}>Abbrechen</button>
          <button className="btn btn-primary" onClick={handleSubmit} disabled={isLoading}>
            {isLoading ? "..." : `${rows.filter((r) => r.title?.trim()).length} Sub-Task(s) erstellen`}
          </button>
        </div>
      </div>
    </div>
  );
}

// === 2-STUFIGE REVIEW MODALS ===

function TwoStageClarifyModal({ completenessResult, answers, setAnswers, onClose, onSubmitAll }: any) {
  const clarifications = completenessResult.clarifications || [];
  const ceoProgress = completenessResult.ceo_progress || { answered: 0, total: 0 };
  const cioProgress = completenessResult.cio_progress || { open_topics: [], answered: 0 };
  return (
    <div onClick={onClose} style={{
      position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
      background: "rgba(0,0,0,0.55)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
    }}>
      <div onClick={(e) => e.stopPropagation()} className="card" style={{
        maxWidth: 720, width: "100%", maxHeight: "85vh", overflow: "auto",
        padding: 20, display: "flex", flexDirection: "column", gap: 14,
      }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>SCHRITT 1 VON 2</div>
            <h2 style={{ margin: 0, fontSize: 18, display: "flex", alignItems: "center", gap: 8 }}>
              📋 Vollständigkeitsprüfung
            </h2>
            <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", marginTop: 4 }}>
              OpenBrain: {completenessResult.openbrain_vorgaben_count} Vorgaben geladen · {clarifications.length} Klärungsfragen
            </div>
          </div>
          <button className="btn" style={{ padding: "4px 10px" }} onClick={onClose}>✕</button>
        </div>

        {/* Progress */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <div className="card" style={{ padding: 8 }}>
            <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>CEO-Geschäftsfragen</div>
            <div style={{ fontSize: 16, fontWeight: 600 }}>{ceoProgress.answered} / {ceoProgress.total}</div>
          </div>
          <div className="card" style={{ padding: 8 }}>
            <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>CIO-Entwicklungsthemen</div>
            <div style={{ fontSize: 16, fontWeight: 600 }}>{cioProgress.answered} / {cioProgress.open_topics.length + cioProgress.answered}</div>
          </div>
        </div>

        {/* Klärungsfragen */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10, maxHeight: 400, overflow: "auto" }}>
          {clarifications.length === 0 ? (
            <div className="card" style={{ textAlign: "center", padding: 20, color: "var(--color-hermes-accent)" }}>
              ✅ Alles vollständig! Klicke auf "Weiter zu Qualitätsprüfung".
            </div>
          ) : clarifications.map((c: any) => (
            <div key={c.id} className="card" style={{ padding: 12, borderLeft: `3px solid var(--color-hermes-accent-blue)` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                <span className="badge badge-blue">{c.phase}</span>
                <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>{c.category}</span>
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{c.question}</div>
              {c.context && <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginBottom: 6, fontStyle: "italic" }}>{c.context}</div>}
              {c.openbrain_refs && c.openbrain_refs.length > 0 && (
                <details style={{ marginBottom: 6 }}>
                  <summary style={{ fontSize: 10, color: "var(--color-hermes-accent-blue)", cursor: "pointer" }}>
                    📚 {c.openbrain_refs.length} OpenBrain-Vorgabe(n) anzeigen
                  </summary>
                  <div style={{ marginTop: 4, fontSize: 11 }}>
                    {c.openbrain_refs.map((r: any, i: number) => (
                      <div key={i} style={{ padding: 4, marginBottom: 4, background: "var(--color-hermes-muted)", borderRadius: 4 }}>
                        <span className="badge badge-blue" style={{ fontSize: 9 }}>{r.brain}</span> {r.content?.slice(0, 150)}...
                      </div>
                    ))}
                  </div>
                </details>
              )}
              <textarea
                className="input"
                placeholder="Deine Antwort..."
                value={answers[c.id] || ""}
                onChange={(e) => setAnswers({ ...answers, [c.id]: e.target.value })}
                style={{ minHeight: 50, fontFamily: "var(--font-mono)", fontSize: 12 }}
              />
            </div>
          ))}
        </div>

        {/* Action */}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className="btn" onClick={onClose}>Abbrechen</button>
          <button
            className="btn btn-primary"
            onClick={onSubmitAll}
            disabled={clarifications.length > 0 && !clarifications.every((c: any) => (answers[c.id] || "").trim())}
          >
            Weiter zu Qualitätsprüfung →
          </button>
        </div>
      </div>
    </div>
  );
}

function TwoStageQualityModal({ reviewResult, onClose, onProceed, onReReview, isReReviewing, canGenerate }: any) {
  const counts = reviewResult.issue_counts || { high: 0, medium: 0, low: 0 };
  const score = reviewResult.score;
  const colorMap: Record<string, string> = {
    ok: "var(--color-hermes-accent)", minor: "var(--color-hermes-accent-blue)",
    review: "var(--color-hermes-accent-orange)", block: "var(--color-hermes-danger)",
  };
  const labelMap: Record<string, string> = {
    ok: "✅ Alles OK", minor: "🟦 Kleinere Hinweise",
    review: "🟧 Manuelle Prüfung empfohlen", block: "🟥 Kritische Issues — bitte zuerst beheben",
  };
  const issues = reviewResult.issues || [];
  const autoResolvable = reviewResult.auto_resolvable || [];
  const needsClarification = reviewResult.needs_clarification || [];
  return (
    <div onClick={onClose} style={{
      position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
      background: "rgba(0,0,0,0.55)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
    }}>
      <div onClick={(e) => e.stopPropagation()} className="card" style={{
        maxWidth: 760, width: "100%", maxHeight: "85vh", overflow: "auto",
        padding: 20, display: "flex", flexDirection: "column", gap: 14,
      }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>SCHRITT 2 VON 2</div>
            <h2 style={{ margin: 0, fontSize: 18, display: "flex", alignItems: "center", gap: 8 }}>
              🧪 Qualitätsprüfung (NALABS + Widerspruchsprüfung)
            </h2>
            <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", marginTop: 4 }}>
              Tool-gestützt: NALABS Smell-Detector + Heuristik
            </div>
          </div>
          <button className="btn" style={{ padding: "4px 10px" }} onClick={onClose}>✕</button>
        </div>

        {/* Score */}
        <div style={{
          padding: "10px 14px", borderRadius: 6,
          background: colorMap[score] + "20", borderLeft: `4px solid ${colorMap[score]}`,
        }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: colorMap[score] }}>{labelMap[score]}</div>
          <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
            {counts.high} kritisch · {counts.medium} mittel · {counts.low} gering
          </div>
        </div>

        {/* Stats */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
          {[
            { label: "Zeichen", value: reviewResult.stats?.total_chars || 0 },
            { label: "Zeilen", value: reviewResult.stats?.total_lines || 0 },
            { label: "Vollständigkeit", value: `${reviewResult.stats?.completeness_pct || 0}%` },
            { label: "Flesch Ø", value: reviewResult.stats?.nalabs_avg_flesch ?? "—" },
          ].map((s, i) => (
            <div key={i} className="card" style={{ padding: "8px 10px", textAlign: "center" }}>
              <div style={{ fontSize: 16, fontWeight: 600 }}>{s.value}</div>
              <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>{s.label}</div>
            </div>
          ))}
        </div>

        {/* Findings */}
        {issues.length > 0 && (
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>📋 Findings ({issues.length})</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 200, overflow: "auto" }}>
              {issues.map((iss: any, i: number) => {
                const sevColor = iss.severity === "high" ? "var(--color-hermes-danger)" : iss.severity === "medium" ? "var(--color-hermes-accent-orange)" : "var(--color-hermes-accent-blue)";
                return (
                  <div key={i} className="card" style={{ padding: "6px 10px", borderLeft: `3px solid ${sevColor}` }}>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <div style={{ fontSize: 11, fontWeight: 600 }}>{iss.category.toUpperCase()} <span style={{ color: sevColor, fontSize: 10 }}>[{iss.severity}]</span></div>
                      <div style={{ fontSize: 9, color: "var(--color-hermes-text-secondary)" }}>{iss.location?.slice(0, 60)}</div>
                    </div>
                    <div style={{ fontSize: 11 }}>{iss.message}</div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Auto-Resolvable */}
        {autoResolvable.length > 0 && (
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: "var(--color-hermes-accent)" }}>🟢 Auto-behebbar ({autoResolvable.length})</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {autoResolvable.map((a: any, i: number) => (
                <div key={i} className="card" style={{ padding: 6, fontSize: 11 }}>
                  ✓ {a.suggestedFix}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Needs Clarification (Rückfragen) — mit Input-Feldern */}
        {needsClarification.length > 0 && (
          <ClarificationAnswerList
            clarifications={needsClarification}
            inlineSave={async (id: string, text: string) => {
              try {
                await api.answerQuality(activeProject!, id, text);
                // Antwort wurde als User-Input ins Brainstorming-Log eingefügt
                qc.invalidateQueries({ queryKey: ["kanban-brainstorm", activeProject] });
                qc.invalidateQueries({ queryKey: ["quality", activeProject] });
                // Lade Review-Daten neu, damit die Rueckfragen-Liste aktualisiert wird
                reviewMut.mutate(brainstormDoc);
              } catch (e: any) {
                alert(`Fehler: ${e.message || e}`);
              }
            }}
          />
        )}

        {/* Actions */}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className="btn" onClick={onClose}>Schließen</button>
          <button className="btn" onClick={onReReview} disabled={isReReviewing}>🔄 Re-Review</button>
          <button
            className="btn btn-primary"
            onClick={onProceed}
            disabled={score === "block" || !canGenerate}
            title={score === "block" ? "Erst kritische Issues beheben" : "Übernimmt das geprüfte MD in Requirements"}
          >
            ✅ Übernehmen & Generieren
          </button>
        </div>
      </div>
    </div>
  );
}
