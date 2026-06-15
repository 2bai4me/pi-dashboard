import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { api } from "../api";

export default function Extensions() {
  const { data: extensions, isLoading } = useQuery({
    queryKey: ["extensions"],
    queryFn: () => api.listExtensions(),
  });

  if (isLoading) return <div style={{ color: "var(--color-hermes-text-secondary)" }}>Loading...</div>;

  return (
    <div>
      <div className="page-header">
        <h1>Extensions</h1>
        <p>PI Agent extensions — lifecycle & status</p>
      </div>

      <div className="card-grid">
        {(extensions || []).map((ext: any) => (
          <div key={ext.name} className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{
                width: 8, height: 8, borderRadius: "50%",
                background: ext.installed ? "var(--color-hermes-accent)" : "var(--color-hermes-danger)",
              }} />
              <span style={{ fontWeight: 600, fontSize: 14 }}>{ext.name}</span>
            </div>

            <p style={{ fontSize: 13, color: "var(--color-hermes-text-secondary)", margin: 0 }}>
              {ext.description}
            </p>

            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <span className={`badge ${ext.installed ? "badge-green" : "badge-red"}`}>
                {ext.installed ? "✓ Installed" : "✗ Not installed"}
              </span>
              {ext.sub_agents && <span className="badge badge-blue">{ext.sub_agents.active_count} active</span>}
            </div>

            {/* Sub-Agent Model Info */}
            {ext.sub_agent_model && (
              <div style={{ fontSize: 12, color: "var(--color-hermes-accent)", padding: "6px 8px", background: "rgba(46,160,67,0.08)", borderRadius: 6 }}>
                <strong>Sub-Agent Model:</strong> {ext.sub_agent_model.provider}/{ext.sub_agent_model.model}
                <br />
                <span style={{ color: "var(--color-hermes-text-secondary)" }}>
                  ~${ext.sub_agent_model.estimated_savings_per_workflow_usd}/workflow saved
                </span>
              </div>
            )}

            {/* Swarm Sub-Agents */}
            {ext.sub_agents?.active?.length > 0 && (
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4, color: "var(--color-hermes-accent)" }}>
                  Active Sub-Agents
                </div>
                {ext.sub_agents.active.slice(0, 5).map((sa: any, i: number) => (
                  <div key={i} style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", paddingLeft: 12, borderLeft: "2px solid var(--color-hermes-muted)", marginBottom: 2 }}>
                    {sa.name} ({sa.created_at ? new Date(sa.created_at).toLocaleTimeString() : "?"})
                  </div>
                ))}
                {ext.sub_agents.active.length > 5 && (
                  <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
                    +{ext.sub_agents.active.length - 5} more
                  </div>
                )}
              </div>
            )}

            <Link
              to={`/extensions/${ext.name}`}
              className="btn"
              style={{ alignSelf: "flex-start", marginTop: 4, textDecoration: "none" }}
            >
              View Details <ArrowRight size={14} />
            </Link>
          </div>
        ))}
      </div>
    </div>
  );
}
