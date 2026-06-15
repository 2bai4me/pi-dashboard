import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

function StatCard({ label, value, sublabel, color }: { label: string; value: string | number; sublabel?: string; color?: string }) {
  return (
    <div className="stat-card">
      <div className="label">{label}</div>
      <div className="value" style={color ? { color } : undefined}>{value}</div>
      {sublabel && <div className="sublabel">{sublabel}</div>}
    </div>
  );
}

export default function Status() {
  const { data: status, isLoading: loadingStatus, error: statusError } = useQuery({
    queryKey: ["status"],
    queryFn: () => api.getStatus(),
    refetchInterval: 10000,
  });

  const { data: system } = useQuery({
    queryKey: ["system"],
    queryFn: () => api.getSystemStats(),
    refetchInterval: 10000,
  });

  const { data: extList } = useQuery({
    queryKey: ["extensions-sum"],
    queryFn: () => api.getExtensions(),
  });

  const { data: projectsOverview } = useQuery({
    queryKey: ["status-projects"],
    queryFn: async () => {
      const projects = await api.get("/kanban/projects");
      const tasks = await api.get("/kanban/tasks");
      // Add task counts per status for each project
      return (projects || []).map((p: any) => {
        const ptasks = (tasks || []).filter((t: any) => t.project_id === p.id);
        const counts: Record<string, number> = {};
        ptasks.forEach((t: any) => {
          counts[t.status] = (counts[t.status] || 0) + 1;
        });
        return { ...p, task_counts: counts, total_tasks: ptasks.length };
      });
    },
  });

  if (loadingStatus) {
    return <div style={{ color: "var(--color-hermes-text-secondary)" }}>Loading...</div>;
  }

  if (statusError) {
    return (
      <div className="page-header">
        <h1>Status</h1>
        <p style={{ color: "var(--color-hermes-danger)" }}>
          Failed to load status. Is the backend running?
        </p>
      </div>
    );
  }

  const s = status as any;

  return (
    <div>
      <div className="page-header">
        <h1>Status</h1>
        <p>Pi Agent Dashboard — Overview</p>
      </div>

      {/* Top Stats */}
      <div className="card-grid" style={{ marginBottom: 24 }}>
        <StatCard label="Pi Version" value={s.pi_version || "?"} color="var(--color-hermes-accent-blue)" sublabel={s.pi_package} />
        <StatCard label="Default Model" value={s.model_strategy?.main_instance || s.default_model || "—"} sublabel={`Provider: ${s.default_provider || "—"}`} />
        <StatCard label="Sub-Agent Modell" value={s.model_strategy?.sub_agents || "ollama/gemma4:12b"} sublabel="Ollama lokal (0 Token-Kosten)" color="var(--color-hermes-accent)" />
        <StatCard label="Thinking Level" value={s.default_thinking_level || "off"} />
        <StatCard label="Sessions" value={s.session_count ?? "?"} sublabel={`${(s.installed_extensions || []).length} extensions`} />
        <StatCard label="Sub-Agent Ersparnis (7d)" value={`$${s.savings_7d?.estimated_savings_usd?.toFixed(4) || "0.0000"}`} sublabel={`${s.savings_7d?.ollama_calls || 0} Ollama-Calls (lokal, gratis)`} color="var(--color-hermes-accent)" />
      </div>

      {/* System */}
      {system && (
        <>
          <div className="page-header" style={{ marginTop: 32 }}>
            <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>System</h2>
          </div>
          <div className="card-grid">
            <StatCard label="OS" value={system.os} />
            <StatCard label="CPU" value={`${system.cpu_count} cores @ ${system.cpu_percent}%`} />
            <StatCard label="Memory" value={system.memory ? `${(system.memory.used / 1024 / 1024 / 1024).toFixed(1)} GB / ${(system.memory.total / 1024 / 1024 / 1024).toFixed(1)} GB` : "—"} sublabel={system.memory ? `${system.memory.percent}%` : undefined} />
            <StatCard label="Disk (agent dir)" value={system.disk ? `${(system.disk.used / 1024 / 1024 / 1024).toFixed(1)} GB / ${(system.disk.total / 1024 / 1024 / 1024).toFixed(1)} GB` : "—"} />
            <StatCard label="Python" value={system.python} />
          </div>
        </>
      )}

      {/* Model Strategy Banner */}
      <div className="card" style={{ marginTop: 24 }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 8px" }}>Token-Budget-Strategie</h3>
        <p style={{ fontSize: 13, color: "var(--color-hermes-text-secondary)", margin: 0 }}>
          {s.model_strategy?.policy}
        </p>
        <div style={{ marginTop: 12, display: "flex", gap: 12, flexWrap: "wrap" }}>
          <div className="badge badge-blue">
            Hauptinstanz: {s.model_strategy?.main_instance || s.default_model || "?"}
          </div>
          <div className="badge badge-green">
            Sub-Agenten: {s.model_strategy?.sub_agents}
          </div>
        </div>
      </div>

      {/* Projekte Übersicht */}
      {projectsOverview && projectsOverview.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 12px" }}>📋 Projekte ({projectsOverview.length})</h3>
          {projectsOverview.map((p: any) => (
            <div key={p.id} className="card" style={{ marginBottom: 8, padding: "10px 14px" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                <span style={{ fontWeight: 600, fontSize: 14 }}>{p.name}</span>
                <span className={`badge ${p.status === "active" ? "badge-green" : "badge-orange"}`} style={{ fontSize: 9 }}>{p.status}</span>
              </div>
              <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", marginBottom: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.description?.slice(0, 100)}</div>
              <div style={{ display: "flex", gap: 8, fontSize: 12 }}>
                <span className="badge badge-blue" style={{ fontSize: 9 }}>total: {p.total_tasks || 0}</span>
                {["triage", "todo", "in_progress", "review", "block", "done"].map((st) => {
                  const count = (p.task_counts || {})[st] || 0;
                  if (count === 0) return null;
                  return (
                    <span key={st} className={`badge ${
                      st === "done" ? "badge-green" : st === "triage" || st === "in_progress" ? "badge-orange" :
                      st === "block" ? "badge-red" : "badge-blue"
                    }`} style={{ fontSize: 9 }}>
                      {st}: {count}
                    </span>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
