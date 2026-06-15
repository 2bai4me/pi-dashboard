import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Key, Eye, EyeOff, Plus, Trash2, Edit3 } from "lucide-react";
import { api } from "../api";

export default function ApiKeys() {
  const qc = useQueryClient();
  const [showAll, setShowAll] = useState(false);
  const [editKey, setEditKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");

  const { data: vars, isLoading } = useQuery({
    queryKey: ["env-vars"],
    queryFn: () => api.get("/env/vars"),
    refetchInterval: 10000,
  });

  const setMut = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => api.put("/env/vars", { key, value }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["env-vars"] }); setEditKey(null); setEditValue(""); },
  });

  const delMut = useMutation({
    mutationFn: (key: string) => api.del(`/env/vars/${key}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["env-vars"] }),
  });

  const categories = ["LLM Provider", "Agent", "OpenBrain", "Ollama"];

  if (isLoading) return <div style={{ color: "var(--color-hermes-text-secondary)" }}>Loading...</div>;

  return (
    <div>
      <div className="page-header" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Key size={20} color="var(--color-hermes-accent-blue)" />
            API Keys & Environment
          </h1>
          <p>Manage API keys, tokens, and environment variables — stored in ~/.pi/agent/.env.override</p>
        </div>
        <button className="btn" onClick={() => setShowAll(!showAll)}>
          {showAll ? <EyeOff size={14} /> : <Eye size={14} />} {showAll ? "Hide Values" : "Show All"}
        </button>
      </div>

      {categories.map((cat) => {
        const items = (vars || []).filter((v: any) => v.category === cat);
        if (items.length === 0) return null;
        return (
          <div key={cat} style={{ marginBottom: 24 }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 8px", textTransform: "capitalize" }}>{cat}</h3>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Variable</th>
                  <th>Value</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((v: any) => (
                  <tr key={v.key}>
                    <td style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--color-hermes-accent-blue)" }}>
                      {v.key}
                    </td>
                    <td style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--color-hermes-text-secondary)" }}>
                      {editKey === v.key ? (
                        <div style={{ display: "flex", gap: 4 }}>
                          <input className="input" style={{ fontFamily: "var(--font-mono)", fontSize: 11, padding: "4px 8px" }}
                            type="text" value={editValue} onChange={(e) => setEditValue(e.target.value)} autoFocus />
                          <button className="btn" style={{ padding: "4px 8px", fontSize: 11 }}
                            onClick={() => setMut.mutate({ key: v.key, value: editValue })}>Save</button>
                          <button className="btn" style={{ padding: "4px 8px", fontSize: 11 }}
                            onClick={() => { setEditKey(null); setEditValue(""); }}>Cancel</button>
                        </div>
                      ) : (
                        v.masked_value || (v.set ? "*** (set)" : "—")
                      )}
                    </td>
                    <td>
                      {v.set ? <span className="badge badge-green">✓ Set</span> : <span className="badge badge-orange">✗ Not set</span>}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 4 }}>
                        <button className="btn" style={{ padding: "4px 8px" }}
                          onClick={() => { setEditKey(v.key); setEditValue(""); }} title="Edit">
                          <Edit3 size={12} />
                        </button>
                        <button className="btn" style={{ padding: "4px 8px" }}
                          onClick={() => delMut.mutate(v.key)} title="Clear">
                          <Trash2 size={12} color="var(--color-hermes-danger)" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
  );
}
