import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Users, Shield, ShieldOff, Trash2, Plus } from "lucide-react";
import { api, setToken } from "../api";

export default function UserAdmin() {
  const [showForm, setShowForm] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("user");

  const { data: users, isLoading, refetch } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get("/users"),
  });

  const createMut = useMutation({
    mutationFn: (data: any) => api.post("/users", data),
    onSuccess: () => { refetch(); setShowForm(false); setUsername(""); setPassword(""); setRole("user"); },
  });

  const toggleMut = useMutation({
    mutationFn: (username: string) => api.post(`/users/${username}/toggle`),
    onSuccess: () => refetch(),
  });

  const deleteMut = useMutation({
    mutationFn: (username: string) => api.del(`/users/${username}`),
    onSuccess: () => refetch(),
  });

  if (isLoading) return <div style={{ color: "var(--color-hermes-text-secondary)" }}>Loading...</div>;

  return (
    <div>
      <div className="page-header" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Users size={20} color="var(--color-hermes-accent-blue)" />
            User Management
          </h1>
          <p>Multi-user accounts, roles & permissions</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          <Plus size={14} /> {showForm ? "Cancel" : "Add User"}
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <input className="input" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} />
            <input className="input" type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
            <select className="input" style={{ width: "auto" }} value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="user">User</option>
              <option value="admin">Admin</option>
              <option value="viewer">Viewer</option>
            </select>
            <button className="btn btn-primary" onClick={() => createMut.mutate({ username, password, role })} disabled={!username || !password}>
              Create
            </button>
          </div>
        </div>
      )}

      {/* Admin User (from .env) */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Shield size={14} color="var(--color-hermes-accent)" />
          <span style={{ fontWeight: 600 }}>admin</span>
          <span className="badge badge-green">Built-in Admin</span>
          <span style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
            (configured in backend/.env)
          </span>
        </div>
      </div>

      {/* All Users */}
      <table className="data-table">
        <thead>
          <tr>
            <th>Username</th>
            <th>Role</th>
            <th>Status</th>
            <th>Created</th>
            <th>Last Login</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {(users || []).map((u: any) => (
            <tr key={u.username}>
              <td style={{ fontWeight: 500 }}>{u.username}</td>
              <td>
                <span className={`badge ${u.role === "admin" ? "badge-green" : u.role === "viewer" ? "badge-orange" : "badge-blue"}`}>
                  {u.role}
                </span>
              </td>
              <td>
                {u.enabled ? (
                  <span className="badge badge-green">Active</span>
                ) : (
                  <span className="badge badge-red">Disabled</span>
                )}
              </td>
              <td style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
                {u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}
              </td>
              <td style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
                {u.last_login ? new Date(u.last_login).toLocaleString() : "—"}
              </td>
              <td>
                <div style={{ display: "flex", gap: 4 }}>
                  <button className="btn" style={{ padding: "4px 8px" }} onClick={() => toggleMut.mutate(u.username)} title={u.enabled ? "Disable" : "Enable"}>
                    {u.enabled ? <ShieldOff size={12} color="var(--color-hermes-accent-orange)" /> : <Shield size={12} color="var(--color-hermes-accent)" />}
                  </button>
                  <button className="btn" style={{ padding: "4px 8px" }} onClick={() => deleteMut.mutate(u.username)} title="Delete">
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
}
