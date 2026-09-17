const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: "ADMIN" | "ENGINEER" | "ON_CALL_ENGINEER" | "VIEWER";
  is_active: boolean;
  created_at: string;
  permissions?: string[];
}

export interface Service {
  id: string;
  name: string;
  slug: string;
  description?: string;
  repository?: string;
  environment: string;
  health_endpoint?: string;
  status: "HEALTHY" | "DEGRADED" | "UNHEALTHY" | "UNKNOWN";
  criticality: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  created_at: string;
  updated_at: string;
  uptime_percentage?: number;
  avg_response_time_ms?: number;
  active_incidents_count?: number;
  recent_health_checks?: HealthCheck[];
}

export interface HealthCheck {
  id: string;
  service_id: string;
  http_status?: number;
  response_time_ms?: number;
  availability: boolean;
  error?: string;
  created_at: string;
}

export interface Alert {
  id: string;
  service_id: string;
  service_name?: string;
  incident_id?: string;
  source: string;
  severity: "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  title: string;
  description?: string;
  fingerprint: string;
  metadata_json: Record<string, any>;
  first_seen: string;
  last_seen: string;
  occurrence_count: number;
  status: "OPEN" | "ACKNOWLEDGED" | "SUPPRESSED" | "RESOLVED";
  created_at: string;
}

export interface Incident {
  id: string;
  service_id: string;
  service_name?: string;
  title: string;
  description?: string;
  status: "DETECTED" | "TRIGGERED" | "ACKNOWLEDGED" | "INVESTIGATING" | "MITIGATING" | "RESOLVED" | "CLOSED";
  severity: "SEV1" | "SEV2" | "SEV3" | "SEV4";
  detected_at: string;
  acknowledged_at?: string;
  resolved_at?: string;
  closed_at?: string;
  assignee_id?: string;
  assignee_name?: string;
  created_at: string;
  updated_at: string;
  timeline_events?: TimelineEvent[];
  comments?: IncidentComment[];
  alert_count?: number;
}

export interface TimelineEvent {
  id: string;
  incident_id: string;
  actor_id?: string;
  actor_name?: string;
  event_type: string;
  message: string;
  metadata_json: Record<string, any>;
  created_at: string;
}

export interface IncidentComment {
  id: string;
  incident_id: string;
  author_id: string;
  author_name?: string;
  body: string;
  created_at: string;
  edited_at?: string;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  service_id?: string;
  service_name: string;
  level: "INFO" | "WARN" | "WARNING" | "ERROR" | "CRITICAL";
  message: string;
  trace_id?: string;
  request_id?: string;
  metadata_json: Record<string, any>;
  created_at: string;
}

export interface Runbook {
  id: string;
  service_id?: string;
  service_name?: string;
  title: string;
  incident_type: string;
  body: string;
  owner_id?: string;
  created_at: string;
  updated_at: string;
}

export interface Postmortem {
  id: string;
  incident_id: string;
  incident_title?: string;
  summary: string;
  impact: string;
  timeline: string;
  root_cause?: string;
  contributing_factors?: string;
  resolution?: string;
  preventive_actions?: string;
  lessons_learned?: string;
  owner_id?: string;
  status: "DRAFT" | "REVIEW" | "APPROVED";
  created_at: string;
  updated_at: string;
}

export interface AIAnalysis {
  id?: string;
  incident_id: string;
  provider: string;
  summary: string;
  probable_causes: string[];
  evidence: { kind: string; fact: string; source?: string }[];
  recommended_actions: string[];
  confidence: number;
  related_incidents: string[];
  created_at?: string;
}

export interface AnalyticsSummary {
  total_incidents: number;
  active_incidents: number;
  resolved_incidents: number;
  alert_count: number;
  alert_to_incident_ratio: number;
  mtta: { mean_minutes: number; count: number; definition: string };
  mttr: { mean_minutes: number; median_minutes: number; p95_minutes: number; count: number; definition: string };
  severity_breakdown: { severity: string; count: number; percentage: number }[];
  incidents_by_service: { service_id: string; service_name: string; count: number; sev1_count: number }[];
  incident_trends: { date: string; count: number; sev1: number; sev2: number; sev3: number; sev4: number }[];
  service_reliability: { service_id: string; service_name: string; uptime_percentage: number; total_checks: number; avg_latency_ms?: number }[];
  recurring_patterns: { pattern_key: string; description: string; occurrences: number; affected_services: string[]; sample_incident_ids: string[] }[];
}

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("incidentops_token");
}

export function setTokens(access: string, refresh: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem("incidentops_token", access);
  localStorage.setItem("incidentops_refresh", refresh);
}

export function clearTokens() {
  if (typeof window === "undefined") return;
  localStorage.removeItem("incidentops_token");
  localStorage.removeItem("incidentops_refresh");
  localStorage.removeItem("incidentops_user");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const url = `${API_BASE}${path}`;
  const response = await fetch(url, { ...options, headers });

  if (response.status === 204) {
    return {} as T;
  }

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const errCode = data?.error?.code || "API_ERROR";
    const errMsg = data?.error?.message || response.statusText || "Request failed";
    throw new ApiError(errCode, errMsg, response.status);
  }

  return data as T;
}

export const api = {
  // Auth
  login: async (email: string, password: string) => {
    const res = await request<{ access_token: string; refresh_token: string }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setTokens(res.access_token, res.refresh_token);
    return res;
  },
  getMe: async () => request<User>("/api/v1/users/me"),
  listUsers: async () => request<User[]>("/api/v1/users"),

  // Incidents
  listIncidents: async (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return request<Incident[]>(`/api/v1/incidents${qs}`);
  },
  getIncident: async (id: string) => request<Incident>(`/api/v1/incidents/${id}`),
  createIncident: async (payload: { service_id: string; title: string; description?: string; severity: string }) =>
    request<Incident>("/api/v1/incidents", { method: "POST", body: JSON.stringify(payload) }),
  updateIncident: async (id: string, payload: Partial<Incident>) =>
    request<Incident>(`/api/v1/incidents/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  transitionIncident: async (id: string, status: string, reason?: string) =>
    request<Incident>(`/api/v1/incidents/${id}/transition`, { method: "POST", body: JSON.stringify({ status, reason }) }),
  reopenIncident: async (id: string, reason: string) =>
    request<Incident>(`/api/v1/incidents/${id}/reopen`, { method: "POST", body: JSON.stringify({ reason }) }),
  assignIncident: async (id: string, assignee_id: string, reason?: string) =>
    request<Incident>(`/api/v1/incidents/${id}/assign`, { method: "POST", body: JSON.stringify({ assignee_id, reason }) }),
  addComment: async (id: string, body: string) =>
    request<IncidentComment>(`/api/v1/incidents/${id}/comments`, { method: "POST", body: JSON.stringify({ body }) }),
  getIncidentTimeline: async (id: string) => request<TimelineEvent[]>(`/api/v1/incidents/${id}/timeline`),
  getIncidentAlerts: async (id: string) => request<Alert[]>(`/api/v1/incidents/${id}/alerts`),

  // Services
  listServices: async () => request<Service[]>("/api/v1/services"),
  getService: async (id: string) => request<Service>(`/api/v1/services/${id}`),
  createService: async (payload: Partial<Service>) =>
    request<Service>("/api/v1/services", { method: "POST", body: JSON.stringify(payload) }),
  updateService: async (id: string, payload: Partial<Service>) =>
    request<Service>(`/api/v1/services/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  triggerHealthCheck: async (id: string) =>
    request<HealthCheck>(`/api/v1/services/${id}/health-check`, { method: "POST" }),
  getServiceHealth: async (id: string) => request<HealthCheck[]>(`/api/v1/services/${id}/health`),

  // Alerts
  listAlerts: async (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return request<Alert[]>(`/api/v1/alerts${qs}`);
  },
  acknowledgeAlert: async (id: string, reason?: string) =>
    request<Alert>(`/api/v1/alerts/${id}/acknowledge`, { method: "POST", body: JSON.stringify({ reason }) }),
  suppressAlert: async (id: string, reason: string, duration_minutes = 60) =>
    request<Alert>(`/api/v1/alerts/${id}/suppress`, { method: "POST", body: JSON.stringify({ reason, duration_minutes }) }),
  resolveAlert: async (id: string, reason?: string) =>
    request<Alert>(`/api/v1/alerts/${id}/resolve`, { method: "POST", body: JSON.stringify({ reason }) }),

  // Logs
  listLogs: async (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return request<LogEntry[]>(`/api/v1/logs${qs}`);
  },

  // Runbooks
  listRunbooks: async (service_id?: string) => {
    const qs = service_id ? `?service_id=${service_id}` : "";
    return request<Runbook[]>(`/api/v1/runbooks${qs}`);
  },
  getRunbook: async (id: string) => request<Runbook>(`/api/v1/runbooks/${id}`),
  createRunbook: async (payload: Partial<Runbook>) =>
    request<Runbook>("/api/v1/runbooks", { method: "POST", body: JSON.stringify(payload) }),

  // Postmortems
  listPostmortems: async () => request<Postmortem[]>("/api/v1/postmortems"),
  getPostmortem: async (id: string) => request<Postmortem>(`/api/v1/postmortems/${id}`),
  getPostmortemByIncident: async (incidentId: string) => request<Postmortem | null>(`/api/v1/postmortems/by-incident/${incidentId}`),
  createPostmortem: async (payload: Partial<Postmortem>) =>
    request<Postmortem>("/api/v1/postmortems", { method: "POST", body: JSON.stringify(payload) }),
  updatePostmortem: async (id: string, payload: Partial<Postmortem>) =>
    request<Postmortem>(`/api/v1/postmortems/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),

  // Analytics
  getAnalyticsSummary: async (days = 30) => request<AnalyticsSummary>(`/api/v1/analytics/summary?days=${days}`),

  // AI & AIOps
  analyzeIncident: async (id: string) => request<AIAnalysis>(`/api/v1/ai/incidents/${id}/analysis`, { method: "POST" }),
  getIncidentAnalysis: async (id: string) => request<AIAnalysis | null>(`/api/v1/ai/incidents/${id}/analysis`),
  generatePostmortemDraft: async (id: string) => request<any>(`/api/v1/ai/incidents/${id}/postmortem-draft`, { method: "POST" }),
  recommendRemediation: async (id: string) => request<any>(`/api/v1/ai/incidents/${id}/remediation`, { method: "POST" }),
};
