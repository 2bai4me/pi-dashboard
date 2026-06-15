import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Lightbulb, TrendingUp, BookOpen, ExternalLink, CheckCircle, ArrowRight } from "lucide-react";
import { api } from "../api";

export default function SelfImprovement() {
  const [activeFramework, setActiveFramework] = useState<string | null>(null);
  const [activePhase, setActivePhase] = useState<number | null>(null);

  const { data: frameworks, isLoading } = useQuery({
    queryKey: ["selfimprovement"],
    queryFn: () => api.get("/selfimprovement/frameworks"),
  });

  const { data: strategy } = useQuery({
    queryKey: ["selfimprovement-strategy"],
    queryFn: () => api.get("/selfimprovement/strategy"),
  });

  if (isLoading) return <div style={{ color: "var(--color-hermes-text-secondary)" }}>Loading research data...</div>;

  return (
    <div>
      <div className="page-header">
        <h1 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Lightbulb size={20} color="var(--color-hermes-accent-orange)" />
          Self-Improvement
        </h1>
        <p>Research & strategy for making PI Agent smarter over time</p>
      </div>

      {/* Overview */}
      <div className="card" style={{ marginBottom: 24, borderLeft: "3px solid var(--color-hermes-accent)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <TrendingUp size={16} color="var(--color-hermes-accent)" />
          <span style={{ fontWeight: 600 }}>
            {strategy?.title || "Self-Improvement Strategy"}
          </span>
        </div>
        <p style={{ fontSize: 13, color: "var(--color-hermes-text-secondary)", margin: 0, lineHeight: 1.6 }}>
          Basierend auf Recherche von <strong>10+ aktiven Projekten</strong> (GenericAgent 12.8K ★, AutoAgent 9.3K ★, EvoAgentX 3K ★, Agent0 1.2K ★, AgentEvolver 1K ★, Huxley-Gödel Machine ICLR 2026, Lumos, Midas Agent, SII CLI, DGM) und <strong>9+ Papers</strong> (ExpeL, Agent0, EvoAgentX, DGM, HGM, GenericAgent, AutoAgent, Survey on Self-Evolving Agents).
        </p>
      </div>

      {/* Action Plan */}
      {strategy && (
        <div style={{ marginBottom: 24 }}>
          <div className="page-header" style={{ marginBottom: 12 }}>
            <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>Action Plan</h2>
            <p>Recommended phases for implementing self-improvement</p>
          </div>
          <div className="card-grid">
            {strategy.phases?.map((phase: any) => (
              <div
                key={phase.phase}
                className="card"
                style={{
                  cursor: "pointer",
                  borderLeft: `3px solid ${
                    phase.phase === 1 ? "var(--color-hermes-accent)" :
                    phase.phase === 2 ? "var(--color-hermes-accent-blue)" :
                    phase.phase === 3 ? "var(--color-hermes-accent-orange)" :
                    phase.phase === 4 ? "var(--color-hermes-danger)" :
                    "var(--color-hermes-text-secondary)"
                  }`,
                }}
                onClick={() => setActivePhase(activePhase === phase.phase ? null : phase.phase)}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <span className={`badge ${phase.phase === 1 ? "badge-green" : "badge-blue"}`}>
                    Phase {phase.phase}
                  </span>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{phase.name}</span>
                </div>
                <p style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", margin: "4px 0" }}>
                  {phase.description?.slice(0, 120)}...
                </p>
                <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
                  ⏱ {phase.effort} · 📈 {phase.impact}
                </div>

                {activePhase === phase.phase && (
                  <div style={{ marginTop: 8, padding: 8, background: "var(--color-hermes-muted)", borderRadius: 6 }}>
                    <div style={{ fontWeight: 500, fontSize: 12, marginBottom: 4 }}>Implementation</div>
                    <p style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", margin: 0 }}>
                      {phase.implementation}
                    </p>
                    {phase.packages && (
                      <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginTop: 4 }}>
                        <strong>Packages:</strong> {phase.packages}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
          {strategy.recommended_start && (
            <div className="card" style={{ marginTop: 12, borderLeft: "3px solid var(--color-hermes-accent)", background: "rgba(46,160,67,0.05)" }}>
              <CheckCircle size={14} color="var(--color-hermes-accent)" style={{ marginRight: 6 }} />
              <span style={{ fontSize: 13 }}>{strategy.recommended_start}</span>
            </div>
          )}
        </div>
      )}

      {/* Framework Research */}
      <div style={{ marginBottom: 24 }}>
        <div className="page-header" style={{ marginBottom: 12 }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>Framework Research</h2>
          <p>{frameworks?.length || 0} self-improving agent frameworks analyzed</p>
        </div>

        <div className="card-grid">
          {(frameworks || []).map((fw: any) => (
            <div
              key={fw.name}
              className="card"
              style={{
                cursor: "pointer",
                borderTop: `3px solid ${fw.applicable ? "var(--color-hermes-accent)" : "var(--color-hermes-text-secondary)"}`,
                opacity: fw.applicable ? 1 : 0.6,
              }}
              onClick={() => setActiveFramework(activeFramework === fw.name ? null : fw.name)}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                <span style={{ fontWeight: 600, fontSize: 14 }}>{fw.name}</span>
                <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                  <span className={`badge ${fw.applicable ? "badge-green" : "badge-orange"}`}>
                    {fw.applicable ? "✓ Applicable" : "Research"}
                  </span>
                  {fw.stars && <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>★{fw.stars}</span>}
                </div>
              </div>

              <p style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", margin: "4px 0", lineHeight: 1.4 }}>
                {fw.description}
              </p>

              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <a href={fw.url} target="_blank" rel="noopener noreferrer"
                  style={{ fontSize: 11, color: "var(--color-hermes-accent-blue)", display: "flex", alignItems: "center", gap: 4 }}
                  onClick={(e) => e.stopPropagation()}>
                  <ExternalLink size={10} /> GitHub
                </a>
                <ArrowRight size={10} color="var(--color-hermes-text-secondary)" />
              </div>

              {activeFramework === fw.name && (
                <div style={{ marginTop: 8, padding: 8, background: "var(--color-hermes-muted)", borderRadius: 6, fontSize: 11 }}>
                  <div style={{ marginBottom: 4 }}><strong>Approach:</strong> {fw.approach}</div>
                  <div style={{ marginBottom: 4 }}><strong>Key Insight:</strong> {fw.key_insight}</div>
                  <div style={{ padding: "4px 6px", borderRadius: 4, background: fw.applicable ? "rgba(46,160,67,0.1)" : "rgba(210,153,34,0.1)", marginTop: 4 }}>
                    <strong>Rationale:</strong> {fw.rationale}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Key Papers */}
      {strategy?.key_papers && (
        <div className="card">
          <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 8px", display: "flex", alignItems: "center", gap: 6 }}>
            <BookOpen size={14} /> Key Papers
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {strategy.key_papers.map((p: any, i: number) => (
              <a key={i} href={p.url} target="_blank" rel="noopener noreferrer"
                style={{ fontSize: 12, color: "var(--color-hermes-accent-blue)", display: "flex", alignItems: "center", gap: 6, padding: "4px 0" }}>
                <ExternalLink size={10} /> {p.title}
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
