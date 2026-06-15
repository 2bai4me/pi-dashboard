import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

const BUILTIN_TOOLS = ["read", "write", "edit", "bash", "grep", "find", "ls"];

export default function Tools() {
  const { data: tools, isLoading } = useQuery({
    queryKey: ["tools"],
    queryFn: () => api.listTools(),
  });

  const { data: summary } = useQuery({
    queryKey: ["tools-summary"],
    queryFn: () => api.toolsSummary(),
  });

  if (isLoading) return <div style={{ color: "var(--color-hermes-text-secondary)" }}>Loading...</div>;

  return (
    <div>
      <div className="page-header">
        <h1>Tools</h1>
        <p>Built-in PI Agent tools</p>
      </div>

      {summary && (
        <div className="stat-card" style={{ marginBottom: 16 }}>
          <div className="label">Built-in Tools</div>
          <div className="value">{summary.builtin_count}</div>
          <div className="sublabel">{summary.builtin_tools?.join(", ")}</div>
        </div>
      )}

      <table className="data-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Description</th>
            <th>Type</th>
          </tr>
        </thead>
        <tbody>
          {(tools || []).map((t: any) => (
            <tr key={t.name}>
              <td style={{
                fontFamily: "var(--font-mono)",
                fontWeight: t.builtin ? 600 : 400,
                color: t.builtin ? "var(--color-hermes-accent-blue)" : "var(--color-hermes-text)",
              }}>
                {t.name}
              </td>
              <td style={{ color: "var(--color-hermes-text-secondary)" }}>{t.description}</td>
              <td>
                {t.builtin ? (
                  <span className="badge badge-blue">Built-in</span>
                ) : (
                  <span className="badge badge-green">Custom</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
