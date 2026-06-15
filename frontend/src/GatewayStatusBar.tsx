import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { RefreshCw, Server, Cpu, Terminal, CheckCircle, XCircle, AlertTriangle, Settings } from "lucide-react";
import { api, getToken } from "./api";
import { useTTS, TTSControl } from "./TTSControl";

import { useTTSContext } from "./TTSContext";

// TTS Settings Modal
function TTSSettingsModal({ onClose }: { onClose: () => void }) {
  const tts = useTTSContext();

  return (
    <div style={{
      position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
      background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 2000,
    }} onClick={onClose}>
      <div className="card" style={{ width: 420, padding: 20, display: "flex", flexDirection: "column", gap: 14 }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ fontSize: 15, fontWeight: 600, margin: 0, display: "flex", alignItems: "center", gap: 6 }}>
            <Settings size={16} /> Einstellungen
          </h3>
          <button className="btn" style={{ padding: "2px 8px", fontSize: 12 }} onClick={onClose}>✕</button>
        </div>

        <div style={{ borderTop: "1px solid var(--color-hermes-border)", paddingTop: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>🔊 Sprachausgabe (TTS)</div>
          <TTSControl tts={tts} />
        </div>

        <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", lineHeight: 1.6 }}>
          <strong>Modus:</strong><br />
          🔇 Aus — Keine Sprachausgabe<br />
          👆 Klick — Text durch Klick vorlesen<br />
          🔄 Auto — Automatisch vorlesen (in Vorbereitung)
        </div>
      </div>
    </div>
  );
}

export default function GatewayStatusBar() {
  const [showSettings, setShowSettings] = useState(false);
  const { data: status, isLoading, refetch } = useQuery({
    queryKey: ["gateway-status"],
    queryFn: () => api.get("/gateway/status"),
    refetchInterval: 15000,
  });

  const restartMut = useMutation({
    mutationFn: () => api.post("/gateway/restart/ollama"),
    onSuccess: () => setTimeout(() => refetch(), 3000),
  });

  const services = [
    { name: "Dashboard", key: "dashboard", icon: <Server size={12} /> },
    { name: "Ollama", key: "ollama", icon: <Cpu size={12} /> },
    { name: "PI Agent", key: "pi", icon: <Terminal size={12} /> },
  ];

  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      gap: 12,
      padding: "4px 16px",
      background: "var(--color-hermes-surface)",
      borderBottom: "1px solid var(--color-hermes-border)",
      fontSize: 11,
      color: "var(--color-hermes-text-secondary)",
      minHeight: 28,
    }}>
      {/* === MiniMax M3 Aktiv-Badge (prominent, links) === */}
      <div
        title="Alle Sub-Agents laufen mit MiniMax M3 (Hybrid-Cloud)"
        style={{
          display: "flex", alignItems: "center", gap: 5,
          padding: "2px 8px",
          background: "linear-gradient(135deg, rgba(255,166,43,0.18) 0%, rgba(248,81,73,0.18) 100%)",
          border: "1px solid rgba(255,166,43,0.5)",
          borderRadius: 4,
          fontSize: 10, fontWeight: 700, color: "var(--color-hermes-accent-orange)",
          letterSpacing: 0.3,
          textTransform: "uppercase",
        }}
      >
        <span style={{
          display: "inline-block", width: 6, height: 6, borderRadius: "50%",
          background: "var(--color-hermes-accent-orange)",
          boxShadow: "0 0 6px rgba(255,166,43,0.7)",
          animation: "pulse-minimax 2s ease-in-out infinite",
        }} />
        <span>MiniMax M3</span>
        <span style={{ color: "var(--color-hermes-text-secondary)", fontWeight: 400, textTransform: "none", fontSize: 9 }}>
          · Sub-Agents aktiv
        </span>
      </div>
      {/* Status Dots */}
      {services.map((svc) => {
        const svcStatus = status?.[svc.key];
        const isRunning = svcStatus?.running;
        return (
          <div key={svc.key} style={{ display: "flex", alignItems: "center", gap: 4 }} title={isRunning ? `${svc.name}: running` : `${svc.name}: ${svcStatus?.error || "stopped"}`}>
            {isRunning
              ? <CheckCircle size={10} color="var(--color-hermes-accent)" style={{ flexShrink: 0 }} />
              : svcStatus?.error
                ? <AlertTriangle size={10} color="var(--color-hermes-danger)" style={{ flexShrink: 0 }} />
                : <XCircle size={10} color="var(--color-hermes-text-secondary)" style={{ flexShrink: 0 }} />
            }
            <span>{svc.name}</span>
          </div>
        );
      })}

      {/* Ollama Models Badge */}
      {status?.ollama?.running && (
        <span className="badge badge-green" style={{ fontSize: 9, padding: "1px 6px" }}>
          {status.ollama.model_count} models
        </span>
      )}
      {status?.ollama?.running && status.ollama.models?.length > 0 && (
        <span style={{ fontSize: 10, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {status.ollama.models.join(", ")}
        </span>
      )}

      {/* PI Version */}
      {status?.pi?.version && (
        <span style={{ color: "var(--color-hermes-accent-blue)", fontSize: 10 }}>
          v{status.pi.version}
        </span>
      )}

      <div style={{ flex: 1 }} />

      {/* Restart Ollama */}
      <button
        className="btn"
        style={{ padding: "2px 8px", fontSize: 10, display: "flex", alignItems: "center", gap: 4 }}
        onClick={() => restartMut.mutate()}
        disabled={restartMut.isPending}
        title="Restart Ollama"
      >
        <RefreshCw size={10} className={restartMut.isPending ? "spin" : ""} />
        Restart Ollama
      </button>

      {/* Refresh */}
      <button
        className="btn"
        style={{ padding: "2px 8px", fontSize: 10 }}
        onClick={() => refetch()}
        title="Refresh status"
      >
        <RefreshCw size={10} />
      </button>

      {/* Settings Gear */}
      <button
        className="btn"
        style={{ padding: "2px 6px", fontSize: 10 }}
        onClick={() => setShowSettings(true)}
        title="Einstellungen"
      >
        <Settings size={12} />
      </button>

      {/* Settings Modal */}
      {showSettings && <TTSSettingsModal onClose={() => setShowSettings(false)} />}
    </div>
  );
}
