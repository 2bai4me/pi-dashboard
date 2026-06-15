import { useState, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Play, Square } from "lucide-react";
import { api, createLogStream } from "../api";

export default function Logs() {
  const [source, setSource] = useState("all");
  const [live, setLive] = useState(false);
  const [streamLogs, setStreamLogs] = useState<any[]>([]);
  const stopRef = useRef<(() => void) | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { data: recent, isLoading, refetch } = useQuery({
    queryKey: ["logs", source],
    queryFn: () => api.recentLogs(200, source),
  });

  useEffect(() => {
    if (live) {
      stopRef.current = createLogStream(2, source, (entry) => {
        setStreamLogs((prev) => [entry, ...prev].slice(0, 100));
      });
    } else {
      if (stopRef.current) {
        stopRef.current();
        stopRef.current = null;
      }
    }
    return () => {
      if (stopRef.current) stopRef.current();
    };
  }, [live, source]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = 0;
    }
  }, [streamLogs, recent]);

  const displayLogs = live ? streamLogs : recent || [];

  return (
    <div>
      <div className="page-header" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h1>Logs</h1>
          <p>PI Agent log entries from sessions and extensions</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <select className="input" style={{ width: "auto" }} value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="all">All Sources</option>
            <option value="sessions">Sessions</option>
            <option value="extensions">Extensions</option>
          </select>
          {live ? (
            <button className="btn btn-danger" onClick={() => setLive(false)}>
              <Square size={14} /> Stop
            </button>
          ) : (
            <button className="btn" onClick={() => setLive(true)}>
              <Play size={14} /> Live Tail
            </button>
          )}
        </div>
      </div>

      {isLoading && !live ? (
        <div style={{ color: "var(--color-hermes-text-secondary)" }}>Loading...</div>
      ) : displayLogs.length === 0 ? (
        <div style={{ color: "var(--color-hermes-text-secondary)", padding: 40, textAlign: "center" }}>
          No log entries found
        </div>
      ) : (
        <div
          ref={scrollRef}
          className="card"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            maxHeight: "calc(100vh - 200px)",
            overflow: "auto",
            padding: 8,
          }}
        >
          {displayLogs.map((entry: any, i: number) => (
            <div
              key={i}
              style={{
                padding: "2px 4px",
                display: "flex",
                gap: 8,
                borderBottom: "1px solid rgba(48,54,61,0.3)",
                lineHeight: 1.6,
              }}
            >
              {entry.source === "session" && (
                <span style={{ color: "var(--color-hermes-accent-blue)", minWidth: 80 }}>
                  {entry.role || "?"}
                </span>
              )}
              {entry.source === "extension" && (
                <span style={{ color: "var(--color-hermes-accent-orange)", minWidth: 80 }}>
                  {entry.extension || "ext"}
                </span>
              )}
              <span style={{ color: "var(--color-hermes-text-secondary)", minWidth: 50 }}>
                {entry.source}
              </span>
              <span style={{ color: "var(--color-hermes-text)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {entry.text || entry.raw || JSON.stringify(entry).slice(0, 200)}
              </span>
              {entry.ts && (
                <span style={{ color: "var(--color-hermes-text-secondary)", minWidth: 60, textAlign: "right" }}>
                  {typeof entry.ts === "number"
                    ? new Date(entry.ts * 1000).toLocaleTimeString()
                    : typeof entry.ts === "string"
                    ? new Date(entry.ts).toLocaleTimeString()
                    : ""}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
