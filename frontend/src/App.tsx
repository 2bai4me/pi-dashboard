import { HashRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect } from "react";
import { getToken, setToken } from "./api";
import { Layout } from "./Layout";
import Login from "./pages/Login";

const queryClient = new QueryClient();
import Status from "./pages/Status";
import Sessions from "./pages/Sessions";
import SessionDetail from "./pages/SessionDetail";
import Config from "./pages/Config";
import Models from "./pages/Models";
import Tools from "./pages/Tools";
import Skills from "./pages/Skills";
import Extensions from "./pages/Extensions";
import ExtensionDetail from "./pages/ExtensionDetail";
import Cost from "./pages/Cost";
import Logs from "./pages/Logs";
import OpenBrain from "./pages/OpenBrain";
import OpenBrainGraph from "./pages/OpenBrainGraph";
import Chat from "./pages/Chat";
import CronJobs from "./pages/CronJobs";
import McpServers from "./pages/McpServers";
import Webhooks from "./pages/Webhooks";
import ApiKeys from "./pages/ApiKeys";
import Roles from "./pages/Roles";
import Kanban from "./pages/Kanban";
import SelfImprovement from "./pages/SelfImprovement";
import PtyChat from "./pages/PtyChat";
import UserAdmin from "./pages/UserAdmin";
import { TTSProvider } from "./TTSContext";
import SopView from "./pages/SopView";
import SysInfo from "./pages/SysInfo";

function Protected({ children }: { children: React.ReactNode }) {
  // Ohne Token: trotzdem anzeigen (Auth ist optional)
  return <>{children}</>;
}

export default function App() {
  // Automatischer Login beim Start
  useEffect(() => {
    if (!getToken()) {
      fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: "admin", password: "admin" }),
      })
        .then((r) => r.json())
        .then((d) => d.token && setToken(d.token))
        .catch(() => {});
    }
  }, []);
  return (
    <TTSProvider>
      <QueryClientProvider client={queryClient}>
        <HashRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/*"
              element={
                <Protected>
                  <AppRoutes />
                </Protected>
              }
            />
          </Routes>
        </HashRouter>
      </QueryClientProvider>
    </TTSProvider>
  );
}

function AppRoutes() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Status />} />
        <Route path="/sessions" element={<Sessions />} />
        <Route path="/sessions/:id" element={<SessionDetail />} />
        <Route path="/config" element={<Config />} />
        <Route path="/models" element={<Models />} />
        <Route path="/tools" element={<Tools />} />
        <Route path="/skills" element={<Skills />} />
        <Route path="/extensions" element={<Extensions />} />
        <Route path="/extensions/:name" element={<ExtensionDetail />} />
        <Route path="/cost" element={<Cost />} />
        <Route path="/logs" element={<Logs />} />
        <Route path="/openbrain" element={<OpenBrain />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/cron" element={<CronJobs />} />
        <Route path="/mcp" element={<McpServers />} />
        <Route path="/webhooks" element={<Webhooks />} />
        <Route path="/apikeys" element={<ApiKeys />} />
        <Route path="/roles" element={<Roles />} />
        <Route path="/openbrain/graph" element={<OpenBrainGraph />} />
        <Route path="/kanban" element={<Kanban />} />
        <Route path="/selfimprovement" element={<SelfImprovement />} />
        <Route path="/chat-pty" element={<PtyChat />} />
        <Route path="/users" element={<UserAdmin />} />
        <Route path="/system" element={<SysInfo />} />
        <Route path="/sop" element={<SopView />} />
      </Routes>
    </Layout>
  );
}
