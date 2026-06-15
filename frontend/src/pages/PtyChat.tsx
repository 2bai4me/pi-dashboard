import { useState, useRef, useEffect } from "react";
import { Terminal as TerminalIcon, Send, Square } from "lucide-react";
import { getToken } from "../api";

export default function PtyChat() {
  const [connected, setConnected] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  function connect() {
    const token = getToken();
    if (!token) return;

    const ws = new WebSocket(`ws://127.0.0.1:9219/api/pty?token=${token}&id=${activeTerminal}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setLogs((prev) => [...prev, "=== CONNECTED ===\n"]);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "output" || msg.type === "info") {
          setLogs((prev) => [...prev, msg.text]);
        } else if (msg.type === "error") {
          setLogs((prev) => [...prev, `ERROR: ${msg.text}\n`]);
        } else if (msg.type === "exit") {
          setLogs((prev) => [...prev, `\n=== EXIT (code ${msg.code}) ===\n`]);
          setConnected(false);
        }
      } catch {
        setLogs((prev) => [...prev, event.data + "\n"]);
      }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
    };

    ws.onerror = () => {
      setLogs((prev) => [...prev, "=== WEBSOCKET ERROR ===\n"]);
    };
  }

  function disconnect() {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
      setConnected(false);
    }
  }

  function sendInput() {
    if (!wsRef.current || !input.trim()) return;
    wsRef.current.send(JSON.stringify({ type: "input", text: input + "\n" }));
    setLogs((prev) => [...prev, `> ${input}\n`]);
    setInput("");
  }

  function sendCtrlC() {
    if (!wsRef.current) return;
    wsRef.current.send(JSON.stringify({ type: "sigint" }));
    setLogs((prev) => [...prev, "^C\n"]);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 48px)" }}>
      <div className="page-header" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <TerminalIcon size={20} color="var(--color-hermes-accent-green)" />
            PTY Terminal
          </h1>
          <p>Interactive PI Agent terminal (WebSocket)</p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className={`badge ${connected ? "badge-green" : "badge-orange"}`}>
            {connected ? "Connected" : "Disconnected"}
          </span>
          {connected ? (
            <button className="btn btn-danger" onClick={disconnect}>
              <Square size={14} /> Disconnect
            </button>
          ) : (
            <button className="btn btn-primary" onClick={connect}>
              <TerminalIcon size={14} /> Connect
            </button>
          )}
        </div>
      </div>

      {/* Terminal Output */}
      <div
        ref={scrollRef}
        className="card"
        style={{
          flex: 1,
          overflow: "auto",
          fontFamily: "var(--font-mono)",
          fontSize: 12,
          lineHeight: 1.5,
          padding: 8,
          marginBottom: 8,
          background: "#0a0e14",
          color: "#e6edf3",
        }}
      >
        {logs.length === 0 && !connected && (
          <div style={{ color: "#8b949e", padding: 20, textAlign: "center" }}>
            Click "Connect" to start an interactive PI session<br />
            <small>(WebSocket to ws://127.0.0.1:9219/api/pty)</small>
          </div>
        )}
        {logs.map((line, i) => (
          <div key={i} style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
            {line}
          </div>
        ))}
      </div>

      {/* Input */}
      <div style={{ display: "flex", gap: 8 }}>
        <input
          className="input"
          style={{ fontFamily: "var(--font-mono)" }}
          placeholder={connected ? "Type command..." : "Connect to start"}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendInput(); }
            if (e.key === "c" && e.ctrlKey) { e.preventDefault(); sendCtrlC(); }
          }}
          disabled={!connected}
          autoFocus
        />
        <button className="btn" onClick={sendCtrlC} disabled={!connected} title="Ctrl+C">
          ^C
        </button>
        <button className="btn btn-primary" onClick={sendInput} disabled={!connected || !input.trim()}>
          <Send size={14} /> Send
        </button>
      </div>
    </div>
  );
}
