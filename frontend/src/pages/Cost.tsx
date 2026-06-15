import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { api } from "../api";

export default function Cost() {
  const [days, setDays] = useState(7);

  const { data: summary, isLoading } = useQuery({
    queryKey: ["cost", days],
    queryFn: () => api.costSummary(days),
  });

  const { data: bySession } = useQuery({
    queryKey: ["cost-by-session"],
    queryFn: () => api.costBySession(10),
  });

  if (isLoading) return <div style={{ color: "var(--color-hermes-text-secondary)" }}>Loading...</div>;

  const s = summary as any;

  return (
    <div>
      <div className="page-header" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h1>Cost & Usage</h1>
          <p>Token usage, costs, and savings tracking</p>
        </div>
        <select className="input" style={{ width: "auto" }} value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>

      {/* Summary Cards */}
      <div className="card-grid" style={{ marginBottom: 24 }}>
        <div className="stat-card">
          <div className="label">Total Calls</div>
          <div className="value">{s.total?.calls || 0}</div>
        </div>
        <div className="stat-card">
          <div className="label">Input Tokens</div>
          <div className="value">{(s.total?.input_tokens / 1000).toFixed(1)}k</div>
          <div className="sublabel">{s.total?.input_tokens.toLocaleString()} total</div>
        </div>
        <div className="stat-card">
          <div className="label">Output Tokens</div>
          <div className="value">{(s.total?.output_tokens / 1000).toFixed(1)}k</div>
        </div>
        <div className="stat-card">
          <div className="label">Estimated Cost</div>
          <div className="value" style={{ color: "var(--color-hermes-danger)" }}>${s.total?.cost?.toFixed(4) || "0.00"}</div>
        </div>
        <div className="stat-card" style={{ borderColor: "var(--color-hermes-accent)" }}>
          <div className="label">🪙 Savings (Ollama lokal)</div>
          <div className="value" style={{ color: "var(--color-hermes-accent)" }}>${s.savings?.estimated_savings_usd?.toFixed(4) || "0.0000"}</div>
          <div className="sublabel">{s.savings?.ollama_calls || 0} Ollama calls (gratis)</div>
        </div>
      </div>

      {/* Savings Strategy Banner */}
      <div className="card" style={{ marginBottom: 24, borderLeft: "3px solid var(--color-hermes-accent)" }}>
        <div style={{ fontSize: 13, color: "var(--color-hermes-text-secondary)" }}>
          {s.savings?.strategy}
        </div>
      </div>

      {/* By Provider */}
      {s.by_provider && Object.keys(s.by_provider).length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 8px" }}>By Provider</h3>
          <table className="data-table">
            <thead>
              <tr>
                <th>Provider</th>
                <th>Calls</th>
                <th>Input Tokens</th>
                <th>Output Tokens</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(s.by_provider).map(([provider, d]: [string, any]) => (
                <tr key={provider}>
                  <td style={{ fontWeight: 600 }}>{provider}</td>
                  <td>{d.calls}</td>
                  <td>{d.input_tokens.toLocaleString()}</td>
                  <td>{d.output_tokens.toLocaleString()}</td>
                  <td>${d.cost.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Daily Chart */}
      {s.by_day && Object.keys(s.by_day).length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 12px" }}>Daily Token Usage</h3>
          <div style={{ height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={Object.entries(s.by_day).map(([day, d]: [string, any]) => ({ day, input: d.input_tokens, output: d.output_tokens }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
                <XAxis dataKey="day" tick={{ fill: "#8b949e", fontSize: 11 }} />
                <YAxis tick={{ fill: "#8b949e", fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="input" fill="#58a6ff" name="Input" stackId="a" />
                <Bar dataKey="output" fill="#2ea043" name="Output" stackId="a" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* By Session */}
      {bySession?.length > 0 && (
        <div>
          <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 8px" }}>Top Sessions by Cost</h3>
          <table className="data-table">
            <thead>
              <tr>
                <th>Session</th>
                <th>Model</th>
                <th>Calls</th>
                <th>Input</th>
                <th>Output</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {bySession.slice(0, 10).map((s: any) => (
                <tr key={s.id}>
                  <td style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{s.id.slice(0, 16)}…</td>
                  <td>{s.model?.split("/").pop() || "—"}</td>
                  <td>{s.calls}</td>
                  <td>{s.input_tokens.toLocaleString()}</td>
                  <td>{s.output_tokens.toLocaleString()}</td>
                  <td style={{ color: "var(--color-hermes-danger)" }}>${s.cost.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
