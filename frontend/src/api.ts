const API_BASE = "/api";

let authToken: string | null = localStorage.getItem("pi-dash-token");

export function setToken(token: string | null) {
  authToken = token;
  if (token) localStorage.setItem("pi-dash-token", token);
  else localStorage.removeItem("pi-dash-token");
}

export function getToken() {
  return authToken;
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const headers: Record<string, string> = {};
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) {
    setToken(null);
    console.warn("401 received — auth might be disabled, continuing without token");
    throw new Error("Session expired");
  }

  if (!res.ok) {
    const err = await res.text().catch(() => "Unknown error");
    throw new Error(`${res.status}: ${err.slice(0, 200)}`);
  }

  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),

  // Auth
  login: (username: string, password: string) =>
    request<{ token: string; user: string }>("POST", "/auth/login", {
      username,
      password,
    }),

  // Overview
  getStatus: () => request<any>("GET", "/overview/status"),
  getSystemStats: () => request<any>("GET", "/overview/system"),
  getExtensions: () => request<any>("GET", "/overview/extensions"),
  getPiVersion: () => request<any>("GET", "/overview/version"),

  // Sessions
  listSessions: (limit = 50, sort = "modified") =>
    request<any[]>("GET", `/sessions?limit=${limit}&sort=${sort}`),
  getSession: (id: string) => request<any>("GET", `/sessions/${id}`),
  getSessionMessages: (id: string, limit = 500, offset = 0) =>
    request<any[]>("GET", `/sessions/${id}/messages?limit=${limit}&offset=${offset}`),
  searchSessions: (q: string, limit = 20) =>
    request<any[]>("GET", `/sessions/search/query?q=${encodeURIComponent(q)}&limit=${limit}`),
  deleteSession: (id: string) => request<any>("DELETE", `/sessions/${id}`),
  sessionStats: () => request<any>("GET", "/sessions/stats/summary"),

  // Config
  getSettings: () => request<any>("GET", "/config/settings"),
  putSettings: (data: any) => request<any>("PUT", "/config/settings", data),
  getModelsConfig: () => request<any>("GET", "/config/models"),
  putModelsConfig: (data: any) => request<any>("PUT", "/config/models", data),

  // Models
  listModels: () => request<any[]>("GET", "/models"),
  listProviders: () => request<any[]>("GET", "/models/providers"),
  setDefaultModel: (modelId: string) =>
    request<any>("POST", "/models/default", { model_id: modelId }),
  toggleModel: (modelId: string) =>
    request<any>("POST", "/models/toggle", { model_id: modelId }),
  // Provider-Management
  addProvider: (data: any) => request<any>("POST", "/models/providers", data),
  updateProvider: (name: string, data: any) => request<any>("PUT", `/models/providers/${name}`, data),
  deleteProvider: (name: string) => request<any>("DELETE", `/models/providers/${name}`),
  testProvider: (name: string) => request<any>("POST", `/models/providers/${name}/test`),
  quickSwitchProvider: (target: string) => request<any>("POST", "/models/quick-switch", { target }),

  // === Pricing-Management (15.06.2026, Task 1d45c65b853b Erweiterung) ===
  getPricing: () => request<any>("GET", "/models/pricing"),
  refreshPricing: () => request<any>("POST", "/models/pricing/refresh"),
  updatePricing: (data: { provider: string; model_id?: string; input_per_1m: number; output_per_1m: number; note?: string }) =>
    request<any>("POST", "/models/pricing/update", data),

  // === Task Token-Usage (Sub-Agent -> Backend) ===
  reportTaskUsage: (taskId: string, data: { model?: string; role?: string; tokens_in: number; tokens_out: number; note?: string }) =>
    request<any>("POST", `/kanban/tasks/${taskId}/usage`, data),
  getTaskStats: (taskId: string) => request<any>("GET", `/kanban/tasks/${taskId}/stats`),
  getTaskHistory: (taskId: string) => request<any>("GET", `/kanban/tasks/${taskId}/history`),

  // === 2-Stufiger Review (Vollstaendigkeit + Qualitaet) ===
  completenessCheck: (projectId: string) => request<any>("POST", `/kanban/completeness-check/${projectId}`),
  getCompleteness: (projectId: string) => request<any>("GET", `/kanban/completeness/${projectId}`),
  answerCompleteness: (projectId: string, clarificationId: string, answer: string) =>
    request<any>("POST", `/kanban/completeness/${projectId}/answer`, { clarification_id: clarificationId, answer }),
  // requirements/review ist bereits oben (reviewRequirementsDoc)

  // === 9-Schritt-Review-Pipeline ===
  runReviewPipeline: (projectId: string) => request<any>("POST", `/kanban/review/pipeline/${projectId}`),
  getReviewPipeline: (projectId: string) => request<any>("GET", `/kanban/review/pipeline/${projectId}`),

  // === Task Drag & Drop ===
  updateTaskStatus: (taskId: string, status: string) => request<any>("PUT", `/kanban/tasks/${taskId}/status`, { status }),
  // === Task Priority (Watchdog: Prio=100 loest Notfallumsetzung aus) ===
  updateTaskPriority: (taskId: string, priority: number) => request<any>("PUT", `/kanban/tasks/${taskId}/priority`, { priority }),
  bulkSetTasksTriage: (projectId: string) => request<any>("POST", `/kanban/tasks/bulk-triage/${projectId}`),
  // === Sub-Tasks (PI-Worker teilt grosse Tasks) ===
  createSubtasks: (taskId: string, subtasks: any[]) => request<any>("POST", `/kanban/tasks/${taskId}/subtasks`, { subtasks }),
  aggregateSubtasks: (taskId: string) => request<any>("POST", `/kanban/tasks/${taskId}/aggregate`, {}),
  // === Task Workflow (CIO + PI-Worker + Auto-Review) ===
  taskWorkflow: (taskId: string, action: string, extra?: any) =>
    request<any>("POST", `/kanban/tasks/${taskId}/workflow`, { action, ...(extra || {}) }),
  getTaskReview: (taskId: string) => request<any>("GET", `/kanban/tasks/${taskId}/review`),

  // === CIO-Review + Implementation-Start ===
  cioReviewImplementation: (projectId: string) => request<any>("POST", `/kanban/implementation/${projectId}/cio-review`),
  startImplementation: (projectId: string) => request<any>("POST", `/kanban/implementation/${projectId}/start`),
  getImplementation: (projectId: string) => request<any>("GET", `/kanban/implementation/${projectId}`),
  markStepDone: (projectId: string, stepId: string) => request<any>("POST", `/kanban/implementation/${projectId}/step/${stepId}/done`),

  // === Quality-Rückfragen (aus NALABS-Review) ===
  saveQualityClarifications: (projectId: string, clarifications: any[]) =>
    request<any>("POST", `/kanban/quality/${projectId}/save-clarifications`, { clarifications }),
  getQuality: (projectId: string) => request<any>("GET", `/kanban/quality/${projectId}`),
  answerQuality: (projectId: string, clarificationId: string, answer: string) =>
    request<any>("POST", `/kanban/quality/${projectId}/answer`, { clarification_id: clarificationId, answer }),

  // === OpenBrain-Validierung + Klaerungsfragen ===
  startValidation: (projectId: string) => request<any>("POST", `/kanban/validation/${projectId}/start`),
  getValidation: (projectId: string) => request<any>("GET", `/kanban/validation/${projectId}`),
  answerClarification: (projectId: string, clarificationId: string, answer: string) =>
    request<any>("POST", `/kanban/validation/${projectId}/answer`, { clarification_id: clarificationId, answer }),

  // === SRS-Versionen + Diff + Export ===
  listRequirementVersions: (projectId: string) =>
    request<any[]>("GET", `/kanban/requirements/${projectId}/versions`),
  diffRequirements: (projectId: string, fromVer?: string, toVer?: string) =>
    request<any>("GET", `/kanban/requirements/${projectId}/diff?from_version=${fromVer || "v1"}&to_version=${toVer || "v2"}`),
  exportRequirements: (projectId: string, format: string) =>
    request<any>("GET", `/kanban/requirements/${projectId}/export?format=${format}`),

  // === Brain-Dev (OpenBrain DEV Vorgaben) ===
  getBrainDev: () => request<any>("GET", "/kanban/brain-dev"),

  // Tools
  listTools: () => request<any[]>("GET", "/tools"),
  toolsSummary: () => request<any>("GET", "/tools/summary"),

  // Skills
  listSkills: () => request<any[]>("GET", "/skills"),
  getSkill: (name: string) => request<any>("GET", `/skills/${name}`),

  // Extensions
  listExtensions: () => request<any[]>("GET", "/extensions"),
  getExtension: (name: string) => request<any>("GET", `/extensions/${name}`),

  // Cost
  costSummary: (days = 30) => request<any>("GET", `/cost/summary?days=${days}`),
  costBySession: (limit = 20) => request<any>("GET", `/cost/by-session?limit=${limit}`),

  // Logs (SSE handled separately)
  recentLogs: (limit = 100, source = "all") =>
    request<any>("GET", `/logs/recent?limit=${limit}&source=${source}`),

  // OpenBrain
  openBrainStatus: () => request<any>("GET", "/openbrain/status"),
  openBrainSearch: (query: string, limit = 5, threshold = 0.3) =>
    request<any>("POST", "/openbrain/search", { query, limit, threshold }),
  openBrainStats: () => request<any>("GET", "/openbrain/stats"),
};

// ─── SSE Helper ────────────────────────────────────────────────────
export function createLogStream(
  interval = 2,
  source = "sessions",
  onData: (entry: any) => void
): () => void {
  const url = `${API_BASE}/logs/stream?interval=${interval}&source=${source}`;
  const abortController = new AbortController();

  async function poll() {
    while (!abortController.signal.aborted) {
      try {
        const res = await fetch(url, {
          headers: { Authorization: `Bearer ${authToken}` },
          signal: abortController.signal,
        });
        const reader = res.body?.getReader();
        if (!reader) continue;
        const decoder = new TextDecoder();
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const text = decoder.decode(value, { stream: true });
          for (const line of text.split("\n")) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6));
                onData(data);
              } catch {
                /* skip malformed */
              }
            }
          }
        }
      } catch {
        if (!abortController.signal.aborted) {
          await new Promise((r) => setTimeout(r, 3000));
        }
      }
    }
  }
  poll();
  return () => abortController.abort();
}
