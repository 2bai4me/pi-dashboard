import { useState, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Network, Search, ZoomIn, ZoomOut, Maximize } from "lucide-react";
import { api } from "../api";

export default function OpenBrainGraph() {
  const [search, setSearch] = useState("");
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const dragRef = useRef<{ active: boolean; startX: number; startY: number; ox: number; oy: number }>({
    active: false, startX: 0, startY: 0, ox: 0, oy: 0,
  });
  const simRef = useRef<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] });

  const { data: graphData, isLoading } = useQuery({
    queryKey: ["openbrain-graph"],
    queryFn: () => api.get("/openbrain/graph"),
    refetchInterval: 30000,
  });

  const { data: stats } = useQuery({
    queryKey: ["openbrain-stats"],
    queryFn: () => api.get("/openbrain/stats"),
  });

  // Initialize simulation and draw
  useEffect(() => {
    if (!graphData || !canvasRef.current) return;

    const { nodes, edges } = graphData;
    if (!nodes?.length) return;

    simRef.current = { nodes, edges };

    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Resize canvas
    const rect = canvas.parentElement!.getBoundingClientRect();
    canvas.width = rect.width * 2;
    canvas.height = rect.height * 2;
    canvas.style.width = rect.width + "px";
    canvas.style.height = rect.height + "px";
    ctx.scale(2, 2);

    // Simple force simulation positions
    const w = rect.width;
    const h = rect.height;
    const centerX = w / 2;
    const centerY = h / 2;

    // Position nodes in a circle with variations
    nodes.forEach((n: any, i: number) => {
      const angle = (2 * Math.PI * i) / nodes.length;
      const radius = Math.min(w, h) * 0.35;
      n.x = centerX + radius * Math.cos(angle) + (Math.random() - 0.5) * 80;
      n.y = centerY + radius * Math.sin(angle) + (Math.random() - 0.5) * 80;
      n.r = 12 + (n.tags?.length || 0) * 3;
    });

    drawGraph(ctx, nodes, edges, zoom, offset.x, offset.y, selectedNode);

    // Animation loop for simple physics
    let animId: number;
    let frame = 0;

    function animate() {
      if (!simRef.current.nodes.length) return;
      frame++;

      // Simple spring forces toward center + repulsion
      const repulsionStrength = 3000;
      const centerStrength = 0.01;
      const damping = 0.85;

      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];

        // Center attraction
        a.vx = (a.vx || 0) - (a.x - centerX) * centerStrength;
        a.vy = (a.vy || 0) - (a.y - centerY) * centerStrength;

        // Repulsion between nodes
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = repulsionStrength / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          a.vx = (a.vx || 0) + fx;
          a.vy = (a.vy || 0) + fy;
          b.vx = (b.vx || 0) - fx;
          b.vy = (b.vy || 0) - fy;
        }

        // Edge attraction (springs)
        for (const edge of edges) {
          const target = edge.target === a.id || edge.source === a.id;
          if (!target) continue;
          const otherId = edge.target === a.id ? edge.source : edge.target;
          const other = nodes.find((n: any) => n.id === otherId);
          if (!other) continue;
          const dx = other.x - a.x;
          const dy = other.y - a.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const spring = (dist - 100) * 0.005;
          a.vx = (a.vx || 0) + (dx / dist) * spring;
          a.vy = (a.vy || 0) + (dy / dist) * spring;
        }

        // Damping and move
        a.vx = (a.vx || 0) * damping;
        a.vy = (a.vy || 0) * damping;
        a.x += a.vx;
        a.y += a.vy;

        // Keep in bounds
        a.x = Math.max(30, Math.min(w - 30, a.x));
        a.y = Math.max(30, Math.min(h - 30, a.y));
      }

      drawGraph(ctx, nodes, edges, zoom, offset.x, offset.y, selectedNode);

      if (frame < 200) {
        animId = requestAnimationFrame(animate);
      }
    }

    animate();

    return () => {
      if (animId) cancelAnimationFrame(animId);
      simRef.current = { nodes: [], edges: [] };
    };
  }, [graphData, zoom, offset, selectedNode]);

  // Handle canvas click
  function handleCanvasClick(e: React.MouseEvent<HTMLCanvasElement>) {
    if (!simRef.current.nodes.length) return;
    const rect = canvasRef.current!.getBoundingClientRect();
    const mx = (e.clientX - rect.left) / zoom - offset.x;
    const my = (e.clientY - rect.top) / zoom - offset.y;

    for (const n of simRef.current.nodes) {
      const dx = mx - n.x;
      const dy = my - n.y;
      if (dx * dx + dy * dy < (n.r + 5) * (n.r + 5)) {
        setSelectedNode(n);
        return;
      }
    }
    setSelectedNode(null);
  }

  function handleWheel(e: React.WheelEvent) {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setZoom((z) => Math.max(0.3, Math.min(3, z * delta)));
  }

  const typeColors: Record<string, string> = {
    project: "#2ea043", architecture: "#58a6ff", decision: "#d29922",
    code: "#a371f7", bug: "#f85149", observation: "#8b949e",
    feature: "#2ea043", idea: "#d29922", reference: "#58a6ff",
  };

  // Filter nodes by search
  const filteredNodes = search
    ? (graphData?.nodes || []).filter((n: any) =>
        (n.label || "").toLowerCase().includes(search.toLowerCase()) ||
        (n.fullText || "").toLowerCase().includes(search.toLowerCase()) ||
        (n.tags || []).some((t: string) => t.toLowerCase().includes(search.toLowerCase()))
      )
    : graphData?.nodes || [];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 48px)" }}>
      <div className="page-header" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Network size={20} color="var(--color-hermes-accent-blue)" />
            OpenBrain Graph
          </h1>
          <p>TheBrain-ähnliche Graph-Ansicht aller gespeicherten Gedanken</p>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="btn" style={{ padding: "4px 8px" }} onClick={() => setZoom((z) => z * 1.3)} title="Zoom in">
            <ZoomIn size={14} />
          </button>
          <button className="btn" style={{ padding: "4px 8px" }} onClick={() => setZoom((z) => z / 1.3)} title="Zoom out">
            <ZoomOut size={14} />
          </button>
          <button className="btn" style={{ padding: "4px 8px" }} onClick={() => { setZoom(1); setOffset({ x: 0, y: 0 }); }} title="Reset">
            <Maximize size={14} />
          </button>
        </div>
      </div>

      {/* Stats + Search */}
      <div style={{ display: "flex", gap: 12, marginBottom: 12, alignItems: "center" }}>
        <div className="stat-card" style={{ padding: "8px 12px", flexDirection: "row", gap: 8, alignItems: "center" }}>
          <div className="label">Nodes</div>
          <div style={{ fontSize: 16, fontWeight: 600 }}>
            {isLoading ? "?" : graphData?.nodes?.length || 0}
          </div>
        </div>
        <div className="stat-card" style={{ padding: "8px 12px", flexDirection: "row", gap: 8, alignItems: "center" }}>
          <div className="label">Edges</div>
          <div style={{ fontSize: 16, fontWeight: 600 }}>
            {graphData?.edges?.length || 0}
          </div>
        </div>
        <div style={{ position: "relative", flex: 1 }}>
          <Search size={14} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--color-hermes-text-secondary)" }} />
          <input className="input" style={{ paddingLeft: 32 }} placeholder="Search thoughts..." value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
      </div>

      {/* Graph + Side Panel */}
      <div style={{ display: "flex", gap: 12, flex: 1, minHeight: 0 }}>
        {/* Canvas */}
        <div ref={containerRef} className="card" style={{ flex: 1, position: "relative", overflow: "hidden", padding: 0 }}>
          {isLoading ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--color-hermes-text-secondary)" }}>
              Loading graph...
            </div>
          ) : (
            <canvas
              ref={canvasRef}
              style={{ cursor: "pointer", width: "100%", height: "100%" }}
              onClick={handleCanvasClick}
              onWheel={handleWheel}
            />
          )}
        </div>

        {/* Detail Panel */}
        <div className="card" style={{ width: 300, minWidth: 300, overflow: "auto" }}>
          {selectedNode ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <h3 style={{ fontSize: 14, fontWeight: 600, margin: 0 }}>{selectedNode.label}</h3>
              <div className="badge" style={{ background: `${selectedNode.color}22`, color: selectedNode.color }}>
                {selectedNode.type}
              </div>
              <details open>
                <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 500, color: "var(--color-hermes-accent-blue)" }}>
                  Full Text
                </summary>
                <pre style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 11,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  margin: "8px 0 0",
                  color: "var(--color-hermes-text)",
                  lineHeight: 1.4,
                  background: "var(--color-hermes-muted)",
                  padding: 8,
                  borderRadius: 4,
                }}>
                  {selectedNode.fullText}
                </pre>
              </details>
              {selectedNode.tags?.length > 0 && (
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4, color: "var(--color-hermes-text-secondary)" }}>
                    Tags
                  </div>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    {selectedNode.tags.map((t: string) => (
                      <span key={t} className="badge badge-orange">{t}</span>
                    ))}
                  </div>
                </div>
              )}
              <button className="btn" style={{ padding: "4px 8px", alignSelf: "flex-start" }} onClick={() => {
                setSelectedNode(null);
                setSearch(selectedNode.tags?.[0] || "");
              }}>
                Search similar
              </button>
            </div>
          ) : (
            <div style={{ textAlign: "center", color: "var(--color-hermes-text-secondary)", padding: 20 }}>
              <Network size={24} style={{ marginBottom: 8, opacity: 0.3 }} />
              <p style={{ fontSize: 13, margin: 0 }}>Click a node to see details</p>
              <p style={{ fontSize: 11, margin: "4px 0 0" }}>
                {search ? `${filteredNodes.length} matching nodes` : "All thoughts displayed"}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Graph Drawing Helper ──────────────────────────────────────────

function drawGraph(
  ctx: CanvasRenderingContext2D,
  nodes: any[],
  edges: any[],
  zoom: number,
  ox: number,
  oy: number,
  selected: any | null
) {
  const w = ctx.canvas.width / 2;
  const h = ctx.canvas.height / 2;

  ctx.clearRect(0, 0, w, h);

  // Background
  ctx.fillStyle = "#0e1217";
  ctx.fillRect(0, 0, w, h);

  ctx.save();
  ctx.translate(ox, oy);
  ctx.scale(zoom, zoom);

  // Edges
  for (const edge of edges) {
    const source = nodes.find((n: any) => n.id === edge.source);
    const target = nodes.find((n: any) => n.id === edge.target);
    if (!source || !target) continue;

    ctx.beginPath();
    ctx.moveTo(source.x, source.y);
    ctx.lineTo(target.x, target.y);
    ctx.strokeStyle = "rgba(139, 148, 158, 0.3)";
    ctx.lineWidth = 1;
    ctx.stroke();

    // Edge label
    const mx = (source.x + target.x) / 2;
    const my = (source.y + target.y) / 2;
    ctx.fillStyle = "rgba(139, 148, 158, 0.5)";
    ctx.font = "8px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(edge.label, mx, my - 4);
  }

  // Nodes
  for (const node of nodes) {
    const isSelected = selected?.id === node.id;
    const radius = node.r || 15;

    // Shadow for selected
    if (isSelected) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius + 4, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(88, 166, 255, 0.3)";
      ctx.fill();
    }

    // Circle
    ctx.beginPath();
    ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
    ctx.fillStyle = node.color || "#8b949e";
    ctx.fill();
    ctx.strokeStyle = isSelected ? "#fff" : "rgba(255,255,255,0.2)";
    ctx.lineWidth = isSelected ? 2.5 : 1;
    ctx.stroke();

    // Label
    ctx.fillStyle = "#e6edf3";
    ctx.font = `${isSelected ? "bold " : ""}9px Inter, sans-serif`;
    ctx.textAlign = "center";
    ctx.fillText(node.label, node.x, node.y + radius + 12);

    // Type icon
    ctx.fillStyle = "rgba(255,255,255,0.5)";
    ctx.font = "8px sans-serif";
    ctx.fillText(node.type, node.x, node.y + radius + 22);
  }

  ctx.restore();
}
