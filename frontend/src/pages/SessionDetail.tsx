import { useQuery } from "@tanstack/react-query";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { api } from "../api";

export default function SessionDetail() {
  const { id } = useParams<{ id: string }>();

  const { data: session, isLoading: loadingS } = useQuery({
    queryKey: ["session", id],
    queryFn: () => api.getSession(id!),
    enabled: !!id,
  });

  const { data: messages, isLoading: loadingM } = useQuery({
    queryKey: ["session-msgs", id],
    queryFn: () => api.getSessionMessages(id!, 500),
    enabled: !!id,
  });

  if (loadingS || loadingM) {
    return <div style={{ color: "var(--color-hermes-text-secondary)" }}>Loading...</div>;
  }

  return (
    <div>
      <Link to="/sessions" style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "var(--color-hermes-accent-blue)", textDecoration: "none", fontSize: 13, marginBottom: 16 }}>
        <ArrowLeft size={14} /> Back to Sessions
      </Link>

      <div className="page-header">
        <h1 style={{ fontFamily: "var(--font-mono)", fontSize: 16 }}>{session?.name || id?.slice(0, 16)}</h1>
        <p style={{ fontSize: 12 }}>
          {session?.message_count || 0} messages · {session?.model ? `Model: ${session.model}` : ""} · {session?.size_bytes ? `${(session.size_bytes / 1024).toFixed(1)} KB` : ""}
        </p>
      </div>

      {messages?.length === 0 ? (
        <div style={{ color: "var(--color-hermes-text-secondary)", padding: 40, textAlign: "center" }}>No messages</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {(messages || []).map((msg: any, i: number) => (
            <div
              key={i}
              className="card"
              style={{
                padding: "12px 16px",
                borderLeft: msg.role === "user"
                  ? "3px solid var(--color-hermes-accent-blue)"
                  : msg.role === "assistant"
                  ? "3px solid var(--color-hermes-accent)"
                  : "3px solid var(--color-hermes-text-secondary)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <span className={`badge ${
                  msg.role === "user" ? "badge-blue" :
                  msg.role === "assistant" ? "badge-green" : "badge-orange"
                }`}>
                  {msg.role}
                </span>
                {msg.timestamp && (
                  <span style={{ fontSize: 11, color: "var(--color-hermes-text-secondary)" }}>
                    {new Date(msg.timestamp).toLocaleString()}
                  </span>
                )}
              </div>
              <pre style={{
                fontFamily: "var(--font-mono)",
                fontSize: 12,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                margin: 0,
                color: "var(--color-hermes-text)",
                lineHeight: 1.5,
                maxHeight: 200,
                overflow: "auto",
              }}>
                {msg.content || "(no content)"}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
