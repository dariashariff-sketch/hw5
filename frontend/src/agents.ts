import type { AgentEvent, Role } from "./api";

export interface AgentMeta {
  role: Role;
  name: string;
  initials: string;
  job: string;
  color: string; // main pastel
  deep: string; // text / ring
}

// One pastel per teammate so you can follow who is talking at a glance.
export const AGENTS: AgentMeta[] = [
  { role: "boss", name: "Boss", initials: "B", job: "Routes tickets, makes the final call", color: "#f4a7b6", deep: "#d9607c" },
  { role: "inventory", name: "Inventory", initials: "In", job: "Stock by SKU & size, restock vendors", color: "#9fbbd3", deep: "#4f7699" },
  { role: "accounting", name: "Accounting", initials: "Ac", job: "Cash, invoices, margins, prepares payments", color: "#ffd98a", deep: "#b3812a" },
  { role: "facilities", name: "Facilities", initials: "Fa", job: "The Chapel Street lease & rent", color: "#b9dfc7", deep: "#4d8a64" },
  { role: "customer_service", name: "Customer Service", initials: "CS", job: "Kind customer drafts, never sent", color: "#d7c6ec", deep: "#7c63a3" },
];

export const AGENT_BY_ROLE = Object.fromEntries(AGENTS.map((a) => [a.role, a])) as Record<Role, AgentMeta>;

export const TOOL_LABELS: Record<string, string> = {
  list_open_tickets: "looking at the board",
  list_all_tickets: "looking at the board",
  get_ticket_details: "reading the ticket",
  check_stock_and_vendors: "checking stock & vendors",
  get_pricing_and_margin: "running margin math",
  get_lease_rent_status: "checking the lease",
  get_invoice_status: "checking the invoice",
  get_cash_position: "checking cash",
  list_pending_approvals: "checking approvals",
  post_to_board: "posting to the board",
  request_payment: "preparing a payment for approval",
  request_purchase_order: "preparing a purchase order for approval",
  update_ticket_status: "updating the ticket status",
  ask_teammate: "asking a teammate",
  final_result: "handing in their report",
};

export type AgentStatus = "idle" | "working" | "waiting" | "done";

export interface AgentState {
  status: AgentStatus;
  doing: string | null; // short "what they're doing now"
  lastSaid: string | null;
  toolsUsed: Record<string, number>;
  output: Record<string, unknown> | null;
  waitingOn: Role | null;
}

const emptyState = (): AgentState => ({
  status: "idle", doing: null, lastSaid: null, toolsUsed: {}, output: null, waitingOn: null,
});

/** Replay one run's events into "what each agent is doing / did". */
export function agentStates(events: AgentEvent[]): Record<Role, AgentState> {
  const states = Object.fromEntries(AGENTS.map((a) => [a.role, emptyState()])) as Record<Role, AgentState>;
  for (const e of events) {
    if (e.agent === "human") continue;
    const s = states[e.agent];
    if (!s) continue;
    switch (e.event) {
      case "run_start":
        s.status = "working";
        s.doing = "getting started";
        break;
      case "model_request":
        if (s.status !== "done") s.doing = "thinking";
        break;
      case "model_response": {
        const said = e.said.filter(Boolean);
        if (said.length) s.lastSaid = said[said.length - 1];
        for (const c of e.tool_calls) {
          s.toolsUsed[c.tool] = (s.toolsUsed[c.tool] ?? 0) + 1;
          s.doing = TOOL_LABELS[c.tool] ?? `using ${c.tool}`;
        }
        break;
      }
      case "delegate":
        s.status = "waiting";
        s.waitingOn = e.to ?? null;
        s.doing = `waiting on ${e.to ? AGENT_BY_ROLE[e.to]?.name : "a teammate"}`;
        break;
      case "run_end":
        s.status = "done";
        s.doing = "done";
        s.output = e.output ?? null;
        s.waitingOn = null;
        break;
      case "error":
        s.status = "done";
        s.doing = "stopped (see error)";
        break;
    }
    // a teammate finishing hands control back to whoever asked
    if (e.event === "run_end" && e.chain.length > 1) {
      const parent = e.chain[e.chain.length - 2] as Role;
      if (states[parent]?.status === "waiting") {
        states[parent].status = "working";
        states[parent].waitingOn = null;
        states[parent].doing = "reading the report";
      }
    }
  }
  return states;
}

export const money = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 0, maximumFractionDigits: 2 });

export const prettyStatus = (s: string) => s.replace(/_/g, " ");
