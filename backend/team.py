"""Runs the Campus Customs team on tickets.

    python -m backend.team --ticket 101      # one ticket, on the current working copy
    python -m backend.team --all             # reset the working copy, then every open ticket

A full run (--all) always resets data/campus_customs_new.db from the untouched original
data/campus_customs.db first.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sqlite3
import uuid
from contextlib import asynccontextmanager

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport
from pydantic_ai.usage import RunUsage

from .agents import run_agent
from .audit import append_event
from .config import MCP_INIT_TIMEOUT, MCP_SERVER_SCRIPT, ORIGINAL_DB, ROOT, WORKING_DB
from .mcp_tools import SHOP_TOOLSET
from .models import TeamDeps, TicketRunResult

# Whole-run ceiling across all tickets. A run stops starting new tickets once it is spent.
RUN_TOTAL_TOKENS_LIMIT = int(os.getenv("CC_RUN_TOKEN_LIMIT", "400000"))


def reset_working_db() -> None:
    """Make the working copy identical to the original database again.

    Uses SQLite's backup API rather than deleting the file: on Windows a file that the
    dashboard is reading can't be deleted, but backup safely overwrites it in place
    (including dropping the team tables the original doesn't have).
    """
    if not ORIGINAL_DB.exists():
        raise FileNotFoundError(ORIGINAL_DB)
    if not WORKING_DB.exists():
        shutil.copy2(ORIGINAL_DB, WORKING_DB)
        return
    src = sqlite3.connect(f"file:{ORIGINAL_DB.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(WORKING_DB, timeout=30)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()


def _mcp_client() -> Client:
    return Client(
        PythonStdioTransport(script_path=str(MCP_SERVER_SCRIPT), cwd=str(ROOT)),
        init_timeout=MCP_INIT_TIMEOUT,
    )


# A long-lived MCP connection, opened by the FastAPI app at startup (see mcp_session).
# Without it each call starts its own short-lived MCP server process.
_session: Client | None = None


@asynccontextmanager
async def mcp_session():
    """Keep one MCP connection open for direct (non-agent) calls, e.g. from the API."""
    global _session
    async with _mcp_client() as client:
        _session = client
        try:
            yield client
        finally:
            _session = None


async def call_tool(tool: str, args: dict | None = None) -> dict:
    """Call one MCP tool directly. Used for things only humans or the runner do."""
    args = args or {}
    if _session is not None:
        result = await _session.call_tool(tool, args)
    else:
        async with _mcp_client() as client:
            result = await client.call_tool(tool, args)
    return result.structured_content or json.loads(result.content[0].text)



async def open_ticket_ids() -> list[int]:
    data = await call_tool("list_open_tickets", {})
    return [t["id"] for t in data["tickets"]]


async def _escalate(ticket_id: int, reason: str) -> None:
    """If the team fails (budget hit, model error), hand the ticket to a human via MCP."""
    await call_tool(
        "post_to_board",
        {"ticket_id": ticket_id, "author_role": "boss", "kind": "escalation", "content": reason},
    )
    await call_tool(
        "update_ticket_status",
        {"ticket_id": ticket_id, "status": "waiting_on_human", "note": reason, "updated_by": "boss"},
    )


async def run_ticket(ticket_id: int, run_id: str | None = None) -> TicketRunResult:
    run_id = run_id or uuid.uuid4().hex[:12]
    deps = TeamDeps(run_id=run_id, ticket_id=ticket_id, role="boss", usage=RunUsage(), chain=["boss"])
    prompt = (
        f"New ticket on the board: {ticket_id}. Read it, bring in the teammates it needs, "
        f"make the final call, post your decision, set the ticket status, and return your "
        f"TicketResolution."
    )
    try:
        async with SHOP_TOOLSET:
            resolution = await run_agent("boss", prompt, deps)
        result = TicketRunResult(run_id=run_id, ticket_id=ticket_id, ok=True, resolution=resolution)
    except Exception as exc:
        reason = f"Agent team stopped ({type(exc).__name__}: {exc}). A human needs to review this ticket."
        append_event(deps, -1, "error", {"type": type(exc).__name__, "message": str(exc)})
        await _escalate(ticket_id, reason)
        result = TicketRunResult(run_id=run_id, ticket_id=ticket_id, ok=False, error=reason)

    result.total_tokens = deps.usage.total_tokens
    result.requests = deps.usage.requests
    result.tool_calls = deps.usage.tool_calls
    append_event(deps, -1, "ticket_done", result.model_dump())
    return result


async def run_all_open_tickets() -> list[TicketRunResult]:
    """Full run: reset the working copy, then work every open ticket oldest-first."""
    reset_working_db()
    run_id = uuid.uuid4().hex[:12]
    results: list[TicketRunResult] = []
    spent = 0
    for ticket_id in await open_ticket_ids():
        if spent >= RUN_TOTAL_TOKENS_LIMIT:
            await _escalate(ticket_id, f"Run token budget ({RUN_TOTAL_TOKENS_LIMIT}) used up before this ticket.")
            results.append(TicketRunResult(run_id=run_id, ticket_id=ticket_id, ok=False, error="run token budget exhausted"))
            continue
        r = await run_ticket(ticket_id, run_id)
        spent += r.total_tokens
        results.append(r)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Campus Customs agent team")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticket", type=int, help="work one ticket on the current working copy")
    group.add_argument("--all", action="store_true", help="reset the working copy and work every open ticket")
    group.add_argument("--reset", action="store_true", help="only reset the working copy")
    args = parser.parse_args()

    if args.reset:
        reset_working_db()
        print(f"Reset {WORKING_DB} from {ORIGINAL_DB}")
        return
    results = asyncio.run(run_all_open_tickets() if args.all else run_ticket(args.ticket))
    results = results if isinstance(results, list) else [results]
    print(json.dumps([r.model_dump() for r in results], indent=2))


if __name__ == "__main__":
    main()
