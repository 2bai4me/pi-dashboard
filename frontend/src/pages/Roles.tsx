import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileText, Check, X, Send } from "lucide-react";
import { api, getToken } from "../api";

const ROLE_ICONS: Record<string, string> = {
  "pi-coder": "💻", "pi-tester": "🧪", "pi-reviewer": "👁️", "pi-fixer": "🔧",
  "CEO-digital": "👑", "CIO": "🏗️", "CMO": "📢", "CFO": "💰",
};

export default function Roles() {
  const [selectedRole, setSelectedRole] = useState<any>(null);
  const [chatInput, setChatInput] = useState("");
  const [chatLog, setChatLog] = useState<{role: string; text: string}[]>([]);
  const [improvedPrompt, setImprovedPrompt] = useState<string | null>(null);

  const { data: roles, isLoading: l1 } = useQuery({ queryKey: ["roles"], queryFn: () => api.get("/roles") });
  const { data: files } = useQuery({ queryKey: ["role-files"], queryFn: () => api.get("/roles/files") });
  const { data: orgRoles, isLoading: l2 } = useQuery({ queryKey: ["org-roles"], queryFn: () => api.get("/roles/org") });

  async function handleImprove() {
    if (!chatInput.trim() || !selectedRole) return;
    const userMsg = chatInput.trim();
    setChatLog((prev) => [...prev, { role: "user", text: userMsg }]);
    setChatInput("");
    const prompt = selectedRole.systemPrompt || "";
    const improvement = await generateImprovedPrompt(prompt, userMsg);
    setChatLog((prev) => [...prev, { role: "assistant", text: improvement.response }]);
    if (improvement.improved) setImprovedPrompt(improvement.improved);
  }

  async function generateImprovedPrompt(original: string, request: string): Promise<{response: string; improved: string | null}> {
    try {
      const token = getToken();
      const res = await fetch("/api/chat/stream", {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ prompt: `Improve this system prompt for a PI agent role.\\n\\nCurrent prompt:\\n---\\n${original}\\n---\\n\\nUser request: ${request}\\n\\nProvide the improved prompt in full. Prefix with IMPROVED_PROMPT:` }),
      });
      const reader = res.body?.getReader();
      if (!reader) return { response: "Could not connect to PI agent", improved: null };
      let text = "";
      const decoder = new TextDecoder();
      while (true) { const { done, value } = await reader.read(); if (done) break; text += decoder.decode(value, { stream: true }); }
      let full = "";
      for (const line of text.split("\\n")) {
        if (line.startsWith("data: ")) { try { const data = JSON.parse(line.slice(6)); if (data.type === "response" && data.text) full += data.text + "\\n"; } catch {} }
      }
      const improvedMatch = full.match(/IMPROVED_PROMPT:([\\s\\S]*)/);
      return { response: full.slice(0, 500) || "Done", improved: improvedMatch ? improvedMatch[1].trim() : null };
    } catch (e: any) { return { response: `Error: ${e.message}`, improved: null }; }
  }

  if (l1 || l2) return <div style={{ color: "var(--color-hermes-text-secondary)" }}>Loading...</div>;

  return (
    <div>
      <div className="page-header">
        <h1>Rollen</h1>
        <p>Sub-Agenten (swarm-spawner) + Organisationale Rollen</p>
      </div>

      <div className="page-header" style={{ marginBottom: 12 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>🏢 Organisationale Rollen</h2>
        <p>Strategische Perspektiven für den PI Agent (CEO-digital, CIO, CMO, CFO)</p>
      </div>
      <div className="card-grid" style={{ marginBottom: 24 }}>
        {(orgRoles || []).map((role: any) => (
          <div key={role.name} className="card" style={{ cursor: "pointer", display: "flex", flexDirection: "column", gap: 8, borderTop: role.name === "CEO-digital" ? "3px solid gold" : `3px solid ${role.provider === "ollama" ? "var(--color-hermes-accent)" : "var(--color-hermes-accent-blue)"}` }} onDoubleClick={() => { setSelectedRole(role); setChatLog([]); setImprovedPrompt(null); }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 24 }}>{role.emoji}</span>
              <div>
                <span style={{ fontWeight: 600, fontSize: 16 }}>{role.name}</span>
                <div style={{ fontSize: 12, color: "var(--color-hermes-accent-orange)", marginTop: 1 }}>{role.description}</div>
              </div>
              <span className={`badge ${role.provider === "ollama" ? "badge-green" : "badge-blue"}`}>{role.provider}/{role.model}</span>
            </div>
            <details><summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 500, color: "var(--color-hermes-accent-blue)" }}>System Prompt</summary>
              <pre style={{ fontFamily: "var(--font-mono)", fontSize: 11, whiteSpace: "pre-wrap", wordBreak: "break-word", margin: "8px 0 0", color: "var(--color-hermes-text-secondary)", maxHeight: 200, overflow: "auto", lineHeight: 1.4, padding: 8, background: "var(--color-hermes-muted)", borderRadius: 4 }}>{role.systemPrompt}</pre>
            </details>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>{(role.toolWhitelist || []).map((t: string) => <span key={t} className="badge badge-blue">{t}</span>)}</div>
          </div>
        ))}
      </div>

      <div className="page-header" style={{ marginBottom: 12 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>🤖 Sub-Agenten (swarm-spawner)</h2>
        <p>4 Rollen die als Subprozesse mit ollama/gemma4:12b laufen</p>
      </div>
      <div className="card-grid" style={{ marginBottom: 24 }}>
        {(roles || []).map((role: any) => (
          <div key={role.name} className="card" style={{ cursor: "pointer", display: "flex", flexDirection: "column", gap: 10, borderTop: `3px solid ${role.provider === "ollama" ? "var(--color-hermes-accent)" : "var(--color-hermes-danger)"}` }} onDoubleClick={() => { setSelectedRole(role); setChatLog([]); setImprovedPrompt(null); }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 24 }}>{ROLE_ICONS[role.name] || "🤖"}</span>
              <div>
                <span style={{ fontWeight: 600, fontSize: 16 }}>{role.name}</span>
                <div style={{ display: "flex", gap: 4, marginTop: 2 }}><span className="badge badge-green">{role.provider}/{role.model}</span><span className="badge badge-blue">{role.timeoutSec}s</span></div>
              </div>
            </div>
            <div style={{ padding: "6px 8px", borderRadius: 6, fontSize: 12, background: role.provider === "ollama" ? "rgba(46,160,67,0.08)" : "rgba(248,81,73,0.08)", color: role.provider === "ollama" ? "var(--color-hermes-accent)" : "var(--color-hermes-danger)" }}>
              {role.provider === "ollama" ? "🆓 Lokal (0 Token-Kosten)" : "💰 MiniMax (kostenpflichtig)"}{role.estimatedSavingsUsd > 0 && <span> · ~${role.estimatedSavingsUsd.toFixed(2)}/call</span>}
            </div>
            <details><summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 500, color: "var(--color-hermes-accent-blue)" }}>System Prompt</summary>
              <pre style={{ fontFamily: "var(--font-mono)", fontSize: 11, whiteSpace: "pre-wrap", wordBreak: "break-word", margin: "8px 0 0", color: "var(--color-hermes-text-secondary)", maxHeight: 200, overflow: "auto", lineHeight: 1.4, padding: 8, background: "var(--color-hermes-muted)", borderRadius: 4 }}>{role.systemPrompt}</pre>
            </details>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>{(role.toolWhitelist || []).map((t: string) => <span key={t} className="badge badge-blue">{t}</span>)}</div>
            <div style={{ fontSize: 12, display: "flex", gap: 12, color: "var(--color-hermes-text-secondary)" }}>
              <span>Fresh: {role.freshContext ? <Check size={12} color="var(--color-hermes-accent)" style={{ display: "inline" }} /> : <X size={12} color="var(--color-hermes-text-secondary)" style={{ display: "inline" }} />}</span>
              <span>Timeout: {role.timeoutSec}s</span>
            </div>
          </div>
        ))}
      </div>

      {/* Prompt Editor + Chat — Modal Popup */}
      {selectedRole && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
          background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center",
          zIndex: 1000,
        }} onClick={() => setSelectedRole(null)}>
          <div style={{
            background: "var(--color-hermes-surface)", border: "1px solid var(--color-hermes-border)", borderRadius: 12,
            width: "90%", maxWidth: 1100, maxHeight: "85vh", display: "flex", gap: 16, padding: 20,
          }} onClick={(e) => e.stopPropagation()}>
            {/* Left: Prompt Editor */}
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <h3 style={{ fontSize: 14, fontWeight: 600, margin: 0 }}>{ROLE_ICONS[selectedRole.name] || "🤖"} {selectedRole.name} — System Prompt</h3>
              </div>
              <textarea className="input" style={{ fontFamily: "var(--font-mono)", fontSize: 12, minHeight: 350, resize: "vertical", whiteSpace: "pre", overflow: "auto", lineHeight: 1.5 }}
                value={improvedPrompt !== null ? improvedPrompt : (selectedRole.systemPrompt || "")}
                onChange={(e) => setImprovedPrompt(e.target.value)} />
              {improvedPrompt !== null && <div style={{ fontSize: 12, color: "var(--color-hermes-accent)" }}>✨ AI-verbessert</div>}
            </div>
            {/* Right: Chat */}
            <div className="card" style={{ width: 320, minWidth: 320, display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>💬 KI-Chat</span>
                <button className="btn" style={{ padding: "2px 8px", fontSize: 11 }} onClick={() => setSelectedRole(null)}>✕</button>
              </div>
              <div style={{ flex: 1, overflow: "auto", display: "flex", flexDirection: "column", gap: 6, minHeight: 250, maxHeight: 400 }}>
                {chatLog.length === 0 && <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)", textAlign: "center", padding: 20 }}>Doppelklick auf Rolle öffnet den Prompt-Editor.</div>}
                {chatLog.map((entry, i) => (
                  <div key={i} style={{ padding: "6px 10px", borderRadius: 6, fontSize: 12, background: entry.role === "user" ? "rgba(88,166,255,0.1)" : "rgba(46,160,67,0.1)", borderLeft: `3px solid ${entry.role === "user" ? "var(--color-hermes-accent-blue)" : "var(--color-hermes-accent)"}` }}>
                    <div style={{ fontWeight: 500, marginBottom: 2 }}>{entry.role === "user" ? "Du" : "KI"}</div>
                    <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.4 }}>{entry.text}</div>
                  </div>
                ))}
              </div>
              <div style={{ display: "flex", gap: 4 }}>
                <input className="input" style={{ fontFamily: "var(--font-mono)", fontSize: 12 }} placeholder="Verbesserungswunsch..." value={chatInput} onChange={(e) => setChatInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleImprove()} />
                <button className="btn btn-primary" style={{ padding: "4px 10px" }} onClick={handleImprove} disabled={!chatInput.trim()}><Send size={14} /></button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
