"""Connects the agents to the Campus Customs MCP server.

This is not a second tools layer: every shop fact and every write goes through
mcp_server/server.py over MCP. This module only decides *which* of the server's tools
each role may see, and stamps the caller's real role onto write calls so an agent can't
claim to be someone else.
"""

from __future__ import annotations

from typing import Any

from fastmcp.client.transports import PythonStdioTransport
from pydantic_ai import RunContext
from pydantic_ai.mcp import CallToolFunc, MCPToolset, ToolResult

from .config import MCP_INIT_TIMEOUT, MCP_SERVER_SCRIPT, ROOT
from .models import Role, TeamDeps

# Tools no agent may ever call. Only the human dashboard uses them.
HUMAN_ONLY_TOOLS = frozenset({"approve_and_pay", "reject_approval"})

_READ_COMMON = {"get_ticket_details", "post_to_board"}

ROLE_TOOLS: dict[Role, frozenset[str]] = {
    "boss": frozenset(
        _READ_COMMON
        | {"list_open_tickets", "get_cash_position", "list_pending_approvals", "update_ticket_status"}
    ),
    "inventory": frozenset(_READ_COMMON | {"check_stock_and_vendors", "get_pricing_and_margin"}),
    "accounting": frozenset(
        _READ_COMMON
        | {
            "get_cash_position",
            "get_invoice_status",
            "get_pricing_and_margin",
            "get_lease_rent_status",
            "check_stock_and_vendors",
            "list_pending_approvals",
            "request_payment",
            "request_purchase_order",
        }
    ),
    "facilities": frozenset(_READ_COMMON | {"get_lease_rent_status", "get_cash_position"}),
    "customer_service": frozenset(
        _READ_COMMON | {"check_stock_and_vendors", "get_pricing_and_margin"}
    ),
}

assert not any(tools & HUMAN_ONLY_TOOLS for tools in ROLE_TOOLS.values())

# Arguments the server uses to know who is acting. Always overwritten with the real role.
_IDENTITY_ARGS = ("author_role", "requested_by", "updated_by")


async def _guard_tool_call(
    ctx: RunContext[TeamDeps], call_tool: CallToolFunc, name: str, args: dict[str, Any]
) -> ToolResult:
    role = ctx.deps.role
    if name in HUMAN_ONLY_TOOLS or name not in ROLE_TOOLS[role]:
        return {"error": f"Refused: role {role!r} is not allowed to call {name!r}"}
    args = dict(args)
    for key in _IDENTITY_ARGS:
        if key in args:
            args[key] = role
    return await call_tool(name, args)


def build_shop_toolset() -> MCPToolset:
    """One stdio connection to the MCP server, shared by the whole team."""
    transport = PythonStdioTransport(script_path=str(MCP_SERVER_SCRIPT), cwd=str(ROOT))
    return MCPToolset(
        transport, process_tool_call=_guard_tool_call, id="campus_customs", init_timeout=MCP_INIT_TIMEOUT
    )


SHOP_TOOLSET = build_shop_toolset()


def toolset_for(role: Role, shop: MCPToolset):
    """The subset of MCP tools a role is allowed to see."""
    allowed = ROLE_TOOLS[role]
    return shop.filtered(lambda ctx, tool_def: tool_def.name in allowed)
