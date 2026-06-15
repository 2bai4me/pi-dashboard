import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Plus, Trash2, Play, Wifi, WifiOff, Activity, CheckCircle, XCircle, Clock } from "lucide-react";
import { api } from "../api";

export default function McpServers() {
  const [showForm, setShowForm] = useState(false);
  const [showConnections, setShowConnections] = useState(false);
  const [name, setName] = useState("");
  const [command, setCommand] = useState("");
  const [args, setArgs] = useState("");
  const [url, setUrl] = useState("");
  const [transport, setTransport] = useState("stdio");
  const [testResult, setTestResult] = useState<string | null>(null);

  const serversQuery = useQuery({
    queryKey: ["mcp-servers"],
    queryFn: () => api.get("/mcp/servers"),
  });

  const saveMut = useMutation({
    mutationFn: (data: any) => api.put("/mcp/servers", data),
    onSuccess: () => { serversQuery.refetch(); setShowForm(false); },
  });

  const testMut = useMutation({
    mutationFn: (data: any) => api.post("/mcp/servers/test", data),
    onSuccess: (data) => {
      setTestResult(data.ok ? `OK: ${data.stdout || data.status}` : `FAILED: ${data.error || data.stderr}`);
    },
    onError: (err: any) => setTestResult(`ERROR: ${err.message}`),
  });

  const servers = serversQuery.data || [];

  function handleAdd() {
    const current = servers;
    const newServer: any = { name, command: command || undefined, args: args ? args.split(" ").filter(Boolean) : [], url: url || undefined, transport };
    saveMut.mutate([...current, newServer]);
  }

  function handleRemove(idx: number) {
    const current = [...servers];
    current.splice(idx, 1);
    saveMut.mutate(current);
  }

  return (
    <div>
      <div className="page-header" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h1>MCP Servers</h1>
          <p>Model Context Protocol — tool servers for the agent</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn" onClick={() => setShowConnections(!showConnections)}>
            <Activity size={14} /> {showConnections ? "Hide Connections" : "Active Connections"}
          </button>
          <button className="btn btn-primary" onClick={() => { setShowForm(!showForm); setTestResult(null); }}>
            <Plus size={14} /> {showForm ? "Cancel" : "Add Server"}
          </button>
        </div>
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <input className="input" placeholder="Server name" value={name} onChange={(e) => setName(e.target.value)} />
            <div style={{ display: "flex", gap: 8 }}>
              <input className="input" placeholder="Command (e.g. npx)" value={command} onChange={(e) => setCommand(e.target.value)} style={{ flex: 1 }} />
              <input className="input" placeholder="Args (space-separated)" value={args} onChange={(e) => setArgs(e.target.value)} style={{ flex: 1 }} />
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <input className="input" placeholder="URL (for SSE transport)" value={url} onChange={(e) => setUrl(e.target.value)} style={{ flex: 1 }} />
              <select className="input" style={{ width: "auto" }} value={transport} onChange={(e) => setTransport(e.target.value)}>
                <option value="stdio">stdio</option>
                <option value="sse">SSE</option>
              </select>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-primary" onClick={handleAdd} disabled={!name}>Save</button>
              <button className="btn" onClick={() => testMut.mutate({ name, command: command || undefined, args: args ? args.split(" ").filter(Boolean) : [], url: url || undefined, transport })} disabled={!command && !url}>
                <Play size={14} /> Test
              </button>
            </div>
            {testResult && (
              <div style={{ fontSize: 13, padding: "6px 10px", borderRadius: 6, background: testResult.startsWith("OK") ? "rgba(46,160,67,0.1)" : "rgba(248,81,73,0.1)" }}>
                {testResult}
              </div>
            )}
          </div>
        </div>
      )}

      {showConnections && <ActiveConnectionsPanel />}

      {servers.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 40 }}>
          <WifiOff size={24} style={{ color: "var(--color-hermes-text-secondary)", marginBottom: 8 }} />
          <p style={{ color: "var(--color-hermes-text-secondary)", margin: 0 }}>No MCP servers configured</p>
        </div>
      ) : (
        <div className="card-grid">
          {servers.map((s: any, i: number) => (
            <div key={s.name || i} className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Wifi size={14} color="var(--color-hermes-accent)" />
                <span style={{ fontWeight: 600, fontSize: 14 }}>{s.name}</span>
                <span className="badge badge-blue">{s.transport}</span>
              </div>
              {s.command && (
                <div style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--color-hermes-text-secondary)" }}>
                  {s.command} {s.args?.join(" ")}
                </div>
              )}
              {s.url && <div style={{ fontSize: 12, color: "var(--color-hermes-accent-blue)" }}>{s.url}</div>}
              {s.env && Object.keys(s.env).length > 0 && (
                <div style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>Env: {Object.keys(s.env).join(", ")}</div>
              )}
              <button className="btn" style={{ alignSelf: "flex-start", padding: "4px 8px" }} onClick={() => handleRemove(i)}>
                <Trash2 size={12} color="var(--color-hermes-danger)" /> Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Active Connections Panel ────────────────────────────────────

function ActiveConnectionsPanel() {
  const { data: connections, isLoading, error } = useQuery({
    queryKey: ["mcp-connections"],
    queryFn: () => api.get("/mcp/connections"),
    refetchInterval: 15000,
  });

  if (isLoading) return <div className="card" style={{ marginBottom: 16, color: "var(--color-hermes-text-secondary)" }}>Checking connections...</div>;
  if (error) return <div className="card" style={{ marginBottom: 16, color: "var(--color-hermes-danger)" }}>Failed to check connections</div>;
  if (!connections?.length) return <div className="card" style={{ marginBottom: 16, color: "var(--color-hermes-text-secondary)" }}>No servers to check</div>;

  return (
    <div className="card" style={{ marginBottom: 16, padding: 12 }}>
      <h3 style={{ fontSize: 13, fontWeight: 600, margin: "0 0 8px", display: "flex", alignItems: "center", gap: 6 }}>
        <Activity size={14} /> Active Connections
      </h3>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {connections.map((c: any) => {
          const statusIcon = c.status === "connected" ? <CheckCircle size={14} color="var(--color-hermes-accent)" /> :
            c.status === "error" || c.status === "not_found" ? <XCircle size={14} color="var(--color-hermes-danger)" /> :
            <Clock size={14} color="var(--color-hermes-accent-orange)" />;
          return (
            <div key={c.name} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", background: "var(--color-hermes-muted)", borderRadius: 6 }}>
              {statusIcon}
              <span style={{ fontWeight: 500, fontSize: 13, flex: 1 }}>{c.name}</span>
              <span className={`badge ${c.status === "connected" ? "badge-green" : c.status === "error" || c.status === "not_found" ? "badge-red" : "badge-orange"}`}>
                {c.status}
              </span>
              {c.latency_ms && (
                <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
                  {c.latency_ms}ms
                </span>
              )}
              {c.error && (
                <span style={{ fontSize: 10, color: "var(--color-hermes-danger)", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {c.error}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
