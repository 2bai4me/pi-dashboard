import { useQuery } from "@tanstack/react-query";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, File, FileText } from "lucide-react";
import { api } from "../api";

export default function ExtensionDetail() {
  const { name } = useParams<{ name: string }>();

  const { data: ext, isLoading } = useQuery({
    queryKey: ["extension", name],
    queryFn: () => api.getExtension(name!),
    enabled: !!name,
  });

  if (isLoading) return <div style={{ color: "var(--color-hermes-text-secondary)" }}>Loading...</div>;
  if (!ext) return <div style={{ color: "var(--color-hermes-danger)" }}>Extension not found</div>;

  return (
    <div>
      <Link to="/extensions" style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "var(--color-hermes-accent-blue)", textDecoration: "none", fontSize: 13, marginBottom: 16 }}>
        <ArrowLeft size={14} /> Back to Extensions
      </Link>

      <div className="page-header">
        <h1>{ext.name}</h1>
        <p>{ext.description}</p>
      </div>

      {/* Info Cards */}
      <div className="card-grid" style={{ marginBottom: 24 }}>
        <div className="stat-card" style={{ padding: "12px" }}>
          <div className="label">Path</div>
          <div className="value" style={{ fontSize: 13, fontFamily: "var(--font-mono)", wordBreak: "break-all" }}>{ext.path}</div>
        </div>
        <div className="stat-card" style={{ padding: "12px" }}>
          <div className="label">Size</div>
          <div className="value" style={{ fontSize: 16 }}>
            {ext.size_bytes > 1024 * 1024
              ? `${(ext.size_bytes / 1024 / 1024).toFixed(2)} MB`
              : ext.size_bytes > 1024
              ? `${(ext.size_bytes / 1024).toFixed(1)} KB`
              : `${ext.size_bytes} B`}
          </div>
        </div>
        <div className="stat-card" style={{ padding: "12px" }}>
          <div className="label">Last Modified</div>
          <div className="value" style={{ fontSize: 14 }}>{ext.modified_at ? new Date(ext.modified_at).toLocaleString() : "—"}</div>
        </div>
        <div className="stat-card" style={{ padding: "12px" }}>
          <div className="label">Files</div>
          <div className="value" style={{ fontSize: 14 }}>{ext.files?.length || 0}</div>
        </div>
      </div>

      {/* SKILL.md Preview */}
      {ext.skill_excerpt && (
        <div className="card" style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 8px", display: "flex", alignItems: "center", gap: 6 }}>
            <FileText size={14} /> SKILL.md
          </h3>
          <pre style={{
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            margin: 0,
            color: "var(--color-hermes-text-secondary)",
            maxHeight: 300,
            overflow: "auto",
            lineHeight: 1.5,
          }}>
            {ext.skill_excerpt}
          </pre>
        </div>
      )}

      {/* Files List */}
      <div className="card">
        <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 8px", display: "flex", alignItems: "center", gap: 6 }}>
          <File size={14} /> Files
        </h3>
        {ext.files?.map((f: string) => (
          <div key={f} style={{ fontSize: 13, fontFamily: "var(--font-mono)", color: "var(--color-hermes-text-secondary)", padding: "4px 0" }}>
            📄 {f}
          </div>
        ))}
      </div>
    </div>
  );
}
