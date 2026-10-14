# Campus Customs Multi-Agent Operations — Harness

## Databases

- `data/campus_customs.db` — original snapshot. **Never modified.** Used to reset.
- `data/campus_customs_new.db` — working copy. The MCP server and backend read and write only this file. Reset it from the original before each full run.

## Tables

| Table | Fields | Why it matters for the agents |
|---|---|---|
| `desk` | `date_today`, `notes` | The shop's "today" (2026-08-31); every overdue and due-soon check uses this date, not the system clock. |
| `tickets` | `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id`, `invoice_id`, `status`, `notes`, `created_at` | The work queue on the board; Boss reads each one and routes it using the linked sku/lease/invoice. |
| `inventory` | `sku`, `name`, `size`, `qty`, `location` (PK: `sku`+`size`) | Inventory checks stock per SKU and size to find shortfalls. |
| `pricing` | `sku`, `unit_cost`, `list_price` | Accounting computes margins and discount floors, and the cost of restock purchase orders. |
| `vendors` | `id`, `name`, `specialty`, `lead_days` | Inventory picks a restock vendor by specialty; `lead_days` sets the restock ETA. |
| `invoices` | `id`, `vendor_id`, `amount`, `due_date`, `status`, `description` | Bills the shop owes. An `open` invoice blocks that vendor from shipping, and a past `due_date` means it's overdue. |
| `leases` | `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes` | Facilities tracks rent amount and due date for the shop space. |
| `cash_accounts` | `name`, `balance`, `date` | The only cash source ($3,400 checking). The pay tool refuses any payment larger than the balance, so it can never go negative. |
| `payments` | `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by` | Audit log of money out. Empty at start; every row must name the human who approved it. |

**Team tables** (created in the working copy by the MCP server on first write; not in the original; removed by a reset):

| Table | Fields | Why it matters |
|---|---|---|
| `board_posts` | `id`, `ticket_id`, `author_role`, `kind`, `content`, `created_at` | The board: customer and vendor drafts (never sent), team notes, Boss's decisions, escalations. |
| `approvals` | `id`, `ticket_id`, `kind`, `ref_id`, `amount`, `account`, `requested_by`, `reason`, `status`, `created_at`, `decided_by`, `decided_at`, `decision_note`, `payment_id` | Payment and PO requests agents prepare. They stay `pending` until a human approves (`approved_paid`) or rejects them. |
| `purchase_orders` | `id`, `ticket_id`, `vendor_id`, `sku`, `size`, `qty`, `unit_cost`, `total`, `status`, `expected_arrival`, `created_at` | Restock orders at `pricing.unit_cost`. They become `ordered` with an arrival date only after a human approves and pays. |

## Starting state (desk date 2026-08-31)

- Cash: checking $3,400.
- Inventory gaps: `CC-TEE-WHITE` size S = 0, `CC-MUG-CREST` OS = 0, `CC-HOOD-NAVY` M = 8.
- Vendors: 1 Bulldog Print Co (apparel reprint, 5 days), 2 Elm City Gifts (mugs and small goods, 3 days), 3 QuickShip CT (local courier, 1 day).
- Invoice 501: Bulldog Print Co, $840, due 2026-08-28, `open`. **Overdue by 3 days.** Bulldog won't ship until it's paid.
- Lease 1: Chapel Street shop, Elm City Properties, $2,400 rent, next due 2026-09-02 (in 2 days).

## The three open tickets and their links

**#101 `customer_order`: Tauhid Zaman, 1 × Bulldog tee, `CC-TEE-WHITE` size S**
- inventory → S qty = 0, so this is a shortfall of 1.
- `invoice_id` 501 → vendors 1, Bulldog Print Co, the only apparel vendor. The invoice is open and overdue, so Bulldog won't ship.
- Path: Accounting prepares an $840 payment for 501 (needs human approval). Then Inventory reorders from Bulldog (5-day lead time). Customer Service drafts an ETA message to Tauhid.

**#102 `rent_notice`: Elm City Properties, rent due**
- `lease_id` 1 → $2,400 due 2026-09-02. It isn't overdue yet, but it's due in 2 days.
- Path: Facilities confirms the lease terms and Accounting prepares a $2,400 payment (needs human approval).

**#103 `price_override`: Yale AI Club, 20 × `CC-HOOD-NAVY` size M, wants a bulk discount**
- inventory → M qty = 8, so 12 short. Restocking would come from Bulldog Print Co, which is blocked by invoice 501.
- pricing → cost $22, list $58 (62% margin). The full order at list price is $1,160. Any discount has to stay above the $22 cost.
- Path: Inventory reports the shortfall. Accounting proposes a discount that keeps the margin positive, and Boss makes the call. Customer Service drafts the quote.

## Cross-ticket constraint: cash

The agents can't treat the tickets independently, because they all draw on the same $3,400.

| Outflow | Amount | Cash left |
|---|---|---|
| Pay invoice 501 (unblocks Bulldog) | $840 | $2,560 |
| Pay rent, lease 1 | $2,400 | $160 |
| Restock PO: 1 tee S @ $8 | $8 | $152 |
| Restock PO: 12 hoodies M @ $22 | $264 | **−$112 ✗** |

All of these need human approval, and the pay tool must refuse anything that would make the balance negative. No revenue is modeled. Boss has to prioritize. Rent and the overdue invoice come first, so the hoodie restock can't be paid for unless something else is deferred.

## First three MCP tools (Problem 3)

These read `data/campus_customs_new.db` read-only. The full tool list is in *MCP tool catalog* below. Each value comes from a database row. Missing rows return an error, never a guess.

**1. `check_stock_and_vendors(sku, size, qty_needed)`**
- **Tables read:** `desk.date_today`; `inventory.qty`, `name`, `location` for the (`sku`, `size`) row; `vendors.name`, `specialty`, `lead_days`; `invoices` rows with `status = 'open'` for each vendor (amount, `due_date`, description).
- **Unlocks:** ticket **101** (also used by 103 for the 12-hoodie shortfall).
- **Why it's right for 101:** It shows that `CC-TEE-WHITE` size S has 0 on hand, so Tauhid's 1-tee order is short by 1. It also shows that Bulldog Print Co, the apparel vendor (5-day lead), has `can_ship = false` because invoice 501 ($840) is open and 3 days overdue. So Inventory knows the restock depends on Accounting paying 501 first.

**2. `get_lease_rent_status(lease_id)`**
- **Tables read:** `desk.date_today`; `leases.space_name`, `landlord`, `monthly_rent`, `next_due`, `notes` for that lease; `cash_accounts.balance` for every account. Since Problem 5 it also reads `approvals` and `payments` for rent already requested or paid.
- **Unlocks:** ticket **102**.
- **Why it's right for 102:** Ticket 102 links to `lease_id = 1`. The tool returns the $2,400 rent for the Chapel Street shop, due 2026-09-02, which is 2 days after the desk date (`overdue = false`), and shows that checking's $3,400 covers it. That gives Facilities and Accounting the exact amount and deadline to prepare a rent payment for human approval.

**3. `get_pricing_and_margin(sku, qty, discount_pct)`**
- **Tables read:** `pricing.unit_cost`, `list_price` for that SKU.
- **Unlocks:** ticket **103**.
- **Why it's right for 103:** The Yale AI Club wants a bulk discount on 20 `CC-HOOD-NAVY` hoodies. The tool turns any proposed discount into a unit price and total margin, using the $22 cost and $58 list price. It also reports the 62.07% maximum discount before a loss, so Accounting and Boss can approve a discount that stays profitable.

## Hard rules (from the assignment)

- Every payment and purchase order requires human approval on the dashboard.
- A payment updates the related tables: `payments` row, `cash_accounts.balance`, and `invoices.status` or `leases.next_due`.
- The pay tool refuses payments when cash is insufficient. Balances never go negative.
- No real emails or vendor calls. Customer and vendor messages stay on the board as drafts.
- Every agent's LLM calls go through Portkey (`PORTKEY_API_KEY`), using model `openai-gpt-luna-6` only.

## Agent team (Problem 5)

Built with Pydantic AI. Every agent uses `openai-gpt-luna-6` through Portkey (`backend/config.py`, the only place a model is named). Every shop fact and every write goes through the MCP server. The backend has no SQL and no second tools layer.

| Agent | File / prompt | Job | MCP tools it can call |
|---|---|---|---|
| **Boss** | `backend/agents/boss.py`, `backend/prompts/boss.md` | Reads each ticket, routes it to teammates, prioritizes spending when cash is short, makes the final call, posts the decision, sets ticket status, and escalates anything complicated to a human. Returns `TicketResolution`. | `list_open_tickets`, `get_ticket_details`, `get_cash_position`, `list_pending_approvals`, `post_to_board`, `update_ticket_status` |
| **Inventory** | `backend/agents/inventory.py`, `backend/prompts/inventory.md` | Checks stock for the exact SKU and size, computes the shortfall and any partial fill, picks the restock vendor by specialty, gives lead time and earliest arrival, flags vendors blocked by open invoices, and costs the restock. | `get_ticket_details`, `check_stock_and_vendors`, `get_pricing_and_margin`, `post_to_board` |
| **Accounting** | `backend/agents/accounting.py`, `backend/prompts/accounting.md` | Tracks cash (no revenue, cash only goes out), invoices, costs and margins. Gives discount options with a 15% margin floor. Prepares invoice and rent payments and restock POs **for human approval**, after an affordability check. | `get_ticket_details`, `get_cash_position`, `get_invoice_status`, `get_lease_rent_status`, `get_pricing_and_margin`, `check_stock_and_vendors`, `list_pending_approvals`, `request_payment`, `request_purchase_order`, `post_to_board` |
| **Facilities** | `backend/agents/facilities.py`, `backend/prompts/facilities.md` | Owns the Chapel Street lease. Checks rent notices against the lease, flags urgency (≤7 days) and overdue rent, escalates contract issues, and drafts landlord replies (never sent). | `get_ticket_details`, `get_lease_rent_status`, `get_cash_position`, `post_to_board` |
| **Customer Service** | `backend/agents/customer_service.py`, `backend/prompts/customer_service.md` | Writes kind, efficient, understanding customer drafts (80–150 words) using only confirmed facts. Never shares internal numbers. Drafts stay on the board and are never sent. | `get_ticket_details`, `check_stock_and_vendors`, `get_pricing_and_margin`, `post_to_board` |

**How the agents talk to each other.** Every agent also has an `ask_teammate(teammate, request)` tool (`backend/agents/base.py`), so any role can hand work to, or ask for help from, any other role. The teammate runs its own agent loop and returns a typed `SpecialistReport` (summary, facts with source tool, actions, approval ids, recommendation, blockers). Example chain: Boss → Inventory → Accounting. Guards: no asking yourself, no cycles (you can't call a role already in the chain), at most 4 roles in a chain, and one shared token budget per ticket.

**Agent loop.** `run_agent` in `backend/agents/base.py` steps through each loop with `agent.iter()`: model request → model response (text and/or tool calls) → tool results → … → typed output. Every step is appended to `output/audit_trail.json`.

**Data types** (`backend/models.py`): `TeamDeps` (run id, ticket id, role, shared usage, request chain), `Fact`, `SpecialistReport`, `TicketResolution`, `TicketRunResult`, `AuditEvent`.

**Running** (`backend/team.py`): `python -m backend.team --all` resets the working copy from the original, then works every open ticket oldest-first. `--ticket 101` works one ticket on the current copy, and `--reset` only resets.

## MCP tool catalog (`mcp_server/server.py`, 15 tools)

| Tool | Tables used | Who calls it |
|---|---|---|
| `list_open_tickets` | reads `tickets`, `desk` | Boss |
| `list_all_tickets` | reads `tickets`, `desk` | backend `GET /tickets` (no agent) |
| `get_ticket_details` | reads `tickets`, `desk`, `inventory`, `pricing`, `leases`, `invoices`, `vendors`, `board_posts`, `approvals`, `purchase_orders` | all agents |
| `check_stock_and_vendors` | reads `inventory`, `vendors`, `invoices`, `desk` | Inventory, Accounting, Customer Service |
| `get_pricing_and_margin` | reads `pricing` | Inventory, Accounting, Customer Service |
| `get_lease_rent_status` | reads `leases`, `desk`, `cash_accounts`, `approvals`, `payments` | Facilities, Accounting |
| `get_invoice_status` | reads `invoices`, `vendors`, `desk`, `approvals`, `payments` | Accounting |
| `get_cash_position` | reads `cash_accounts`, `approvals`, `invoices`, `vendors`, `leases`, `payments`, `desk` | Boss, Accounting, Facilities |
| `list_pending_approvals` | reads `approvals`, `cash_accounts`, `desk` | Boss, Accounting |
| `post_to_board` | writes `board_posts` (checks `tickets`) | all agents (only Customer Service may post `customer_draft`, only Boss may post `decision`) |
| `request_payment` | writes `approvals` (amount read from `invoices.amount` or `leases.monthly_rent`; checks `cash_accounts`) | Accounting |
| `request_purchase_order` | writes `purchase_orders` and `approvals` (reads `pricing.unit_cost`, `vendors`, `inventory`, `invoices`, `cash_accounts`) | Accounting |
| `update_ticket_status` | writes `tickets.status` and `tickets.notes` | Boss |
| `approve_and_pay` | **human only.** Writes `payments`, `cash_accounts.balance`, `approvals`, and `invoices.status` / `leases.next_due` / `purchase_orders` | backend `POST /approvals/{id}/approve` after a human clicks Approve (no agent) |
| `reject_approval` | **human only.** Writes `approvals`, `purchase_orders` | backend `POST /approvals/{id}/reject` (no agent) |

`board_posts`, `approvals` and `purchase_orders` are team tables that the MCP server creates in the working copy on first write. The original database never has them, and a reset removes them.

`.mcp.json` at the project root registers this server as `campus-customs` (stdio, `python mcp_server/server.py`). `output/mcp_smoke.json` records the Problem 4 test of the first three tools, with every value checked against the database.

## Backend API routes (Problem 7, `backend/main.py`)

FastAPI, started from `backend/` with `uvicorn main:app --reload --port 8000`. Every route goes through the MCP server; CORS allows only the Vite dashboard origins (`http://localhost:5173`, plus `:3000`). The full list with one line each is in `output/runs.md`.

| Route | What it does |
|---|---|
| `GET /tickets` | All tickets, `open`/`resolved` (resolved once the team's run ends with Boss's decision), Boss's exact `status`, whether agents are running, tokens used. |
| `GET /tickets/{id}` | One ticket with linked rows, board posts, approvals and POs. |
| `POST /tickets/{id}/run` | Starts the team (Boss first) on one ticket in the background; returns a `run_id`. |
| `GET /runs`, `GET /runs/{run_id}` | Run status and the final `TicketResolution`. |
| `GET /events` | Recent agent steps from the audit trail: who said what, tool calls, delegations, results, tokens (poll with `after=`). |
| `GET /approvals` | Requests waiting on a human. |
| `POST /approvals/{id}/approve` | **The only route that moves money**, after a human approves (MCP `approve_and_pay`). |
| `POST /approvals/{id}/reject` | A human declines a request; no money moves. |
| `GET /cash` | Checking balance from `cash_accounts`, pending total, payment history. |
| `POST /reset` | Copies the original database over the working copy (SQLite backup API, safe while the board is reading it); refused while agents run. |

## Dashboard (Problem 8, `frontend/`)

React + Vite + TypeScript, started from `frontend/` with `npm run dev`, which opens `http://localhost:5173` and calls the API at `http://localhost:8000` (`frontend/.env`). It uses the same pastel theme as `output/desk_tickets.html`; the full design rationale is in `output/design.md`.

- **Ticket board:** 3 tickets, pick one, **Start the team**; a ticket flips to **Resolved** with a stamp when its run ends.
- **Team room:** a drawn character per agent (Boss and Accounting are women; Inventory, Facilities, Customer Service), live speech bubbles and status chips, faded when not called, and a per-ticket token-budget bar.
- **Live feed** and **Who did what:** each agent's words, tool calls, delegations, refusals and final report.
- **Checking** and **Cash timeline:** the live balance (counts down on approval) and a step chart of paid vs pending.
- **Needs your OK:** a press-and-hold **Hold to approve** (about 1.2 s, can't happen by accident) and **decline**; refusals from the pay tool show their reason.
- **On the board:** drafts (marked *not sent*), notes, decisions, escalations. **Night shift** dark mode in the corner.

## Plan vs run (Problems 6 and 9)

`output/desk_tickets.html` holds the plan made before running (Expected) next to what happened (Actual) for each ticket, plus the itemized **Cash** tab.

**Full run, 2026-10-14.** The working copy was reset first (identical to the original, checking **$3,400.00**). Tickets 101 → 102 → 103 ran one at a time through `POST /tickets/{id}/run`. All three ended with Boss's final decision, so all three show **resolved**.

| Ticket | Teammates (of 5) | Delegation | Tokens | Requests filed | Human approval | Cash |
|---|---|---|---|---|---|---|
| 101 Bulldog tee | Boss, Inventory, Accounting, Customer Service | Boss → Inventory → Accounting; Boss → Customer Service | 58,038 | #1 invoice 501 $840; #2 PO 1 tee $8 | both approved by Daria | −$848.00 |
| 102 Rent due | Boss, Facilities, Accounting | Boss → Facilities → Accounting; Boss → Accounting | 46,745 | #3 rent lease 1 $2,400 | approved by Daria | −$2,400.00 |
| 103 Bulk hoodies | Boss, Inventory, Accounting, Customer Service | Boss → Inventory → Accounting; Boss → Accounting; Boss → Customer Service | 55,676 | none | none | $0.00 |

**Cash:** $3,400.00 − $840.00 − $8.00 − $2,400.00 − $0.00 = **$152.00**, which matches `cash_accounts` in the working database. All 3 `payments` rows have `approved_by = Daria`. Invoice 501 is `paid`, lease 1's `next_due` is 2026-10-02, and PO 1 is `ordered` with arrival 2026-09-05.

**What matched the plan:** who Boss called first on every ticket, who was *not* called (never all 5), both 101 requests, the 102 rent request and the $152 leftover, no hoodie PO on 103, and every run inside the 25–60k token estimate.

**What differed:**
- **Duplicate Accounting calls:** on 102 and 103, Boss asked Accounting directly at the same moment a specialist did, so Accounting ran twice. The duplicate guard stopped any double request; the cost was tokens, not money.
- **103 discount at the floor:** Boss priced the hoodies at **$25.89 (55% off, exactly the 15% margin floor)**, not the 10–15% discount we expected. The customer draft calls it the "approved" price. It's held on the board for a human to change before anything is sent.
- **103 reason for no PO:** the vendor block, not the cash gap.

The full details are in `output/resolved_tickets.json` (per ticket: id, final status, outcome, each agent's contribution and tools, human approvals) and `output/resolved_board.html` (board screenshots after each run and after the approvals). Every step of these runs, plus the 3 human approvals, is appended to `output/audit_trail.json`.

## Output files

| File | Problem | What it is |
|---|---|---|
| `AI_prompts.md` | 1 | Every prompt, by problem. |
| `output/harness.md` | 2–9 | This file. |
| `mcp_server/server.py`, `mcp_server/README.md`, `.mcp.json` | 3–5, 7 | The MCP server (15 tools), its README, and its registration. |
| `output/mcp_smoke.json` | 4 | Evidence that the first 3 tools match the database. |
| `backend/` (`agents/`, `prompts/`, `models.py`, `config.py`, `mcp_tools.py`, `audit.py`, `team.py`, `main.py`) | 5, 7 | The agent team and the FastAPI routes. |
| `output/audit_trail.json` | 5, 9 | Append-only log of every agent loop step and human action. |
| `output/desk_tickets.html` | 6, 9 | Expected vs Actual per ticket, and the Cash tab (Reflection is left for later). |
| `output/runs.md` | 7 | Each API route in one line. |
| `frontend/`, `output/design.md` | 8 | The React dashboard and why it looks the way it does. |
| `output/resolved_tickets.json`, `output/resolved_board.html` | 9 | Resolved tickets and board screenshots. |

## Safety and guardrails

Real customers and real money call for controls in code, not just instructions in prompts:

1. **Human approval for all money.** Agents can only *request* payments and POs (`status = pending`). Money moves only in `approve_and_pay`. No agent's toolset includes it (enforced in `backend/mcp_tools.py` by tool filtering plus a second check on every call). It needs a named human approver and refuses agent role names. Every payment row records `approved_by`.
2. **No negative balances.** `approve_and_pay` refuses if the balance is below the amount, and the request tools refuse amounts the balance could never cover. Requests also report `over_committed` when pending approvals exceed cash, so Boss has to prioritize.
3. **Amounts come from the database, never from the model.** Invoice, rent and PO amounts are read from `invoices`, `leases` and `pricing`, so a model can't invent or mistype a dollar figure. Duplicate pending requests are refused.
4. **Vendor rule enforced.** A PO to a vendor with an open invoice can't be paid until that invoice is paid.
5. **Nothing leaves the building.** No email, SMS or HTTP tools exist. Customer, vendor and landlord messages are `*_draft` posts on the board, `sent_to_anyone: false`.
6. **Least privilege per role, and no impersonation.** Each agent sees only its own tools. The caller's real role is stamped onto `author_role`, `requested_by` and `updated_by`, so an agent can't pose as Boss or Customer Service.
7. **No invented facts.** Tools return errors for missing rows. Prompts require every fact in a report to name its source tool. Customer Service never shares internal numbers (cash, margins, unpaid invoices).
8. **Escalation by default.** Boss escalates cash trade-offs, discounts below a 15% margin, data conflicts, lease or contract issues, and anything uncertain. Any crash or budget stop also escalates the ticket to `waiting_on_human` automatically.
9. **Token and loop limits.** Each ticket has one shared budget across all agents: 150,000 tokens, 30 model requests, 60 tool calls, and at most 4,000 output tokens per response. A full run stops starting new tickets after 400,000 tokens. Delegation chains are capped at 4 roles, with no cycles. All limits can be changed through `CC_*` environment variables.
10. **Audit trail.** `output/audit_trail.json` is append-only (atomic rewrite, never wiped, and it refuses to overwrite a corrupt file). It records every loop step with time, run id, ticket, agent, chain, prompts, tool calls with arguments, tool results, model replies, and running token usage.
11. **Resettable sandbox.** Agents only touch `data/campus_customs_new.db`, and a full run resets it from the untouched original first.
12. **Deliberate human approval on the dashboard.** The approver types their name once (stored as `approved_by`). Approving is press-and-hold, so a stray click can't move money. Every approve, reject and reset is written to the audit trail as a `human` event.
13. **Narrow API surface.** The backend allows only the dashboard's own origins (CORS). Reset is refused while agents are running, and only one ticket runs at a time from the board, so the shared-cash reasoning stays in order.
14. **One model, one gateway.** `openai-gpt-luna-6` through Portkey is named in exactly one place (`backend/config.py`); no other model name appears in the code.
