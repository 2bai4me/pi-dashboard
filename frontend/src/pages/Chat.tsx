import { useState, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Send, Terminal, MessageSquare } from "lucide-react";
import { api, getToken } from "../api";

export default function Chat() {
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([
    { role: "system", text: "Welcome to Pi Chat. Type a prompt to start a conversation with the agent." },
  ]);
  const [streaming, setStreaming] = useState(false);
  const [model, setModel] = useState("");
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const { data: sessions } = useQuery({
    queryKey: ["chat-sessions"],
    queryFn: () => api.get("/chat/sessions"),
  });

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  async function handleSubmit(e?: React.FormEvent) {
    e?.preventDefault();
    if (!prompt.trim() || streaming) return;

    const userMsg = prompt.trim();
    setPrompt("");
    setMessages((prev) => [...prev, { role: "user", text: userMsg }]);
    setStreaming(true);

    const abort = new AbortController();
    abortRef.current = abort;

    try {
      const token = getToken();
      const resp = await fetch("/api/chat/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          prompt: userMsg,
          model: model || undefined,
          session_id: activeSession || undefined,
        }),
        signal: abort.signal,
      });

      const reader = resp.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let assistantText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value, { stream: true });
        for (const line of text.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === "response" && data.text) {
              assistantText += data.text + "\n";
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                if (last?.role === "assistant") {
                  return [...prev.slice(0, -1), { role: "assistant", text: last.text + data.text + "\n" }];
                }
                return [...prev, { role: "assistant", text: data.text }];
              });
            } else if (data.type === "error") {
              setMessages((prev) => [...prev, { role: "system", text: `Error: ${data.text}` }]);
            }
          } catch {}
        }
      }
    } catch (err: any) {
      if (err.name !== "AbortError") {
        setMessages((prev) => [...prev, { role: "system", text: `Request failed: ${err.message}` }]);
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  function handleCancel() {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
      setStreaming(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 48px)" }}>
      <div className="page-header">
        <h1 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Terminal size={20} color="var(--color-hermes-accent-blue)" />
          Chat
        </h1>
        <p>Talk to the PI Agent — streaming responses</p>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <select className="input" style={{ width: "auto" }} value={model} onChange={(e) => setModel(e.target.value)}>
          <option value="">Default model</option>
          {sessions?.slice(0, 5).map((s: any) => (
            s.model ? <option key={s.model} value={s.model}>{s.model.split("/").pop()}</option> : null
          ))}
        </select>
        <select className="input" style={{ width: "auto" }} value={activeSession || ""} onChange={(e) => setActiveSession(e.target.value || null)}>
          <option value="">New session</option>
          {(sessions || []).slice(0, 10).map((s: any) => (
            <option key={s.id} value={s.id}>{(s.name || s.id).slice(0, 30)}</option>
          ))}
        </select>
      </div>

      {/* Messages */}
      <div
        ref={scrollRef}
        className="card"
        style={{
          flex: 1,
          overflow: "auto",
          marginBottom: 12,
          display: "flex",
          flexDirection: "column",
          gap: 8,
          padding: 12,
        }}
      >
        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              padding: "8px 12px",
              borderRadius: 8,
              background:
                msg.role === "user"
                  ? "rgba(88,166,255,0.08)"
                  : msg.role === "assistant"
                  ? "rgba(46,160,67,0.08)"
                  : "rgba(210,153,34,0.08)",
              borderLeft: `3px solid ${
                msg.role === "user"
                  ? "var(--color-hermes-accent-blue)"
                  : msg.role === "assistant"
                  ? "var(--color-hermes-accent)"
                  : "var(--color-hermes-accent-orange)"
              }`,
            }}
          >
            <div style={{ fontSize: 11, marginBottom: 4, color: "var(--color-hermes-text-secondary)" }}>
              {msg.role.toUpperCase()}
            </div>
            <pre style={{
              fontFamily: "var(--font-mono)",
              fontSize: 13,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              margin: 0,
              color: "var(--color-hermes-text)",
              lineHeight: 1.5,
              maxHeight: streaming && msg.role === "assistant" ? "none" : 500,
              overflow: streaming && msg.role === "assistant" ? "visible" : "auto",
            }}>
              {msg.text}
            </pre>
          </div>
        ))}
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} style={{ display: "flex", gap: 8 }}>
        <input
          className="input"
          placeholder="Type your prompt..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          disabled={streaming}
          autoFocus
        />
        {streaming ? (
          <button type="button" className="btn btn-danger" onClick={handleCancel}>
            Stop
          </button>
        ) : (
          <button type="submit" className="btn btn-primary" disabled={!prompt.trim()}>
            <Send size={14} /> Send
          </button>
        )}
      </form>
    </div>
  );
}
