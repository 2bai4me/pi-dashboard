import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { api } from "../api";

export default function Skills() {
  const { data: skills, isLoading } = useQuery({
    queryKey: ["skills"],
    queryFn: () => api.listSkills(),
  });

  if (isLoading) return <div style={{ color: "var(--color-hermes-text-secondary)" }}>Loading...</div>;

  return (
    <div>
      <div className="page-header">
        <h1>Skills</h1>
        <p>Installed PI Agent skills (SKILL.md)</p>
      </div>

      {!skills?.length ? (
        <div style={{ color: "var(--color-hermes-text-secondary)", padding: 40, textAlign: "center" }}>
          No skills installed in ~/.pi/agent/skills/
        </div>
      ) : (
        <div className="card-grid">
          {skills.map((s: any) => (
            <div key={s.path} className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <FileText size={16} color="var(--color-hermes-text-secondary)" />
                <span style={{ fontWeight: 600, fontSize: 14 }}>{s.name}</span>
              </div>

              {s.description && (
                <p style={{ fontSize: 13, color: "var(--color-hermes-text-secondary)", margin: 0 }}>
                  {s.description}
                </p>
              )}

              <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                <span className="badge badge-blue">{s.scope}</span>
                <span className="badge badge-orange">{s.has_frontmatter ? "Frontmatter" : "No frontmatter"}</span>
                <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
                  {s.size_bytes > 1024 ? `${(s.size_bytes / 1024).toFixed(1)} KB` : `${s.size_bytes} B`}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
