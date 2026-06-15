import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Play, Pause, Trash2, Plus, RotateCw } from "lucide-react";
import { api } from "../api";

export default function CronJobs() {
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [schedule, setSchedule] = useState("0 9 * * *");
  const [editingId, setEditingId] = useState<string | null>(null);

  const jobsQuery = useQuery({
    queryKey: ["cron-jobs"],
    queryFn: () => api.get("/cron/jobs"),
  });

  const createMut = useMutation({
    mutationFn: (data: any) => editingId ? api.put(`/cron/jobs/${editingId}`, data) : api.post("/cron/jobs", data),
    onSuccess: () => { jobsQuery.refetch(); setShowForm(false); setName(""); setPrompt(""); setEditingId(null); },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.del(`/cron/jobs/${id}`),
    onSuccess: () => jobsQuery.refetch(),
  });

  const toggleMut = useMutation({
    mutationFn: ({ id, action }: { id: string; action: string }) => api.post(`/cron/jobs/${id}/${action}`),
    onSuccess: () => jobsQuery.refetch(),
  });

  const triggerMut = useMutation({
    mutationFn: (id: string) => api.post(`/cron/jobs/${id}/trigger`),
    onSuccess: () => jobsQuery.refetch(),
  });

  const jobs = jobsQuery.data || [];

  async function handleSave() {
    await createMut.mutateAsync({ name, prompt, schedule });
  }

  return (
    <div>
      <div className="page-header" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h1>Cron Jobs</h1>
          <p>Scheduled PI Agent tasks</p>
        </div>
        <button className="btn btn-primary" onClick={() => { setShowForm(!showForm); setEditingId(null); setName(""); setPrompt(""); setSchedule("0 9 * * *"); }}>
          <Plus size={14} /> {showForm ? "Cancel" : "New Job"}
        </button>
      </div>

      {/* Create/Edit Form */}
      {showForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 12px" }}>
            {editingId ? "Edit Job" : "New Cron Job"}
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <input className="input" placeholder="Job name" value={name} onChange={(e) => setName(e.target.value)} />
            <textarea className="input" style={{ fontFamily: "var(--font-mono)", minHeight: 80 }} placeholder="Prompt" value={prompt} onChange={(e) => setPrompt(e.target.value)} />
            <div style={{ display: "flex", gap: 8 }}>
              <input className="input" placeholder="Cron expression (e.g. 0 9 * * *)" value={schedule} onChange={(e) => setSchedule(e.target.value)} />
              <select className="input" style={{ width: "auto" }} value={schedule} onChange={(e) => setSchedule(e.target.value)}>
                <option value="0 9 * * *">Daily 9:00</option>
                <option value="0 */6 * * *">Every 6 hours</option>
                <option value="*/30 * * * *">Every 30 min</option>
                <option value="0 0 * * 0">Weekly Sunday</option>
                <option value="every 1h">Every hour (simple)</option>
              </select>
            </div>
            <button className="btn btn-primary" onClick={handleSave} disabled={!name || !prompt}>
              {createMut.isPending ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      )}

      {/* Jobs Table */}
      <table className="data-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Schedule</th>
            <th>Status</th>
            <th>Last Run</th>
            <th>Next Run</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {jobs.length === 0 ? (
            <tr>
              <td colSpan={6} style={{ padding: 40, textAlign: "center", color: "var(--color-hermes-text-secondary)" }}>
                No cron jobs configured
              </td>
            </tr>
          ) : (
            jobs.map((job: any) => (
              <tr key={job.id}>
                <td style={{ fontWeight: 500 }}>{job.name}</td>
                <td style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--color-hermes-accent-orange)" }}>
                  {job.schedule}
                </td>
                <td>
                  {job.enabled ? (
                    <span className="badge badge-green">Active</span>
                  ) : (
                    <span className="badge badge-orange">Paused</span>
                  )}
                </td>
                <td style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
                  {job.last_run ? new Date(job.last_run).toLocaleString() : "—"}
                </td>
                <td style={{ fontSize: 12, color: "var(--color-hermes-text-secondary)" }}>
                  {job.next_run ? new Date(job.next_run).toLocaleString() : "—"}
                </td>
                <td>
                  <div style={{ display: "flex", gap: 4 }}>
                    <button className="btn" style={{ padding: "4px 8px" }} onClick={() => triggerMut.mutate(job.id)} title="Run now">
                      <Play size={12} color="var(--color-hermes-accent)" />
                    </button>
                    {job.enabled ? (
                      <button className="btn" style={{ padding: "4px 8px" }} onClick={() => toggleMut.mutate({ id: job.id, action: "pause" })} title="Pause">
                        <Pause size={12} color="var(--color-hermes-accent-orange)" />
                      </button>
                    ) : (
                      <button className="btn" style={{ padding: "4px 8px" }} onClick={() => toggleMut.mutate({ id: job.id, action: "resume" })} title="Resume">
                        <RotateCw size={12} color="var(--color-hermes-accent)" />
                      </button>
                    )}
                    <button className="btn" style={{ padding: "4px 8px" }} onClick={() => deleteMut.mutate(job.id)} title="Delete">
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


