import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, X, Star, Plus, Zap, Trash2, TestTube2, Edit2, RefreshCw, Power } from "lucide-react";
import { api, getToken } from "../api";

const QUICK_SWITCH_TARGETS = [
  { id: "ollama-gemma4", label: "Ollama Gemma4 12b (lokal)", emoji: "🖥️", desc: "Schnell, kostenlos, lokal" },
  { id: "ollama-gemma3-4b", label: "Ollama Gemma3 4b (schnell)", emoji: "⚡", desc: "Sehr schnell, kleines Modell" },
  { id: "minimax-m3", label: "MiniMax M3 (Cloud, smart)", emoji: "🧠", desc: "1M Context, Reasoning-fähig" },
  { id: "minimax-m2.7", label: "MiniMax M2.7 (Cloud)", emoji: "🧠", desc: "1M Context, Reasoning-fähig" },
];

export default function Models() {
  const qc = useQueryClient();
  const [showAddProvider, setShowAddProvider] = useState(false);
  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<any | null>(null);

  const { data: models, isLoading } = useQuery({
    queryKey: ["models"],
    queryFn: () => api.listModels(),
  });
  const { data: providers } = useQuery({
    queryKey: ["providers"],
    queryFn: () => api.listProviders(),
  });
  const { data: status } = useQuery({
    queryKey: ["status"],
    queryFn: () => api.status(),
  });

  const setDefault = useMutation({
    mutationFn: (modelId: string) => api.setDefaultModel(modelId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["models"] }); qc.invalidateQueries({ queryKey: ["status"] }); },
  });
  const toggleModel = useMutation({
    mutationFn: (modelId: string) => api.toggleModel(modelId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["models"] }),
  });
  const addProvider = useMutation({
    mutationFn: (data: any) => api.addProvider(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["providers"] }); qc.invalidateQueries({ queryKey: ["models"] }); setShowAddProvider(false); },
  });
  const deleteProvider = useMutation({
    mutationFn: (name: string) => api.deleteProvider(name),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["providers"] }); qc.invalidateQueries({ queryKey: ["models"] }); },
  });
  const testProviderMut = useMutation({
    mutationFn: (name: string) => api.testProvider(name),
    onSuccess: (data: any) => setTestResult(data),
  });
  // === Pricing-Management (15.06.2026, Task 1d45c65b853b Erweiterung) ===
  const { data: pricing } = useQuery({
    queryKey: ["pricing"],
    queryFn: () => api.getPricing(),
  });
  const refreshPricingMut = useMutation({
    mutationFn: () => api.refreshPricing(),
    onSuccess: (data: any) => {
      qc.invalidateQueries({ queryKey: ["pricing"] });
      qc.invalidateQueries({ queryKey: ["models"] });
      setTestResult({ ok: true, provider: `Pricing refresh: ${data.updated_count} models updated, ${data.skipped_count} skipped` });
    },
  });
  const updatePricingMut = useMutation({
    mutationFn: (data: { provider: string; model_id?: string; input_per_1m: number; output_per_1m: number; note?: string }) =>
      api.updatePricing(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pricing"] });
      qc.invalidateQueries({ queryKey: ["models"] });
    },
  });
  });
  const quickSwitch = useMutation({
    mutationFn: (target: string) => api.quickSwitchProvider(target),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["models"] }); qc.invalidateQueries({ queryKey: ["status"] }); },
  });

  if (isLoading) return <div style={{ color: "var(--color-hermes-text-secondary)" }}>Loading...</div>;

  const byProvider: Record<string, any[]> = {};
  (models || []).forEach((m: any) => {
    if (!byProvider[m.provider]) byProvider[m.provider] = [];
    byProvider[m.provider].push(m);
  });

  const currentDefault = (models || []).find((m: any) => m.is_default);

  return (
    <div>
      <div className="page-header">
        <h1>🧠 Models & Providers</h1>
        <p>Schneller Wechsel zwischen Ollama (lokal) und MiniMax (Cloud) — oder eigenen Provider hinzufügen</p>
      </div>

      {/* Quick-Switch Bar */}
      <div className="card" style={{ marginBottom: 16, padding: 16, background: "rgba(88,166,255,0.05)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
          <Zap size={16} color="var(--color-hermes-accent-orange)" />
          <span style={{ fontSize: 14, fontWeight: 600 }}>Schnell-Wechsel</span>
          {currentDefault && (
            <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
              Aktuell: <strong style={{ color: "var(--color-hermes-accent)" }}>{currentDefault.full_id}</strong>
            </span>
          )}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 8 }}>
          {QUICK_SWITCH_TARGETS.map((t) => {
            const isCurrent = currentDefault?.id === t.id.split("-").slice(-1)[0] && currentDefault?.provider === t.id.split("-")[0];
            const isActive = quickSwitch.isPending && quickSwitch.variables === t.id;
            return (
              <button
                key={t.id}
                className="btn"
                disabled={isCurrent || isActive}
                onClick={() => quickSwitch.mutate(t.id)}
                style={{
                  padding: 10, fontSize: 12, textAlign: "left",
                  background: isCurrent ? "rgba(46,160,67,0.15)" : "var(--color-hermes-surface-2)",
                  border: isCurrent ? "1px solid var(--color-hermes-accent)" : "1px solid transparent",
                  opacity: isCurrent ? 0.6 : 1,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontSize: 16 }}>{t.emoji}</span>
                  <span style={{ fontWeight: 600 }}>{t.label}</span>
                  {isCurrent && <Check size={12} color="var(--color-hermes-accent)" />}
                </div>
                <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", marginTop: 2 }}>
                  {t.desc}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Providers Header mit Add-Button */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>Provider ({providers?.length || 0})</h2>
        <button className="btn btn-primary" onClick={() => setShowAddProvider(true)}>
          <Plus size={14} /> Custom Provider
        </button>
      </div>

      {/* === Pricing-Section (15.06.2026, Task 1d45c65b853b Erweiterung) === */}
      <div className="card" style={{ marginBottom: 24, padding: 16, borderLeft: "3px solid var(--color-hermes-accent)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <div>
            <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>💰 Pricing (USD pro 1M Tokens)</h2>
            <p style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)", margin: "4px 0 0" }}>
              Wird beim Task-Start als Snapshot im Task gespeichert. Spätere Preisaenderungen beruehren abgeschlossene Tasks NICHT.
            </p>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button
              className="btn"
              onClick={() => refreshPricingMut.mutate()}
              disabled={refreshPricingMut.isPending}
              title="Aktualisiert alle Provider-Preise aus der internen Datenbank (platform.minimax.io, openrouter.ai)"
            >
              <RefreshCw size={14} className={refreshPricingMut.isPending ? "spin" : ""} /> Preise aktualisieren
            </button>
          </div>
        </div>
        {pricing ? (
          <table className="data-table" style={{ fontSize: 12 }}>
            <thead>
              <tr>
                <th>Provider</th>
                <th>Modell</th>
                <th>Input $/M</th>
                <th>Output $/M</th>
                <th>Source</th>
                <th>Last updated</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(pricing).flatMap(([provName, provData]: [string, any]) =>
                Object.entries(provData.models || {}).map(([modelKey, p]: [string, any]) => (
                  <PricingRow
                    key={`${provName}/${modelKey}`}
                    provider={provName}
                    modelKey={modelKey}
                    pricing={p}
                    onUpdate={(input, output, note) =>
                      updatePricingMut.mutate({ provider: provName, model_id: modelKey === "default" ? undefined : modelKey, input_per_1m: input, output_per_1m: output, note })
                    }
                    isLoading={updatePricingMut.isPending}
                  />
                ))
              )}
            </tbody>
          </table>
        ) : (
          <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>Lade Preise...</div>
        )}
      </div>

      <div className="card-grid" style={{ marginBottom: 24 }}>
        {(providers || []).map((p: any) => {
          const isProtected = ["ollama", "minimax-direct"].includes(p.name);
          return (
            <div key={p.name} className="stat-card" style={{ padding: 12, gap: 4 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ fontSize: 14, fontWeight: 600 }}>{p.name}</div>
                <div style={{ display: "flex", gap: 4 }}>
                  <button
                    className="btn"
                    style={{ padding: "2px 6px", fontSize: 10 }}
                    onClick={() => { setTestResult(null); testProviderMut.mutate(p.name); }}
                    disabled={testProviderMut.isPending}
                    title="Verbindung testen"
                  >
                    <TestTube2 size={12} />
                  </button>
                  {!isProtected && (
                    <button
                      className="btn"
                      style={{ padding: "2px 6px", fontSize: 10 }}
                      onClick={() => { if (confirm(`Provider "${p.name}" wirklich löschen?`)) deleteProvider.mutate(p.name); }}
                      title="Löschen"
                    >
                      <Trash2 size={12} color="var(--color-hermes-danger)" />
                    </button>
                  )}
                </div>
              </div>
              <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
                {p.base_url ? p.base_url.replace(/^https?:\/\//, "").slice(0, 40) : "local"}
              </div>
              <div style={{ marginTop: 4, display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                <span className="badge badge-blue">{p.model_count} models</span>
                {p.has_key ? (
                  <span className="badge badge-green">✓ Key</span>
                ) : (
                  <span className="badge badge-red">✗ No key</span>
                )}
                {isProtected && <span className="badge badge-orange">geschützt</span>}
              </div>
            </div>
          );
        })}
      </div>

      {/* Test-Result Banner */}
      {testResult && (
        <div className="card" style={{
          marginBottom: 16, padding: 10,
          background: testResult.ok ? "rgba(46,160,67,0.1)" : "rgba(248,81,73,0.1)",
          borderLeft: `3px solid ${testResult.ok ? "var(--color-hermes-accent)" : "var(--color-hermes-danger)"}`,
        }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: testResult.ok ? "var(--color-hermes-accent)" : "var(--color-hermes-danger)" }}>
            {testResult.ok ? "✅ Verbindung OK" : "❌ Verbindung fehlgeschlagen"}: {testResult.provider}
          </div>
          {testResult.url && <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>URL: {testResult.url}</div>}
          {testResult.status && <div style={{ fontSize: 11 }}>Status: {testResult.status}</div>}
          {testResult.error && <div style={{ fontSize: 11 }}>Error: {testResult.error}</div>}
          <button className="btn" style={{ marginTop: 6, padding: "2px 8px", fontSize: 10 }} onClick={() => setTestResult(null)}>✕ Schließen</button>
        </div>
      )}

      {/* Models per Provider */}
      <h2 style={{ fontSize: 16, fontWeight: 600, margin: "0 0 12px" }}>Modelle</h2>
      {Object.entries(byProvider).map(([provider, ms]) => (
        <div key={provider} style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 8px", textTransform: "capitalize" }}>
            {provider}
          </h3>
          <table className="data-table">
            <thead>
              <tr>
                <th>Model ID</th>
                <th>Context</th>
                <th>Reasoning</th>
                <th>Input</th>
                <th>Status</th>
                <th>Default</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {ms.map((m: any) => (
                <tr key={m.full_id}>
                  <td style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{m.id}</td>
                  <td>{m.context_window ? `${(m.context_window / 1000).toFixed(0)}k` : "—"}</td>
                  <td>{m.reasoning ? <Check size={14} color="var(--color-hermes-accent)" /> : <X size={14} color="var(--color-hermes-text-secondary)" />}</td>
                  <td style={{ color: "var(--color-hermes-text-secondary)", fontSize: 12 }}>{m.input?.join(", ") || "—"}</td>
                  <td>
                    {m.enabled ? (
                      <span className="badge badge-green">On</span>
                    ) : (
                      <span className="badge badge-orange">Off</span>
                    )}
                  </td>
                  <td>
                    {m.is_default ? (
                      <Star size={14} color="var(--color-hermes-accent-orange)" fill="var(--color-hermes-accent-orange)" />
                    ) : "—"}
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 4 }}>
                      {!m.is_default && (
                        <button className="btn" style={{ padding: "2px 8px", fontSize: 11 }} onClick={() => setDefault.mutate(m.full_id)} disabled={setDefault.isPending}>
                          Set Default
                        </button>
                      )}
                      <button className="btn" style={{ padding: "2px 8px", fontSize: 11 }} onClick={() => toggleModel.mutate(m.full_id)} disabled={toggleModel.isPending}>
                        {m.enabled ? "Disable" : "Enable"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {/* Add-Provider-Modal */}
      {showAddProvider && (
        <AddProviderModal
          onClose={() => setShowAddProvider(false)}
          onSubmit={(data) => addProvider.mutate(data)}
          isLoading={addProvider.isPending}
        />
      )}
    </div>
  );
}

function AddProviderModal({ onClose, onSubmit, isLoading }: { onClose: () => void; onSubmit: (data: any) => void; isLoading: boolean }) {
  const [name, setName] = useState("");
  const [api, setApi] = useState("openai-completions");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [authHeader, setAuthHeader] = useState("");
  const [modelsText, setModelsText] = useState("claude-3-5-sonnet");
  const [contextWindow, setContextWindow] = useState("200000");

  const handleSubmit = () => {
    const models = modelsText.split(",").map((mid) => ({
      id: mid.trim(),
      contextWindow: parseInt(contextWindow) || 128000,
      reasoning: true,
      input: ["text"],
    })).filter((m) => m.id);
    onSubmit({
      name: name.trim(),
      api,
      base_url: baseUrl.trim(),
      api_key: apiKey.trim(),
      auth_header: authHeader.trim(),
      models,
    });
  };

  return (
    <div onClick={onClose} style={{
      position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
      background: "rgba(0,0,0,0.55)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
    }}>
      <div onClick={(e) => e.stopPropagation()} className="card" style={{ maxWidth: 540, width: "100%", padding: 20 }}>
        <h2 style={{ margin: "0 0 16px", fontSize: 18, display: "flex", alignItems: "center", gap: 8 }}>
          <Plus size={18} /> Custom Provider hinzufügen
        </h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <label style={{ fontSize: 12, fontWeight: 600 }}>Name (alphanumerisch, ohne Leerzeichen)</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="z.B. anthropic, openai, mein-eigener" />

          <label style={{ fontSize: 12, fontWeight: 600 }}>API-Typ</label>
          <select className="input" value={api} onChange={(e) => setApi(e.target.value)}>
            <option value="openai-completions">OpenAI-kompatibel (/v1/chat/completions)</option>
            <option value="anthropic-messages">Anthropic Messages API</option>
            <option value="google-generative-ai">Google Generative AI</option>
            <option value="ollama">Ollama (nativ)</option>
          </select>

          <label style={{ fontSize: 12, fontWeight: 600 }}>Base URL (ohne trailing /v1)</label>
          <input className="input" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="z.B. https://api.anthropic.com" />

          <label style={{ fontSize: 12, fontWeight: 600 }}>API Key</label>
          <input className="input" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-..." />

          <label style={{ fontSize: 12, fontWeight: 600 }}>Custom Auth Header (optional, falls nicht Authorization)</label>
          <input className="input" value={authHeader} onChange={(e) => setAuthHeader(e.target.value)} placeholder="z.B. x-api-key" />

          <label style={{ fontSize: 12, fontWeight: 600 }}>Modelle (kommasepariert)</label>
          <input className="input" value={modelsText} onChange={(e) => setModelsText(e.target.value)} placeholder="claude-3-5-sonnet, claude-3-haiku" />

          <label style={{ fontSize: 12, fontWeight: 600 }}>Context Window (für alle Modelle)</label>
          <input className="input" type="number" value={contextWindow} onChange={(e) => setContextWindow(e.target.value)} placeholder="200000" />
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
          <button className="btn" onClick={onClose}>Abbrechen</button>
          <button className="btn btn-primary" onClick={handleSubmit} disabled={!name.trim() || isLoading}>
            {isLoading ? "..." : "Hinzufügen"}
          </button>
        </div>
      </div>
    </div>
  );
}


// === Pricing-Row mit Inline-Editor (15.06.2026) ===
function PricingRow({
  provider, modelKey, pricing, onUpdate, isLoading,
}: {
  provider: string;
  modelKey: string;
  pricing: { input_per_1m: number; output_per_1m: number; currency?: string; source?: string; last_updated?: string; note?: string };
  onUpdate: (input: number, output: number, note?: string) => void;
  isLoading: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [inputPrice, setInputPrice] = useState(pricing.input_per_1m ?? 0);
  const [outputPrice, setOutputPrice] = useState(pricing.output_per_1m ?? 0);
  const [note, setNote] = useState(pricing.note ?? "");

  useEffect(() => {
    setInputPrice(pricing.input_per_1m ?? 0);
    setOutputPrice(pricing.output_per_1m ?? 0);
  }, [pricing.input_per_1m, pricing.output_per_1m]);

  return (
    <tr>
      <td style={{ fontWeight: 600 }}>{provider}</td>
      <td style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>{modelKey}</td>
      <td>
        {editing ? (
          <input
            className="input"
            type="number"
            step="0.01"
            value={inputPrice}
            onChange={(e) => setInputPrice(parseFloat(e.target.value) || 0)}
            style={{ width: 90, padding: "2px 4px", fontSize: 11 }}
          />
        ) : (
          <span>${(pricing.input_per_1m ?? 0).toFixed(3)}</span>
        )}
      </td>
      <td>
        {editing ? (
          <input
            className="input"
            type="number"
            step="0.01"
            value={outputPrice}
            onChange={(e) => setOutputPrice(parseFloat(e.target.value) || 0)}
            style={{ width: 90, padding: "2px 4px", fontSize: 11 }}
          />
        ) : (
          <span>${(pricing.output_per_1m ?? 0).toFixed(3)}</span>
        )}
      </td>
      <td style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }} title={pricing.source || ""}>
        {pricing.source || "—"}
      </td>
      <td style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>
        {pricing.last_updated ? new Date(pricing.last_updated).toLocaleString("de-DE") : "—"}
      </td>
      <td>
        {editing ? (
          <div style={{ display: "flex", gap: 4 }}>
            <button
              className="btn btn-primary"
              style={{ padding: "2px 8px", fontSize: 11 }}
              onClick={() => { onUpdate(inputPrice, outputPrice, note); setEditing(false); }}
              disabled={isLoading}
            >
              Save
            </button>
            <button className="btn" style={{ padding: "2px 8px", fontSize: 11 }} onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        ) : (
          <button className="btn" style={{ padding: "2px 8px", fontSize: 11 }} onClick={() => setEditing(true)} title="Preis manuell überschreiben">
            <Edit2 size={11} /> Edit
          </button>
        )}
      </td>
    </tr>
  );
}
