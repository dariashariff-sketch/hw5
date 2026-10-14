// Talks to the FastAPI backend from Problem 7.
export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export type Role = "boss" | "inventory" | "accounting" | "facilities" | "customer_service";

export interface Ticket {
  id: number;
  type: string;
  requester: string;
  subject: string;
  status: string; // Boss's database status, e.g. waiting_on_human
  state: "open" | "resolved";
  agents_running: boolean;
  last_run_id: string | null;
  tokens_used: number | null;
  created_at: string;
}

export interface TicketsResponse {
  shop_today: string;
  open_count: number;
  resolved_count: number;
  tickets: Ticket[];
}

export interface AgentEvent {
  seq: number;
  ts: string;
  run_id: string;
  ticket_id: number;
  agent: Role | "human";
  chain: string[];
  event: string;
  said: string[];
  tool_calls: { tool: string; args: unknown }[];
  tool_results: { tool: string; content: unknown }[];
  total_tokens: number | null;
  task?: string;
  to?: Role;
  output?: Record<string, unknown>;
  detail?: Record<string, unknown>;
}

export interface Approval {
  id: number;
  ticket_id: number;
  kind: "invoice" | "rent" | "purchase_order";
  ref_id: number;
  amount: number;
  account: string;
  requested_by: string;
  reason: string;
  status: string;
  created_at: string;
}

export interface Cash {
  account: string;
  balance: number;
  as_of: string;
  pending_approvals_total: number;
  balance_if_all_pending_paid: number;
  payments: { id: number; kind: string; ref_id: number; amount: number; paid_at: string; approved_by: string }[];
}

export interface BoardPost {
  id: number;
  ticket_id: number;
  author_role: Role;
  kind: "customer_draft" | "vendor_draft" | "internal_note" | "decision" | "escalation";
  content: string;
  created_at: string;
}

export interface TicketDetails {
  shop_today: string;
  ticket: Record<string, unknown> & { id: number; notes: string | null };
  board_posts: BoardPost[];
  approvals: Approval[];
}

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "object" && detail && "error" in detail ? String((detail as { error: unknown }).error) : String(detail));
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body?.detail ?? body);
  return body as T;
}

export const api = {
  tickets: () => request<TicketsResponse>("/tickets"),
  ticket: (id: number) => request<TicketDetails>(`/tickets/${id}`),
  run: (id: number) => request<{ run_id: string }>(`/tickets/${id}/run`, { method: "POST", body: "{}" }),
  events: (after: number | null) =>
    request<{ last_seq: number | null; events: AgentEvent[] }>(
      `/events?limit=1000${after === null ? "" : `&after=${after}`}`,
    ),
  approvals: () => request<{ pending: Approval[]; balances: Record<string, number> }>("/approvals"),
  approve: (id: number, approvedBy: string) =>
    request<Record<string, unknown>>(`/approvals/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ approved_by: approvedBy }),
    }),
  reject: (id: number, decidedBy: string, reason: string) =>
    request<Record<string, unknown>>(`/approvals/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ decided_by: decidedBy, reason }),
    }),
  cash: () => request<Cash>("/cash"),
  reset: () => request<{ reset: boolean }>("/reset", { method: "POST" }),
};
