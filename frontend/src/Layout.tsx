import { NavLink, useNavigate } from "react-router-dom";
import {
  Activity,
  BookOpen,
  Brain,
  ChevronDown,
  ChevronRight,
  Cpu,
  DollarSign,
  FileText,
  Key,
  LayoutDashboard,
  LogOut,
  MessagesSquare,
  Network,
  Puzzle,
  Server,
  Settings2,
  Shield,
  Terminal,
  TrendingUp,
  Users,
  Wrench,
} from "lucide-react";
import { setToken } from "./api";
import GatewayStatusBar from "./GatewayStatusBar";
import { useState } from "react";
import { useTTSContext } from "./TTSContext";

const NAV_ITEMS = [
  { section: "Overview", items: [
    { to: "/", label: "Status", icon: LayoutDashboard },
    { to: "/system", label: "System", icon: Server },
    { to: "/kanban", label: "Projekte", icon: LayoutDashboard },
  ]},
  { section: "Agent", items: [
    { to: "/sessions", label: "Sessions", icon: MessagesSquare },
    { to: "/chat-pty", label: "Terminal", icon: Terminal },
    { to: "/models", label: "Models", icon: Cpu },
    { to: "/tools", label: "Tools", icon: Wrench },
    { to: "/skills", label: "Skills", icon: BookOpen },
    { to: "/roles", label: "Rollen", icon: Shield },
  ]},
  { section: "Management", items: [
    { to: "/sop", label: "SOP Prozesse", icon: Activity },
    { to: "/config", label: "Config", icon: Settings2 },
    { to: "/cron", label: "Cron Jobs", icon: Activity },
    { to: "/mcp", label: "MCP", icon: Wrench },
    { to: "/extensions", label: "Extensions", icon: Puzzle },
    { to: "/cost", label: "Cost & Usage", icon: DollarSign },
    { to: "/logs", label: "Logs", icon: FileText },
    { to: "/webhooks", label: "Webhooks", icon: MessagesSquare },
  ]},
  { section: "Growth", items: [
    { to: "/selfimprovement", label: "Self-Improve", icon: TrendingUp },
  ]},
  { section: "Integrations", items: [
    { to: "/users", label: "Users", icon: Users },
    { to: "/apikeys", label: "API Keys", icon: Key },
    { to: "/openbrain", label: "OpenBrain", icon: Brain },
    { to: "/openbrain/graph", label: "Brain Graph", icon: Network },
  ]},
];

export function Layout({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const tts = useTTSContext();

  function toggleSection(section: string) {
    setCollapsed((prev) => ({ ...prev, [section]: !prev[section] }));
  }

  function handleLogout() {
    setToken(null);
    navigate("/login");
  }

  return (
    <div className="dashboard-layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <Cpu size={18} className="text-hermes-accent-blue" />
          <span>Pi Dashboard</span>
        </div>

        <nav className="sidebar-nav">
          {NAV_ITEMS.map((section) => {
            const isCollapsed = collapsed[section.section];
            return (
              <div key={section.section}>
                <div
                  className="sidebar-section-title"
                  onClick={() => toggleSection(section.section)}
                  style={{ cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", userSelect: "none" }}
                >
                  <span>{section.section}</span>
                  {isCollapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
                </div>
                {!isCollapsed && section.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === "/"}
                    className={({ isActive }) =>
                      `sidebar-link${isActive ? " active" : ""}`
                    }
                  >
                    <item.icon size={16} />
                    {item.label}
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>

        <div style={{ flex: 1 }} />

        <div style={{ padding: "8px", borderTop: "1px solid var(--color-hermes-border)" }}>
          <button className="sidebar-link" style={{ width: "100%", border: "none", background: "none", cursor: "pointer" }} onClick={handleLogout}>
            <LogOut size={16} />
            Logout
          </button>
        </div>
      </aside>

      <main className="main-content" style={{ padding: 0 }}>
        <GatewayStatusBar />
        <div style={{ padding: 24 }}>
          {children}
        </div>
      </main>

      {/* Floating TTS Stop Button */}
      {tts.speaking && (
        <div style={{
          position: "fixed", bottom: 24, right: 24, zIndex: 9999,
          background: "var(--color-hermes-danger)", color: "#fff",
          padding: "10px 18px", borderRadius: 30, cursor: "pointer",
          boxShadow: "0 4px 12px rgba(248,81,73,0.4)",
          display: "flex", alignItems: "center", gap: 8,
          fontSize: 14, fontWeight: 600,
          border: "none",
        }}
          onClick={tts.stop}
        >
          ⏹ Vorlesen stoppen
        </div>
      )}
    </div>
  );
}
