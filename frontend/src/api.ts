export type FieldDef = {
  key: string; label: string; type: string; required: boolean; help: string;
  placeholder: string; default: string; options: string[];
};
export type ToolMeta = { name: string; description: string; write: boolean };
export type ConnectorT = {
  id: string; name: string; category: string; description: string; icon: string; color: string;
  docs_url: string; setup_steps: string[]; fields: FieldDef[]; builtin: boolean; tools: ToolMeta[];
  connected: boolean; enabled: boolean; status: string; status_message: string; values: Record<string, string>;
};
export type AgentT = {
  id: string; name: string; description: string; icon: string; color: string; system_prompt: string;
  model: string; effort: string; connectors: string[]; auto_approve: boolean;
};
export type PendingT = {
  id: string; name: string; input: Record<string, unknown>; needs_approval: boolean; write: boolean;
  connector: string; description: string; decision?: string;
};
export type EventT = { id: number; kind: string; payload: any; created_at: number };
export type ConversationT = {
  id: string; agent_id: string; title: string; status: string; error: string | null; source: string;
  usage_in: number; usage_out: number; created_at: number; updated_at: number; pending: PendingT[];
  events?: EventT[];
};
export type ActivityT = {
  id: number; conversation_id: string; agent_id: string; connector_id: string; tool: string; input: string;
  result: string; ok: boolean; duration_ms: number; approved_by: string; created_at: number;
};
export type AutomationT = {
  id: string; name: string; agent_id: string; prompt: string; interval_minutes: number; enabled: number;
  last_run: number | null; last_conversation_id: string | null;
};
export type Dashboard = {
  connectors_total: number; connectors_active: number; agents: number; conversations: number;
  pending_approvals: number; actions_7d: number; success_rate: number; tokens_in: number; tokens_out: number;
  activity_per_day: number[]; top_connectors: { connector_id: string; n: number }[]; recent: ActivityT[];
  api_key_set: boolean;
};
export type SettingsT = {
  anthropic_api_key: string; company_name: string; company_profile: string; default_model: string;
  default_effort: string; fallback_enabled: boolean;
};
export type MetaT = { name: string; version: string; models: { id: string; label: string }[]; efforts: string[]; workspace: string };

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((data as any).detail || `HTTP ${r.status}`);
  return data as T;
}

export const api = {
  meta: () => req<MetaT>("GET", "/api/meta"),
  dashboard: () => req<Dashboard>("GET", "/api/dashboard"),
  settings: () => req<SettingsT>("GET", "/api/settings"),
  saveSettings: (s: Partial<SettingsT>) => req<SettingsT>("PUT", "/api/settings", s),
  testKey: () => req<{ ok: boolean; model: string }>("POST", "/api/settings/test"),

  connectors: () => req<ConnectorT[]>("GET", "/api/connectors"),
  saveConnector: (id: string, values: Record<string, string>, enabled: boolean) =>
    req("PUT", `/api/connectors/${id}`, { values, enabled }),
  testConnector: (id: string) => req<{ ok: boolean; message: string }>("POST", `/api/connectors/${id}/test`),
  deleteConnector: (id: string) => req("DELETE", `/api/connectors/${id}`),

  agents: () => req<AgentT[]>("GET", "/api/agents"),
  createAgent: (a: Omit<AgentT, "id">) => req<AgentT>("POST", "/api/agents", a),
  updateAgent: (a: AgentT) => req<AgentT>("PUT", `/api/agents/${a.id}`, a),
  deleteAgent: (id: string) => req("DELETE", `/api/agents/${id}`),

  conversations: (agentId?: string) =>
    req<ConversationT[]>("GET", `/api/conversations${agentId ? `?agent_id=${agentId}` : ""}`),
  conversation: (id: string, after = 0) => req<ConversationT>("GET", `/api/conversations/${id}?after=${after}`),
  createConversation: (agent_id: string, message?: string) =>
    req<ConversationT>("POST", "/api/conversations", { agent_id, message }),
  send: (id: string, text: string) => req("POST", `/api/conversations/${id}/messages`, { text }),
  decide: (id: string, decisions: Record<string, { approve: boolean; input?: unknown }>) =>
    req("POST", `/api/conversations/${id}/decide`, { decisions }),
  stop: (id: string) => req("POST", `/api/conversations/${id}/stop`),
  deleteConversation: (id: string) => req("DELETE", `/api/conversations/${id}`),
  approvals: () => req<ConversationT[]>("GET", "/api/approvals"),

  activity: (connector?: string) =>
    req<ActivityT[]>("GET", `/api/activity${connector ? `?connector_id=${connector}` : ""}`),

  automations: () => req<AutomationT[]>("GET", "/api/automations"),
  createAutomation: (a: Partial<AutomationT>) => req<AutomationT>("POST", "/api/automations", a),
  updateAutomation: (id: string, a: Partial<AutomationT>) => req<AutomationT>("PUT", `/api/automations/${id}`, a),
  runAutomation: (id: string) => req<{ conversation_id: string }>("POST", `/api/automations/${id}/run`),
  deleteAutomation: (id: string) => req("DELETE", `/api/automations/${id}`),
};

export function timeAgo(ts: number | null | undefined): string {
  if (!ts) return "—";
  const d = Date.now() / 1000 - ts;
  if (d < 60) return "az önce";
  if (d < 3600) return `${Math.floor(d / 60)} dk önce`;
  if (d < 86400) return `${Math.floor(d / 3600)} sa önce`;
  return new Date(ts * 1000).toLocaleDateString("tr-TR", { day: "numeric", month: "short" });
}

export function prettyTool(full: string, connectors: ConnectorT[]): { connector?: ConnectorT; name: string } {
  const [cid, name] = full.includes("__") ? full.split("__") : ["", full];
  return { connector: connectors.find((c) => c.id === cid), name: (name || full).replace(/_/g, " ") };
}
