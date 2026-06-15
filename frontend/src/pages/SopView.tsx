import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Play, Pause, CheckCircle, XCircle, AlertTriangle, Plus, ArrowRight, Clock, Users, Wrench, Activity, TrendingUp, Award, Zap } from "lucide-react";
import { api } from "../api";

const STATUS_COLORS: Record<string, string> = {
  planned: "var(--color-hermes-text-secondary)",
  approved: "var(--color-hermes-accent-blue)",
  running: "var(--color-hermes-accent-orange)",
  paused: "var(--color-hermes-accent-orange)",
  completed: "var(--color-hermes-accent)",
  failed: "var(--color-hermes-danger)",
};

const ROLE_EMOJI: Record<string, string> = {
  "CEO-digital": "👑", CIO: "🏗️", CMO: "📢", CFO: "💰",
  "pi-coder": "💻", "pi-tester": "🧪", "pi-reviewer": "👁️", "pi-fixer": "🔧",
};

export default function SopView() {
  const qc = useQueryClient();
  const [activeSop, setActiveSop] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [autoPlay, setAutoPlay] = useState(false);

  const { data: sops, isLoading } = useQuery({
    queryKey: ["sops"],
    queryFn: () => api.get("/sop/list"),
    refetchInterval: 3000,
  });

  const { data: stats } = useQuery({
    queryKey: ["sop-stats"],
    queryFn: () => api.get("/sop/stats/summary"),
  });

  const { data: activeDetail, refetch: refetchDetail } = useQuery({
    queryKey: ["sop-detail", activeSop],
    queryFn: () => api.get(`/sop/${activeSop}`),
    enabled: !!activeSop,
    refetchInterval: activeSop ? 2000 : false,
  });

  const createMut = useMutation({
    mutationFn: (data: any) => api.post("/sop/create", data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["sops"] }); setShowCreate(false); setName(""); setDescription(""); },
  });

  const approveMut = useMutation({
    mutationFn: (id: string) => api.post(`/sop/${id}/approve`),
    onSuccess: () => refetchDetail(),
  });

  const startMut = useMutation({
    mutationFn: (id: string) => api.post(`/sop/${id}/start`),
    onSuccess: () => refetchDetail(),
  });

  const pauseMut = useMutation({
    mutationFn: (id: string) => api.post(`/sop/${id}/pause`),
    onSuccess: () => refetchDetail(),
  });

  const completeMut = useMutation({
    mutationFn: ({ sopId, stepId }: { sopId: string; stepId: string }) =>
      api.post(`/sop/${sopId}/step/${stepId}/complete`, { output: "Completed by agent", evidence: ["auto"] }),
    onSuccess: () => refetchDetail(),
  });

  const sop = activeDetail;

  useEffect(() => {
    if (autoPlay && sop?.status === "running") {
      const currentStep = sop.steps?.find((s: any) => s.status === "running");
      if (currentStep) {
        const timer = setTimeout(() => {
          completeMut.mutate({ sopId: sop.id, stepId: currentStep.id });
        }, 3000);
        return () => clearTimeout(timer);
      }
    }
  }, [autoPlay, sop?.status, sop?.steps]);

  if (isLoading) return <div style={{ color: "var(--color-hermes-text-secondary)" }}>Loading...</div>;

  return (
    <div>
      <div className="page-header" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Activity size={20} color="var(--color-hermes-accent-blue)" />
            SOP Prozesse
          </h1>
          <p>Standard Operating Procedures — definiert von CEO-digital, ausgeführt von Sub-Agenten</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: "var(--color-hermes-text-secondary)", cursor: "pointer" }}>
            <input type="checkbox" checked={autoPlay} onChange={() => setAutoPlay(!autoPlay)} />
            Auto-Play
          </label>
          <button className="btn btn-primary" onClick={() => setShowCreate(!showCreate)}>
            <Plus size={14} /> {showCreate ? "Cancel" : "New SOP"}
          </button>
        </div>
      </div>

      {/* Create Form */}
      {showCreate && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <input className="input" placeholder="Process name (e.g. 'Deploy Microservice')" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
            <textarea className="input" style={{ minHeight: 60 }} placeholder="Describe the process goal in natural language for CEO-digital..." value={description} onChange={(e) => setDescription(e.target.value)} />
            <button className="btn btn-primary" onClick={() => createMut.mutate({ name, description })} disabled={!name || !description}>
              ✨ CEO-digital elaborates
            </button>
          </div>
        </div>
      )}

      {/* Stats */}
      {stats && (
        <div className="card-grid" style={{ marginBottom: 16 }}>
          <div className="stat-card" style={{ padding: "8px 12px", flexDirection: "row", gap: 8, alignItems: "center" }}>
            <Activity size={14} color="var(--color-hermes-accent-blue)" />
            <span className="label">Total</span>
            <span style={{ fontWeight: 600 }}>{stats.total}</span>
          </div>
          {Object.entries(stats.by_status || {}).map(([s, c]: [string, any]) => (
            <div key={s} className="stat-card" style={{ padding: "8px 12px", flexDirection: "row", gap: 8, alignItems: "center" }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: STATUS_COLORS[s] }} />
            <span className="label">{s}</span>
            <span style={{ fontWeight: 600 }}>{c}</span>
          </div>
          ))}
          <div className="stat-card" style={{ padding: "8px 12px", flexDirection: "row", gap: 8, alignItems: "center" }}>
            <Clock size={14} />
            <span className="label">⌀ Duration</span>
            <span style={{ fontWeight: 600 }}>{stats.avg_duration_min}min</span>
          </div>
          <div className="stat-card" style={{ padding: "8px 12px", flexDirection: "row", gap: 8, alignItems: "center" }}>
            <TrendingUp size={14} color="var(--color-hermes-accent)" />
            <span className="label">Improvements</span>
            <span style={{ fontWeight: 600 }}>{stats.total_improvements}</span>
          </div>
        </div>
      )}

      {/* SOP List + Detail */}
      <div style={{ display: "flex", gap: 16 }}>
        {/* List */}
        <div style={{ width: activeSop ? 300 : "100%", minWidth: activeSop ? 300 : "auto" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {(sops || []).map((s: any) => (
              <div
                key={s.id}
                className="card"
                style={{ cursor: "pointer", padding: "10px 14px", borderLeft: `3px solid ${STATUS_COLORS[s.status] || "#333"}`, background: activeSop === s.id ? "var(--color-hermes-surface-2)" : "" }}
                onClick={() => setActiveSop(s.id === activeSop ? null : s.id)}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{s.name}</span>
                  <span className={`badge ${s.status === "running" ? "badge-green" : s.status === "failed" ? "badge-red" : "badge-orange"}`} style={{ fontSize: 10 }}>
                    {s.status}
                  </span>
                </div>
                <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", marginTop: 2 }}>{s.description?.slice(0, 80)}</div>
                <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginTop: 2 }}>
                  {s.steps?.length || 0} steps · v{s.version} · by {s.created_by}
                </div>
                {/* Mini Progress Bar */}
                {s.steps && (
                  <div style={{ marginTop: 6, height: 4, background: "var(--color-hermes-muted)", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${s.steps.filter((st: any) => st.status === "completed").length / s.steps.length * 100}%`, background: "var(--color-hermes-accent)", borderRadius: 2, transition: "width 0.3s" }} />
                  </div>
                )}
              </div>
            ))}
            {(!sops || sops.length === 0) && <div style={{ color: "var(--color-hermes-text-secondary)", textAlign: "center", padding: 20 }}>No SOPs created yet</div>}
          </div>
        </div>

        {/* Detail */}
        {activeSop && sop && (
          <div style={{ flex: 1, minWidth: 0 }}>
            {/* Header */}
            <div className="card" style={{ marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                  <h2 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>{sop.name}</h2>
                  <p style={{ fontSize: 13, color: "var(--color-hermes-text-secondary)", margin: "4px 0 0" }}>{sop.description}</p>
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  {sop.status === "planned" && <button className="btn btn-primary" onClick={() => approveMut.mutate(sop.id)}><Award size={14} /> Approve</button>}
                  {(sop.status === "approved" || sop.status === "paused") && <button className="btn" onClick={() => startMut.mutate(sop.id)}><Play size={14} /> Start</button>}
                  {sop.status === "running" && <button className="btn btn-danger" onClick={() => pauseMut.mutate(sop.id)}><Pause size={14} /> Pause</button>}
                </div>
              </div>
              <div style={{ display: "flex", gap: 12, marginTop: 8, fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
                <span>Version {sop.version}</span>
                <span>·</span>
                <span>by {sop.created_by}</span>
                <span>·</span>
                <span>{sop.steps?.length || 0} steps</span>
                {sop.quality_score && <span>· Quality: {sop.quality_score.toFixed(0)}%</span>}
              </div>
            </div>

            {/* Animated Process Flow */}
            <div className="card" style={{ marginBottom: 16, overflow: "hidden" }}>
              <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 12px" }}>Process Flow</h3>
              <div style={{ display: "flex", alignItems: "center", gap: 4, overflow: "auto", padding: "8px 0" }}>
                {(sop.steps || []).map((step: any, i: number) => (
                  <div key={step.id} style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
                    <div
                      className="card"
                      style={{
                        padding: "8px 12px",
                        textAlign: "center",
                        minWidth: 100,
                        borderTop: `3px solid ${
                          step.status === "completed" ? "var(--color-hermes-accent)" :
                          step.status === "running" ? "var(--color-hermes-accent-orange)" :
                          step.status === "failed" ? "var(--color-hermes-danger)" :
                          "var(--color-hermes-border)"
                        }`,
                        animation: step.status === "running" && autoPlay ? "pulse 1s ease-in-out infinite" : "none",
                        position: "relative",
                      }}
                    >
                      <div style={{ fontSize: 18 }}>{ROLE_EMOJI[step.role] || "🤖"}</div>
                      <div style={{ fontSize: 11, fontWeight: 600, marginTop: 2 }}>{step.name}</div>
                      <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>{step.role}</div>
                      {step.tool && <div style={{ fontSize: 9, color: "var(--color-hermes-accent-blue)", marginTop: 1 }}>🔧 {step.tool}</div>}
                      {/* Status Icon */}
                      <div style={{ position: "absolute", top: -6, right: -6 }}>
                        {step.status === "completed" ? <CheckCircle size={14} color="var(--color-hermes-accent)" /> :
                         step.status === "running" ? <Zap size={14} color="var(--color-hermes-accent-orange)" /> :
                         step.status === "failed" ? <XCircle size={14} color="var(--color-hermes-danger)" /> : null}
                      </div>
                      {/* Progress indicator for running step */}
                      {step.status === "running" && (
                        <div style={{ marginTop: 4, height: 2, background: "var(--color-hermes-muted)", borderRadius: 1, overflow: "hidden" }}>
                          <div className="progress-animate" style={{ height: "100%", width: "60%", background: "var(--color-hermes-accent-orange)", borderRadius: 1 }} />
                        </div>
                      )}
                    </div>
                    {i < sop.steps.length - 1 && <ArrowRight size={14} color="var(--color-hermes-text-secondary)" />}
                  </div>
                ))}
              </div>
            </div>

            {/* Step Detail Table */}
            <div className="card">
              <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 8px" }}>Step Details</h3>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Step</th>
                    <th>Role</th>
                    <th>Tool</th>
                    <th>Status</th>
                    <th>Duration</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(sop.steps || []).map((step: any, i: number) => (
                    <tr key={step.id} style={{ background: step.status === "running" ? "rgba(210,153,34,0.05)" : "" }}>
                      <td style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>#{i + 1}</td>
                      <td style={{ fontWeight: 500 }}>
                        {step.name}
                        {step.approval_required && <span className="badge badge-orange" style={{ marginLeft: 6, fontSize: 9 }}>APPROVAL</span>}
                      </td>
                      <td><span style={{ fontSize: 12 }}>{ROLE_EMOJI[step.role] || "🤖"} {step.role}</span></td>
                      <td><span className="badge badge-blue" style={{ fontSize: 10 }}>{step.tool}</span></td>
                      <td>
                        <span className={`badge ${
                          step.status === "completed" ? "badge-green" :
                          step.status === "running" ? "badge-orange" :
                          step.status === "failed" ? "badge-red" :
                          step.status === "planned" ? "badge-blue" :
                          "badge-orange"
                        }`}>{step.status}</span>
                      </td>
                      <td style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
                        {step.started_at && step.completed_at
                          ? `${((new Date(step.completed_at).getTime() - new Date(step.started_at).getTime()) / 60000).toFixed(1)}min`
                          : step.started_at ? "running..." : "—"}
                      </td>
                      <td>
                        {step.status === "running" && (
                          <button className="btn" style={{ padding: "2px 8px", fontSize: 10 }} onClick={() => completeMut.mutate({ sopId: sop.id, stepId: step.id })}>
                            <CheckCircle size={10} /> Complete
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Monitor Panel */}
            {sop.monitor?.improvements?.length > 0 && (
              <div className="card" style={{ marginTop: 16, borderLeft: "3px solid var(--color-hermes-accent)" }}>
                <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 8px", display: "flex", alignItems: "center", gap: 6 }}>
                  <TrendingUp size={14} color="var(--color-hermes-accent)" /> Process Monitor — Improvements
                </h3>
                <ul style={{ margin: 0, padding: "0 0 0 16px", fontSize: 12, color: "var(--color-hermes-text-secondary)", lineHeight: 1.8 }}>
                  {sop.monitor.improvements.map((imp: string, i: number) => <li key={i}>{imp}</li>)}
                </ul>
              </div>
            )}

            {/* Step Times */}
            {sop.monitor?.step_times?.length > 0 && (
              <div className="card" style={{ marginTop: 16 }}>
                <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 8px" }}>⏱ Step Execution Times</h3>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {sop.monitor.step_times.map((t: any, i: number) => (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                      <span style={{ minWidth: 120 }}>{t.step}</span>
                      <div style={{ flex: 1, height: 8, background: "var(--color-hermes-muted)", borderRadius: 4, overflow: "hidden" }}>
                        <div style={{ height: "100%", width: `${Math.min(t.duration_min / 10 * 100, 100)}%`, background: t.duration_min > 5 ? "var(--color-hermes-danger)" : "var(--color-hermes-accent)", borderRadius: 4 }} />
                      </div>
                      <span style={{ color: "var(--color-hermes-text-secondary)", minWidth: 50, textAlign: "right" }}>{t.duration_min}min</span>
                      <span style={{ fontSize: 10, color: "var(--color-hermes-accent-blue)" }}>🔧 {t.tools}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
