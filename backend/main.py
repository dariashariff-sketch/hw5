"""Campus Customs Multi-Agent Operations — FastAPI backend for the dashboard.

Start it from the backend/ folder:

    uvicorn main:app --reload --port 8000

Every shop fact and every database write goes through the MCP server
(mcp_server/server.py). This file only routes HTTP calls to MCP tools, starts agent
runs, and reads the audit trail.

Money moves in exactly one place: POST /approvals/{id}/approve, which a human triggers
by clicking Approve on the dashboard. Agents can only prepare requests.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

# Allow `uvicorn main:app` from inside backend/ while keeping backend a package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from backend.audit import append_human_event, read_events  # noqa: E402
from backend.config import MODEL_NAME, ORIGINAL_DB, WORKING_DB  # noqa: E402
from backend.mcp_tools import SHOP_TOOLSET  # noqa: E402
from backend.models import TicketRunResult  # noqa: E402
from backend.team import call_tool, mcp_session, reset_working_db, run_ticket  # noqa: E402

# run_id -> {"run_id", "ticket_id", "status": running|done|failed, "started_at", "result"}
RUNS: dict[str, dict] = {}
_TASKS: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One MCP connection for the routes and one shared by the agents, opened once.
    stack = AsyncExitStack()
    await stack.enter_async_context(mcp_session())
    await stack.enter_async_context(SHOP_TOOLSET)
    try:
        yield
    finally:
        # Don't let a slow MCP subprocess shutdown block `--reload` (seen on Windows).
        try:
            await asyncio.wait_for(stack.aclose(), timeout=5)
        except Exception:
            pass


app = FastAPI(
    title="Campus Customs Multi-Agent Operations API",
    description="Backend for the Campus Customs dashboard. All shop data goes through the MCP server.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _running_ticket_ids() -> set[int]:
    return {r["ticket_id"] for r in RUNS.values() if r["status"] == "running"}


def _check(result: dict, status_code: int = 400) -> dict:
    """MCP tools report refusals as {"error": ...}; turn those into HTTP errors."""
    if "error" in result:
        raise HTTPException(status_code=status_code, detail=result)
    return result


# --------------------------------------------------------------------------- 1. tickets


def _team_finished_ticket_ids() -> dict[int, dict]:
    """Tickets whose latest agent run (since the last reset) finished with a final decision.
    Read from the audit trail so it survives a server restart."""
    finished: dict[int, dict] = {}
    for e in read_events():
        if e["event"] == "reset_database":
            finished.clear()
        elif e["event"] == "ticket_done":
            if e["detail"].get("ok"):
                finished[e["ticket_id"]] = e["detail"]
            else:
                finished.pop(e["ticket_id"], None)
    return finished


@app.get("/tickets")
async def list_tickets():
    """All tickets with their status and whether each is open or resolved.

    A ticket is `resolved` once the team's run on it finishes with Boss's final decision
    (or if the database already says resolved). `status` keeps Boss's exact database status,
    e.g. waiting_on_human when a payment still needs a human click.
    """
    data = await call_tool("list_all_tickets")
    running = _running_ticket_ids()
    finished = _team_finished_ticket_ids()
    tickets = []
    for t in data["tickets"]:
        done = finished.get(t["id"])
        resolved = t["is_resolved"] or (done is not None and t["id"] not in running)
        tickets.append({
            "id": t["id"],
            "type": t["type"],
            "requester": t["requester"],
            "subject": t["subject"],
            "status": t["status"],
            "state": "resolved" if resolved else "open",
            "agents_running": t["id"] in running,
            "last_run_id": done["run_id"] if done else None,
            "tokens_used": done["total_tokens"] if done else None,
            "created_at": t["created_at"],
        })
    data["open_count"] = sum(t["state"] == "open" for t in tickets)
    data["resolved_count"] = len(tickets) - data["open_count"]
    return {"shop_today": data["shop_today"], "open_count": data["open_count"],
            "resolved_count": data["resolved_count"], "tickets": tickets}


@app.get("/tickets/{ticket_id}")
async def ticket_details(ticket_id: int):
    """One ticket with its linked rows, board posts (drafts, notes, decisions), approvals and POs."""
    return _check(await call_tool("get_ticket_details", {"ticket_id": ticket_id}), 404)


# --------------------------------------------------------------------------- 2. run the team


class RunRequest(BaseModel):
    wait: bool = Field(False, description="True: block until the run finishes and return the result")


async def _run_in_background(run_id: str, ticket_id: int) -> TicketRunResult:
    try:
        result = await run_ticket(ticket_id, run_id)
        RUNS[run_id].update(status="done" if result.ok else "failed", result=result.model_dump(),
                            finished_at=_now())
        return result
    except Exception as exc:  # run_ticket already escalates; this is a last resort
        RUNS[run_id].update(status="failed", result={"error": f"{type(exc).__name__}: {exc}"},
                            finished_at=_now())
        raise


@app.post("/tickets/{ticket_id}/run", status_code=202)
async def run_team_on_ticket(ticket_id: int, body: RunRequest | None = None):
    """Start the agent team (Boss first) on one ticket. Watch progress with GET /events."""
    _check(await call_tool("get_ticket_details", {"ticket_id": ticket_id}), 404)
    if ticket_id in _running_ticket_ids():
        raise HTTPException(409, f"The team is already working on ticket {ticket_id}")

    run_id = uuid.uuid4().hex[:12]
    RUNS[run_id] = {"run_id": run_id, "ticket_id": ticket_id, "status": "running",
                    "started_at": _now(), "model": MODEL_NAME, "result": None}
    task = asyncio.create_task(_run_in_background(run_id, ticket_id))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)

    if body and body.wait:
        try:
            await task
        except Exception:
            pass
    return RUNS[run_id]


@app.get("/runs")
async def list_runs():
    """Every run started since the server came up, newest first."""
    return sorted(RUNS.values(), key=lambda r: r["started_at"], reverse=True)


@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    """Status (running / done / failed) and final result of one run."""
    if run_id not in RUNS:
        raise HTTPException(404, f"No run {run_id}")
    return RUNS[run_id]


# --------------------------------------------------------------------------- 3. agent events


def _summarize(seq: int, e: dict) -> dict:
    """Turn one audit-trail step into what the board shows: who said what, which tools."""
    parts = e.get("detail", {}).get("parts", [])
    out = {
        "seq": seq,
        "ts": e["ts"],
        "run_id": e["run_id"],
        "ticket_id": e["ticket_id"],
        "agent": e["agent"],
        "chain": e["chain"],
        "event": e["event"],
        "said": [p["content"] for p in parts if p.get("type") == "text" and p.get("content")],
        "tool_calls": [{"tool": p["tool"], "args": p.get("args")} for p in parts if p.get("type") == "tool_call"],
        "tool_results": [{"tool": p["tool"], "content": p.get("content")} for p in parts if p.get("type") == "tool_result"],
        "total_tokens": e.get("usage", {}).get("total_tokens"),
    }
    d = e.get("detail", {})
    if e["event"] == "delegate":
        out["said"] = [f"Asked {d.get('to')}: {d.get('request')}"]
        out["to"] = d.get("to")
    elif e["event"] == "run_start":
        out["task"] = d.get("prompt")
    elif e["event"] == "run_end":
        out["output"] = d.get("output")
    elif e["event"] in ("error", "ticket_done") or e["agent"] == "human":
        out["detail"] = d
    return out


@app.get("/events")
async def recent_events(
    limit: int = Query(100, ge=1, le=1000),
    after: int | None = Query(None, description="Only events with seq greater than this (for polling)"),
    ticket_id: int | None = None,
    run_id: str | None = None,
    agent: str | None = None,
):
    """Recent agent steps from output/audit_trail.json: what each agent said, did, and which tools it used."""
    events = [_summarize(i, e) for i, e in enumerate(read_events())]
    if after is not None:
        events = [e for e in events if e["seq"] > after]
    if ticket_id is not None:
        events = [e for e in events if e["ticket_id"] == ticket_id]
    if run_id:
        events = [e for e in events if e["run_id"] == run_id]
    if agent:
        events = [e for e in events if e["agent"] == agent]
    events = events[-limit:]
    return {"last_seq": events[-1]["seq"] if events else after, "events": events}


# --------------------------------------------------------------------------- 4. human approvals


class Decision(BaseModel):
    approved_by: str = Field(..., min_length=1, description="Name of the human approving")


class Rejection(BaseModel):
    decided_by: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


@app.get("/approvals")
async def pending_approvals():
    """Payment and purchase-order requests the agents prepared, waiting for a human."""
    return await call_tool("list_pending_approvals")


@app.post("/approvals/{approval_id}/approve")
async def approve(approval_id: int, body: Decision):
    """HUMAN ONLY. Approve and pay one request. This is the only route that changes cash."""
    result = await call_tool("approve_and_pay", {"approval_id": approval_id, "approved_by": body.approved_by})
    append_human_event(result.get("ticket_id"), "approve_and_pay",
                       {"approval_id": approval_id, "result": result}, body.approved_by)
    return _check(result, 409)


@app.post("/approvals/{approval_id}/reject")
async def reject(approval_id: int, body: Rejection):
    """HUMAN ONLY. Reject a request. Moves no money."""
    result = await call_tool("reject_approval", {"approval_id": approval_id, "decided_by": body.decided_by,
                                                 "reason": body.reason})
    append_human_event(result.get("ticket_id"), "reject_approval",
                       {"approval_id": approval_id, "result": result}, body.decided_by)
    return _check(result, 409)


# --------------------------------------------------------------------------- 5. cash


@app.get("/cash")
async def checking_balance():
    """Current checking balance from cash_accounts, plus what is pending approval against it."""
    data = await call_tool("get_cash_position")
    checking = next((a for a in data["accounts"] if a["account"] == "checking"), None)
    if checking is None:
        raise HTTPException(404, "No checking account in cash_accounts")
    return {
        "account": "checking",
        "balance": checking["balance"],
        "as_of": checking["as_of"],
        "pending_approvals_total": checking["pending_approvals_total"],
        "balance_if_all_pending_paid": checking["balance_if_all_pending_paid"],
        "payments": data["payments"],
    }


# --------------------------------------------------------------------------- 6. reset


@app.post("/reset")
async def reset_database():
    """Restore data/campus_customs_new.db from the untouched original for a fresh run."""
    if _running_ticket_ids():
        raise HTTPException(409, "Agents are still running; wait for them to finish before resetting")
    reset_working_db()
    RUNS.clear()
    append_human_event(None, "reset_database", {"from": ORIGINAL_DB.name, "to": WORKING_DB.name}, "dashboard")
    return {"reset": True, "working_db": WORKING_DB.name, "copied_from": ORIGINAL_DB.name,
            "cash": await checking_balance()}


@app.get("/")
async def root():
    return {"app": "Campus Customs Multi-Agent Operations", "model": MODEL_NAME, "docs": "/docs"}
