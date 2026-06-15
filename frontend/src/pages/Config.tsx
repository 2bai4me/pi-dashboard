import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

export default function Config() {
  const [tab, setTab] = useState<"settings" | "models" | "auth">("settings");
  const [editContent, setEditContent] = useState<string>("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.getSettings(),
  });

  const { data: models } = useQuery({
    queryKey: ["models-config"],
    queryFn: () => api.getModelsConfig(),
  });

  const { data: auth } = useQuery({
    queryKey: ["auth"],
    queryFn: () => api.getSettings(), // auth via /config/auth
  });

  // Initialize editor content
  useState(() => {
    switch (tab) {
      case "settings": setEditContent(JSON.stringify(settings?.data, null, 2) || "{}"); break;
      case "models": setEditContent(JSON.stringify(models?.data, null, 2) || "{}"); break;
      case "auth": setEditContent(JSON.stringify(auth?.data, null, 2) || "{}"); break;
    }
  });

  async function handleSave() {
    setSaving(true);
    setMsg("");
    try {
      let parsed = JSON.parse(editContent);
      switch (tab) {
        case "settings": await api.putSettings(parsed); break;
        case "models": await api.putModelsConfig(parsed); break;
      }
      setDirty(false);
      setMsg("Saved successfully");
    } catch (err: any) {
      setMsg(`Error: ${err.message}`);
    } finally {
      setSaving(false);
    }
  }

  const currentData = tab === "settings" ? settings : tab === "models" ? models : auth;

  return (
    <div>
      <div className="page-header">
        <h1>Config</h1>
        <p>Edit PI Agent configuration files</p>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 4, marginBottom: 16, borderBottom: "1px solid var(--color-hermes-border)", paddingBottom: 4 }}>
        {(["settings", "models", "auth"] as const).map((t) => (
          <button
            key={t}
            className="btn"
            style={{
              borderBottom: tab === t ? "2px solid var(--color-hermes-accent-blue)" : "2px solid transparent",
              borderRadius: 0,
              background: "transparent",
              borderTop: "none", borderLeft: "none", borderRight: "none",
            }}
            onClick={() => { setTab(t); setDirty(false); setMsg(""); }}
          >
            {t === "settings" ? "settings.json" : t === "models" ? "models.json" : "auth.json"}
          </button>
        ))}
      </div>

      {/* Info */}
      <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", marginBottom: 12 }}>
        {currentData?.path}
      </div>

      {/* Editor */}
      <textarea
        className="input"
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 12,
          minHeight: 400,
          resize: "vertical",
          whiteSpace: "pre",
          overflowWrap: "normal",
          overflow: "auto",
        }}
        value={editContent}
        onChange={(e) => { setEditContent(e.target.value); setDirty(true); }}
      />

      {/* Actions */}
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving || !dirty}>
          {saving ? "Saving..." : "Save"}
        </button>
        {msg && (
          <span style={{
            fontSize: 13,
            color: msg.startsWith("Error") ? "var(--color-hermes-danger)" : "var(--color-hermes-accent)",
          }}>
            {msg}
          </span>
        )}
      </div>
    </div>
  );
}
