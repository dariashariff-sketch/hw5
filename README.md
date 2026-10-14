# Campus Customs Multi-Agent Operations

Homework 5 · Foundations of AI · Yale SOM

A five-agent team runs the Campus Customs shop. Tickets (customer orders, rent notices, discount requests) land on a board. **Boss** reads each one and brings in only the teammates it needs: **Inventory**, **Accounting**, **Facilities** and **Customer Service**. A human watches the agents work on a React dashboard and approves every payment before any money moves.

There are three pieces:

| Piece | Folder | What it does |
|---|---|---|
| MCP server | `mcp_server/` | The only shop-tools layer: 15 FastMCP tools over the SQLite database. |
| Backend | `backend/` | Pydantic AI agent team and FastAPI routes. Every agent uses `openai-gpt-luna-6` through Portkey. |
| Dashboard | `frontend/` | React + Vite + TypeScript board: pick a ticket, watch the agents, approve payments. |

## Data: two database files

- `data/campus_customs.db`: the **original**. Never modified. It's the source for every reset.
- `data/campus_customs_new.db`: the **working copy**. The MCP server, agents and backend only read and write this file.

The committed working copy is the state after our graded run in Problem 9: checking is $152.00 and 3 payments were approved by a human. **Reset it before your own run** (see below).

## Setup (once)

Requires Python 3.12+ and Node 20+.

```bash
pip install -r requirements.txt
```

```bash
cd frontend
npm install
```

Copy `.env.example` to `.env` in the project root and put your Portkey key in it. The real `.env` is git-ignored.

```bash
cp .env.example .env
```

```
PORTKEY_API_KEY=your-portkey-api-key
```

## Running it

### 1. Copy the original DB to the working copy (a clean run)

Do this whenever you want to start fresh. It makes `campus_customs_new.db` identical to `campus_customs.db`: checking back to $3,400, all three tickets open, and no approvals, payments or board posts. Use any one of these:

```bash
python -m backend.team --reset
```

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

You can also click **Reset database** on the dashboard, or call `POST http://localhost:8000/reset`. Only use the plain `cp` while nothing is running. The other two are safe while the board is open.

### 2. The MCP server

You don't have to start it yourself. The backend launches `mcp_server/server.py` over stdio when it starts, and the agents use it from there. To run or inspect it on its own:

```bash
python mcp_server/server.py
```

`.mcp.json` registers it as `campus-customs` for MCP clients such as Claude Code. Tool details are in `mcp_server/README.md`.

### 3. Start the FastAPI backend (http://localhost:8000)

From the `backend/` folder:

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Interactive route docs are at http://localhost:8000/docs. The one-line list is in `output/runs.md`.

### 4. Start the React board (http://localhost:5173)

In a second terminal:

```bash
cd frontend
npm run dev
```

This opens the board in your browser. It calls the backend at `http://localhost:8000`, which allows this origin through CORS.

### 5. A full three-ticket run

1. **Reset the DB first** (step 1). Checking should show **$3,400.00**.
2. On the board, select **#101** and press **Start the team**. Watch the Team room and Live feed. When the ticket stamps **Resolved**, do the same for **#102**, then **#103**. Run them one at a time, in order, because they share one checking account.
3. Type your name in **"You're approving as"**, then **press and hold** each request in **Needs your OK**. Approve **invoice 501 first**: Bulldog Print Co won't ship the tee PO until that invoice is paid, and the pay tool will refuse the PO until then.
4. Watch checking drop on the Cash card and in the Cash timeline.

Without the board, this command resets and then runs all three tickets. Approvals still happen on the dashboard or through `POST /approvals/{id}/approve`.

```bash
python -m backend.team --all
```

## Rules the code enforces

- **Human approval for all money.** Agents can only *request* payments and purchase orders. Money moves only in the `approve_and_pay` MCP tool, which no agent can call. A human triggers it from the dashboard, and the approver's name is saved on every payment.
- **No negative balances.** The pay tool refuses any payment the checking balance can't cover. Cash only goes out; revenue isn't modeled.
- **Vendor rule.** A vendor with an open, unpaid invoice won't ship, so its POs can't be paid until that invoice is.
- **Database facts only.** "Today" is `desk.date_today` (2026-08-31). Lead times come from `vendors.lead_days`. Dollar amounts are read from the database, never typed by the model.
- **Nothing is sent.** Customer and vendor messages are drafts on the board.
- **One model.** `openai-gpt-luna-6` through Portkey (`PORTKEY_API_KEY`) is set in exactly one place, `backend/config.py`.
- **Token limits.** Each ticket gets 150,000 tokens, 30 model requests and 60 tool calls. A full run is capped at 400,000 tokens.
- **Audit trail.** Every agent step and human action is appended to `output/audit_trail.json`, which is never wiped.

## Layout

```
.
├── AI_prompts.md            every prompt, by problem
├── README.md                this file
├── requirements.txt
├── .env.example             copy to .env (git-ignored) and add PORTKEY_API_KEY
├── .gitignore
├── .mcp.json                registers the MCP server
├── data/
│   ├── campus_customs.db        original (never modified)
│   └── campus_customs_new.db    working copy
├── mcp_server/
│   ├── server.py            15 MCP tools
│   └── README.md
├── backend/
│   ├── main.py              FastAPI routes
│   ├── models.py            data types
│   ├── config.py            model, Portkey, paths, token limits
│   ├── mcp_tools.py         which MCP tools each role may call
│   ├── audit.py             append-only audit trail
│   ├── team.py              run tickets, reset the DB (CLI)
│   ├── agents/              boss.py, inventory.py, accounting.py, facilities.py, customer_service.py, base.py
│   └── prompts/             boss.md, inventory.md, accounting.md, facilities.md, customer_service.md
├── frontend/                React + Vite + TypeScript board
└── output/
    ├── harness.md           tables, tools, agents, routes, dashboard, safety
    ├── mcp_smoke.json       MCP tool test against the database
    ├── desk_tickets.html    plan vs actual per ticket, Cash, Reflection
    ├── runs.md              API routes
    ├── design.md            dashboard design
    ├── resolved_tickets.json
    ├── resolved_board.html  board screenshots for each resolved ticket
    ├── audit_trail.json
    └── github_url.txt
```
