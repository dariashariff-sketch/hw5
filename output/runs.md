# Runs — Campus Customs backend

Start from `backend/`: `uvicorn main:app --reload --port 8000` → **http://localhost:8000** (interactive docs at `/docs`). Every route reads and writes shop data through the MCP server only.

## Routes (`backend/main.py`)

| # | Method & URL | What it does |
|---|---|---|
| 1 | `GET http://localhost:8000/tickets` | All tickets with `state` (`open`/`resolved`: resolved once the team's run finishes with Boss's decision, or the database says resolved), Boss's exact `status` (e.g. `waiting_on_human`), whether agents are running, tokens used, and open/resolved counts (MCP `list_all_tickets` + audit trail). |
| 1b | `GET http://localhost:8000/tickets/{ticket_id}` | One ticket plus its linked rows, board posts (drafts, notes, decisions, escalations), approvals and POs (MCP `get_ticket_details`). |
| 2 | `POST http://localhost:8000/tickets/{ticket_id}/run` | Starts the agent team (Boss first) on that ticket in the background and returns a `run_id` (202). Body `{"wait": true}` blocks until it finishes. 404 for an unknown ticket, 409 if one is already running. |
| 2b | `GET http://localhost:8000/runs` · `GET http://localhost:8000/runs/{run_id}` | Run status (`running`/`done`/`failed`) with the final `TicketResolution` and tokens used. |
| 3 | `GET http://localhost:8000/events?limit=&after=&ticket_id=&run_id=&agent=` | Recent agent steps from `output/audit_trail.json`: who acted (agent, chain), what they said, tool calls and args, tool results, delegations, final outputs, tokens. Poll with `after=last_seq` to refresh the board. |
| 4 | `GET http://localhost:8000/approvals` | Payment and PO requests the agents prepared, waiting for a human (MCP `list_pending_approvals`). |
| 4 | `POST http://localhost:8000/approvals/{approval_id}/approve` body `{"approved_by": "<name>"}` | **Human clicks Approve. The only route that changes cash** (MCP `approve_and_pay`): writes `payments`, lowers checking, marks the invoice paid / moves the rent due date / orders the PO. 409 if cash would go negative, the vendor has an open invoice, the request isn't pending, or the approver is an agent. Logged to the audit trail. |
| 4b | `POST http://localhost:8000/approvals/{approval_id}/reject` body `{"decided_by", "reason"}` | Human rejects a request. No money moves. Logged to the audit trail. |
| 5 | `GET http://localhost:8000/cash` | Current checking `balance` from `cash_accounts`, plus pending approvals total, balance if all pending were paid, and payment history. |
| 6 | `POST http://localhost:8000/reset` | Copies the untouched `data/campus_customs.db` over `data/campus_customs_new.db` for a fresh run, clears run history, and returns the restored cash ($3,400). 409 while agents are running. |
| — | `GET http://localhost:8000/` | Health check and model name (`openai-gpt-luna-6`). |

## Route test log (2026-10-14, no agent runs, no tokens spent)

- `GET /tickets` → 3 tickets (101, 102, 103), all `open`. `GET /cash` → checking $3,400. `GET /events` → empty to start.
- `GET /tickets/999` and `POST /tickets/999/run` → 404 "No ticket with id=999".
- With two test requests filed directly over MCP (invoice 501 $840, PO 12 hoodies $264):
  - Approve the PO first → 409, refused because Bulldog has open invoice 501.
  - Approve with `approved_by="accounting"` → 409, "agents cannot approve payments".
  - Approve the invoice as Daria → 200, checking $3,400 → **$2,560**, invoice 501 `paid`, `payments` row with `approved_by = Daria`.
  - Reject the PO → 200, no money moved.
- `GET /events?agent=human` showed each approve and reject attempt. `POST /reset` → checking back to $3,400, and the working copy's checksum matches the original again.
