import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Search, BookOpen, Database } from "lucide-react";
import { api } from "../api";

export default function OpenBrain() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any[] | null>(null);
  const [searching, setSearching] = useState(false);

  const { data: status, isLoading: loadingStatus } = useQuery({
    queryKey: ["openbrain-status"],
    queryFn: () => api.openBrainStatus(),
  });

  const { data: stats } = useQuery({
    queryKey: ["openbrain-stats"],
    queryFn: () => api.openBrainStats(),
    enabled: true,
  });

  async function handleSearch() {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const res = await api.openBrainSearch(query);
      setResults(res.results || res);
    } catch (err: any) {
      setResults([]);
      console.error("Search failed:", err);
    } finally {
      setSearching(false);
    }
  }

  const configured = status?.configured;

  return (
    <div>
      <div className="page-header">
        <h1 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Brain size={20} color="var(--color-hermes-accent-blue)" />
          OpenBrain
        </h1>
        <p>Semantic knowledge base search & integration</p>
      </div>

      {/* Status */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div className={`status-dot ${configured ? "active" : "inactive"}`} />
          <span style={{ fontWeight: 500 }}>
            {configured ? "Connected" : "Not configured"}
          </span>
          {configured && (
            <span style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
              {status.url}
            </span>
          )}
        </div>
        {!configured && !loadingStatus && (
          <p style={{ fontSize: 13, color: "var(--color-hermes-orange)", margin: "8px 0 0" }}>
            Set <code>OPENBRAIN_URL</code> and <code>OPENBRAIN_ACCESS_KEY</code> in <code>backend/.env</code> to connect.
          </p>
        )}
      </div>

      {/* Stats */}
      {stats?.stats && (
        <div className="card-grid" style={{ marginBottom: 24 }}>
          <div className="stat-card">
            <div className="label">Total Thoughts</div>
            <div className="value">{stats.stats.total || "?"}</div>
          </div>
          <div className="stat-card">
            <div className="label">By Type</div>
            <div className="value" style={{ fontSize: 14 }}>
              {stats.stats.by_type ? Object.entries(stats.stats.by_type).slice(0, 5).map(([type, count]: [string, any]) => (
                <div key={type} style={{ display: "inline-flex", gap: 4, marginRight: 8 }}>
                  <span style={{ fontWeight: 400, color: "var(--color-hermes-text-secondary)" }}>{type}</span>
                  <span>{count}</span>
                </div>
              )) : "—"}
            </div>
          </div>
          <div className="stat-card">
            <div className="label">Provider</div>
            <div className="value" style={{ fontSize: 14 }}>{stats.stats.provider || "built-in"}</div>
          </div>
        </div>
      )}

      {/* Search */}
      {configured && (
        <div className="card" style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 12px", display: "flex", alignItems: "center", gap: 6 }}>
            <Search size={14} /> Semantic Search
          </h3>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              className="input"
              placeholder="Search the brain..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            />
            <button className="btn btn-primary" onClick={handleSearch} disabled={searching || !query.trim()}>
              {searching ? "Searching..." : "Search"}
            </button>
          </div>

          {/* Results */}
          {results !== null && (
            <div style={{ marginTop: 16 }}>
              {results.length === 0 ? (
                <div style={{ color: "var(--color-hermes-text-secondary)", fontSize: 13 }}>
                  No results found
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {results.map((r: any, i: number) => (
                    <div key={i} style={{
                      padding: "8px 12px",
                      background: "var(--color-hermes-muted)",
                      borderRadius: 6,
                      borderLeft: "3px solid var(--color-hermes-accent-blue)",
                    }}>
                      <div style={{ fontSize: 12, marginBottom: 4 }}>
                        <span className="badge badge-blue">{r.thought_type || r.type || "thought"}</span>
                        {r.tags && r.tags.map((t: string) => (
                          <span key={t} className="badge badge-orange" style={{ marginLeft: 4 }}>{t}</span>
                        ))}
                        {r.similarity && (
                          <span style={{ marginLeft: 8, fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
                            {(r.similarity * 100).toFixed(0)}% match
                          </span>
                        )}
                      </div>
                      <div style={{
                        fontSize: 12,
                        color: "var(--color-hermes-text)",
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                        maxHeight: 100,
                        overflow: "hidden",
                      }}>
                        {r.content || JSON.stringify(r).slice(0, 300)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Help */}
      <div className="card">
        <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 8px", display: "flex", alignItems: "center", gap: 6 }}>
          <BookOpen size={14} /> About OpenBrain
        </h3>
        <p style={{ fontSize: 13, color: "var(--color-hermes-text-secondary)", margin: 0, lineHeight: 1.5 }}>
          OpenBrain ist ein semantischer Gedächtnisspeicher. PI-Agent speichert dort
          kontextuelle Gedanken, Entscheidungen und Code-Diagramme, die später
          via semantische Suche wieder abgefragt werden können. Tags helfen bei der
          Kategorisierung (Projekt, Code, Bug, Decision, etc.).
        </p>
      </div>
    </div>
  );
}

// Local component for the Brain icon
function Brain({ size, color }: { size: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color || "currentColor"} strokeWidth="2">
      <path d="M12 4a4 4 0 0 1 4 4c0 1.1-.4 2.1-1.1 2.8l1.1 1.1" />
      <path d="M12 4a4 4 0 0 0-4 4c0 1.1.4 2.1 1.1 2.8L8 12l1.1 1.1" />
      <path d="M12 4v16" />
      <path d="M8 20h8" />
      <path d="M6 16h12" />
    </svg>
  );
}
