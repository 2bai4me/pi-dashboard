import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Search, Trash2 } from "lucide-react";
import { api } from "../api";

export default function Sessions() {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("modified");

  const { data: sessions, isLoading, error, refetch } = useQuery({
    queryKey: ["sessions", search, sort],
    queryFn: () =>
      search
        ? api.searchSessions(search)
        : api.listSessions(50, sort),
  });

  const { data: stats } = useQuery({
    queryKey: ["session-stats"],
    queryFn: () => api.sessionStats(),
  });

  async function handleDelete(id: string) {
    if (!confirm("Delete this session?")) return;
    await api.deleteSession(id);
    refetch();
  }

  return (
    <div>
      <div className="page-header">
        <h1>Sessions</h1>
        <p>Browse, search, and manage conversation sessions</p>
      </div>

      {/* Stats */}
      {stats && (
        <div className="card-grid" style={{ marginBottom: 16 }}>
          {Object.entries(stats.by_model || {}).map(([model, count]: [string, any]) => (
            <div key={model} className="stat-card" style={{ padding: "8px 12px" }}>
              <div className="label">{model.split("/")[1] || model}</div>
              <div className="value" style={{ fontSize: 18 }}>{count} sessions</div>
            </div>
          ))}
        </div>
      )}

      {/* Search Bar */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <div style={{ position: "relative", flex: 1 }}>
          <Search size={14} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--color-hermes-text-secondary)" }} />
          <input
            className="input"
            style={{ paddingLeft: 32 }}
            placeholder="Search sessions..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select className="input" style={{ width: "auto" }} value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="modified">Last modified</option>
          <option value="created">Created</option>
          <option value="name">Name</option>
        </select>
      </div>

      {/* Session Table */}
      {isLoading ? (
        <div style={{ color: "var(--color-hermes-text-secondary)" }}>Loading...</div>
      ) : error ? (
        <div style={{ color: "var(--color-hermes-danger)" }}>Failed to load sessions</div>
      ) : !sessions?.length ? (
        <div style={{ color: "var(--color-hermes-text-secondary)", textAlign: "center", padding: 40 }}>
          No sessions found
        </div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Name / ID</th>
              <th>Model</th>
              <th>Messages</th>
              <th>First Message</th>
              <th>Last Modified</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s: any) => (
              <tr key={s.id}>
                <td>
                  <Link to={`/sessions/${s.id}`} style={{ color: "var(--color-hermes-accent-blue)", textDecoration: "none", fontWeight: 500 }}>
                    {s.name || s.id.slice(0, 16)}...
                  </Link>
                </td>
                <td style={{ color: "var(--color-hermes-text-secondary)" }}>
                  {s.model ? (
                    <span className="badge badge-blue">{s.model.split("/").pop()}</span>
                  ) : "—"}
                </td>
                <td>{s.message_count}</td>
                <td style={{ maxWidth: 250, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--color-hermes-text-secondary)" }}>
                  {s.first_user_message || "—"}
                </td>
                <td style={{ color: "var(--color-hermes-text-secondary)", fontSize: 12 }}>
                  {s.modified_at ? new Date(s.modified_at).toLocaleDateString() : "—"}
                </td>
                <td>
                  <button className="btn" style={{ padding: "4px 8px" }} onClick={() => handleDelete(s.id)} title="Delete">
                    <Trash2 size={14} style={{ color: "var(--color-hermes-danger)" }} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
