import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { HardDrive, Cpu, Activity, Clock, Box, Server, Database, BarChart3 } from "lucide-react";
import { api } from "../api";

function StatCard({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub?: string }) {
  return (
    <div className="stat-card">
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
        {icon}
        <div className="label">{label}</div>
      </div>
      <div className="value" style={{ fontSize: 18 }}>{value}</div>
      {sub && <div className="sublabel">{sub}</div>}
    </div>
  );
}

export default function SysInfo() {
  const { data: status, isLoading } = useQuery({
    queryKey: ["status-full"],
    queryFn: () => api.get("/overview/status"),
    refetchInterval: 15000,
  });

  if (isLoading) return <div style={{ color: "var(--color-hermes-text-secondary)" }}>Loading...</div>;

  const sys = status?.system || {};
  const mem = sys.memory || {};
  const disk = sys.disk || {};

  function fmt(bytes: number) {
    if (!bytes) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let i = 0;
    let v = bytes;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return `${v.toFixed(1)} ${units[i]}`;
  }

  const uptime = sys.uptime_s ? (() => {
    const d = Math.floor(sys.uptime_s / 86400);
    const h = Math.floor((sys.uptime_s % 86400) / 3600);
    const m = Math.floor((sys.uptime_s % 3600) / 60);
    return `${d}d ${h}h ${m}m`;
  })() : "—";

  const ollamaModels = sys.ollama_models || [];

  return (
    <div>
      <div className="page-header">
        <h1 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Server size={20} color="var(--color-hermes-accent-blue)" />
          System
        </h1>
        <p>PI Agent host system information</p>
      </div>

      {/* System Stats */}
      <div className="card-grid" style={{ marginBottom: 24 }}>
        <StatCard icon={<Server size={14} color="var(--color-hermes-accent-blue)" />} label="OS" value={sys.os || "—"} sub={`Python ${sys.python}`} />
        <StatCard icon={<Activity size={14} color="var(--color-hermes-accent)" />} label="Uptime" value={uptime} sub={`PI v${status?.pi_version || "?"}`} />
        <StatCard icon={<Cpu size={14} color="var(--color-hermes-accent-orange)" />} label="CPU" value={`${sys.cpu_count} cores`} sub={`${sys.cpu_percent || 0}% utilization`} />
        <StatCard icon={<BarChart3 size={14} color="var(--color-hermes-accent)" />} label="Memory" value={mem.total ? fmt(mem.used) : "—"} sub={mem.total ? `${((mem.used / mem.total) * 100).toFixed(0)}% of ${fmt(mem.total)}` : ""} />
        <StatCard icon={<HardDrive size={14} color="var(--color-hermes-danger)" />} label="Disk" value={fmt(disk.used)} sub={disk.total ? `${disk.percent?.toFixed(0) || "?"}% of ${fmt(disk.total)}` : ""} />
        <StatCard icon={<Box size={14} color="var(--color-hermes-accent-blue)" />} label="Agent Dir" value={fmt(sys.pi_agent_dir_size || 0)} sub={`${status?.agent_dir || "—"}`} />
      </div>

      {/* Agent Config */}
      <div className="page-header" style={{ marginTop: 24 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>Agent Configuration</h2>
      </div>
      <div className="card-grid" style={{ marginBottom: 24 }}>
        <StatCard icon={<Cpu size={14} />} label="Default Model" value={status?.default_model || "—"} sub={status?.default_provider || ""} />
        <StatCard icon={<Box size={14} />} label="Enabled Models" value={`${status?.enabled_models?.length || 0}`} sub={(status?.enabled_models || []).join(", ")} />
        <StatCard icon={<Activity size={14} />} label="Thinking Level" value={status?.default_thinking_level || "off"} />
        <StatCard icon={<Box size={14} />} label="Sessions" value={`${status?.session_count || 0}`} sub={`${status?.installed_extensions?.length || 0} extensions`} />
      </div>

      {/* Savings */}
      {status?.savings_7d && (
        <div className="card" style={{ marginBottom: 24, borderLeft: "3px solid var(--color-hermes-accent)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <Database size={14} color="var(--color-hermes-accent)" />
            <span style={{ fontWeight: 600 }}>Token Savings (7 days)</span>
          </div>
          <div style={{ display: "flex", gap: 16, fontSize: 13 }}>
            <span>🆓 {status.savings_7d.ollama_calls} Ollama calls</span>
            <span>💰 {status.savings_7d.minimax_calls} MiniMax calls</span>
            <span style={{ color: "var(--color-hermes-accent)" }}>
              ~${status.savings_7d.estimated_savings_usd?.toFixed(4)} saved
            </span>
          </div>
          <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", marginTop: 4 }}>
            {status?.model_strategy?.policy}
          </div>
        </div>
      )}

      {/* Ollama Models */}
      {ollamaModels.length > 0 && (
        <div className="card">
          <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 8px", display: "flex", alignItems: "center", gap: 6 }}>
            <Database size={14} /> Ollama Models ({ollamaModels.length})
          </h3>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {ollamaModels.map((m: string) => (
              <span key={m} className="badge badge-green">{m}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
