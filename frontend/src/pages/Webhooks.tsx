import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Plus, Trash2, ToggleLeft, ToggleRight } from "lucide-react";
import { api } from "../api";

export default function Webhooks() {
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState("all");

  const hooksQuery = useQuery({
    queryKey: ["webhooks"],
    queryFn: () => api.get("/webhooks"),
  });

  const createMut = useMutation({
    mutationFn: (data: any) => api.post("/webhooks", data),
    onSuccess: () => { hooksQuery.refetch(); setShowForm(false); setName(""); setUrl(""); setEvents("all"); },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.del(`/webhooks/${id}`),
    onSuccess: () => hooksQuery.refetch(),
  });

  const toggleMut = useMutation({
    mutationFn: (id: string) => api.post(`/webhooks/${id}/toggle`),
    onSuccess: () => hooksQuery.refetch(),
  });

  const hooks = hooksQuery.data || [];

  return (
    <div>
      <div className="page-header" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h1>Webhooks</h1>
          <p>Manage webhook subscriptions for the agent</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          <Plus size={14} /> {showForm ? "Cancel" : "New Webhook"}
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <input className="input" placeholder="Webhook name" value={name} onChange={(e) => setName(e.target.value)} />
            <input className="input" placeholder="URL (e.g. https://example.com/webhook)" value={url} onChange={(e) => setUrl(e.target.value)} />
            <select className="input" style={{ width: "auto" }} value={events} onChange={(e) => setEvents(e.target.value)}>
              <option value="all">All events</option>
              <option value="session_start,session_end">Session start/end</option>
              <option value="tool_call">Tool calls</option>
              <option value="error">Errors</option>
            </select>
            <button className="btn btn-primary" onClick={() => createMut.mutate({ name, url, events: events.split(",") })} disabled={!name || !url}>
              Create
            </button>
          </div>
        </div>
      )}

      <table className="data-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>URL</th>
            <th>Events</th>
            <th>Status</th>
            <th>Secret</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {hooks.length === 0 ? (
            <tr><td colSpan={6} style={{ padding: 40, textAlign: "center", color: "var(--color-hermes-text-secondary)" }}>
              No webhooks configured
            </td></tr>
          ) : (
            hooks.map((h: any) => (
              <tr key={h.id}>
                <td style={{ fontWeight: 500 }}>{h.name}</td>
                <td style={{ fontSize: 12, color: "var(--color-hermes-accent-blue)", maxWidth: 250, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {h.url}
                </td>
                <td style={{ fontSize: 12 }}>{(h.events || []).join(", ")}</td>
                <td>
                  {h.enabled ? <span className="badge badge-green">Active</span> : <span className="badge badge-orange">Disabled</span>}
                </td>
                <td>
                  {h.secret ? (
                    <span className="badge badge-blue" title={h.secret}>
                      {h.secret.slice(0, 12)}…
                    </span>
                  ) : "—"}
                </td>
                <td>
                  <div style={{ display: "flex", gap: 4 }}>
                    <button className="btn" style={{ padding: "4px 8px" }} onClick={() => toggleMut.mutate(h.id)} title="Toggle">
                      {h.enabled ? <ToggleRight size={14} color="var(--color-hermes-accent)" /> : <ToggleLeft size={14} color="var(--color-hermes-text-secondary)" />}
                    </button>
                    <button className="btn" style={{ padding: "4px 8px" }} onClick={() => deleteMut.mutate(h.id)} title="Delete">
                      <Trash2 size={12} color="var(--color-hermes-danger)" />
                    </button>
                  </div>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
