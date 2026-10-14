"""What every Campus Customs agent shares: the model, the MCP toolset, the
`ask_teammate` delegation tool, and the audited agent loop.

Full connectivity: every agent has `ask_teammate`, so any role can hand work to, or ask
for help from, any other role. Guards: no asking yourself, no cycles (you can't ask a
role already in the chain), a maximum chain depth, and one shared token budget per ticket.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
    RetryPromptPart,
)

from ..audit import append_event
from ..config import MAX_DELEGATION_DEPTH, MODEL_SETTINGS, PROMPTS_DIR, build_model, ticket_usage_limits
from ..mcp_tools import SHOP_TOOLSET, toolset_for
from ..models import ROLES, Role, TeamDeps

# role -> Agent, filled in as each agent module is imported (see agents/__init__.py)
REGISTRY: dict[Role, Agent[TeamDeps, Any]] = {}

ROLE_TITLES: dict[Role, str] = {
    "boss": "Boss",
    "inventory": "Inventory",
    "accounting": "Accounting",
    "facilities": "Facilities",
    "customer_service": "Customer Service",
}

_MODEL = build_model()


def load_prompt(role: Role) -> str:
    return (PROMPTS_DIR / f"{role}.md").read_text(encoding="utf-8")


def build_agent(role: Role, output_type: type) -> Agent[TeamDeps, Any]:
    """Create one team member: its prompt file, the shared model, its MCP tools, and
    the `ask_teammate` tool. Registers it so teammates can find it by role."""
    agent: Agent[TeamDeps, Any] = Agent(
        _MODEL,
        name=role,
        instructions=load_prompt(role),
        deps_type=TeamDeps,
        output_type=output_type,
        toolsets=[toolset_for(role, SHOP_TOOLSET)],
        model_settings=MODEL_SETTINGS,
        retries=2,
    )

    @agent.instructions
    def run_context(ctx: RunContext[TeamDeps]) -> str:
        others = [r for r in ROLES if r != ctx.deps.role]
        return (
            f"You are the {ROLE_TITLES[ctx.deps.role]} agent (role id `{ctx.deps.role}`). "
            f"Current ticket: {ctx.deps.ticket_id}. "
            f"Request chain so far: {' -> '.join(ctx.deps.chain)}. "
            f"Teammates you can ask with ask_teammate: {', '.join(others)}. "
            f"You cannot ask anyone already in the chain, and the chain may be at most "
            f"{MAX_DELEGATION_DEPTH + 1} roles long."
        )

    @agent.tool
    async def ask_teammate(ctx: RunContext[TeamDeps], teammate: Role, request: str) -> dict:
        """Hand a piece of work to a teammate, or ask them for help, and get their report back.

        teammate: one of boss, inventory, accounting, facilities, customer_service.
        request: exactly what you need from them, including the ticket facts they need
        (sku, size, qty, invoice id, lease id, amounts) and what you already know.
        """
        me = ctx.deps
        if teammate == me.role:
            return {"error": "You can't ask yourself; do the work directly."}
        if teammate in me.chain:
            return {
                "error": f"{teammate} is already in this request chain ({' -> '.join(me.chain)}). "
                "Put your question in your report instead so they see it when you return."
            }
        if me.depth + 1 > MAX_DELEGATION_DEPTH:
            return {"error": "Delegation chain is at its maximum depth. Finish with what you have."}

        child = me.child(teammate)
        append_event(me, -1, "delegate", {"to": teammate, "request": request})
        prompt = (
            f"Ticket {me.ticket_id}. Request from {ROLE_TITLES[me.role]} "
            f"(chain: {' -> '.join(child.chain)}):\n\n{request}"
        )
        try:
            report = await run_agent(teammate, prompt, child)
        except Exception as exc:  # budget hit or model error inside the teammate
            append_event(child, -1, "error", {"type": type(exc).__name__, "message": str(exc)})
            raise
        return report.model_dump()

    REGISTRY[role] = agent
    return agent


def _describe_parts(parts) -> list[dict]:
    out = []
    for p in parts:
        if isinstance(p, ToolCallPart):
            out.append({"type": "tool_call", "tool": p.tool_name, "tool_call_id": p.tool_call_id, "args": p.args})
        elif isinstance(p, ToolReturnPart):
            out.append({"type": "tool_result", "tool": p.tool_name, "tool_call_id": p.tool_call_id, "content": p.content})
        elif isinstance(p, RetryPromptPart):
            out.append({"type": "retry", "tool": p.tool_name, "content": p.content})
        elif isinstance(p, TextPart):
            out.append({"type": "text", "content": p.content})
        elif isinstance(p, UserPromptPart):
            out.append({"type": "user_prompt", "content": p.content})
        else:
            out.append({"type": getattr(p, "part_kind", type(p).__name__)})
    return out


async def run_agent(role: Role, prompt: str, deps: TeamDeps):
    """Run one agent's loop step by step, appending every step to the audit trail.

    The loop is: model request -> model response (text and/or tool calls) -> tool results
    -> next model request ... until the agent returns its typed output.
    """
    agent = REGISTRY[role]
    append_event(deps, 0, "run_start", {"prompt": prompt, "model": _MODEL.model_name})
    step = 0
    async with agent.iter(
        prompt, deps=deps, usage=deps.usage, usage_limits=ticket_usage_limits()
    ) as run:
        async for node in run:
            step += 1
            if Agent.is_user_prompt_node(node):
                append_event(deps, step, "user_prompt", {"prompt": node.user_prompt})
            elif Agent.is_model_request_node(node):
                req: ModelRequest = node.request
                append_event(deps, step, "model_request", {"parts": _describe_parts(req.parts)})
            elif Agent.is_call_tools_node(node):
                resp: ModelResponse = node.model_response
                append_event(
                    deps,
                    step,
                    "model_response",
                    {
                        "model_name": resp.model_name,
                        "parts": _describe_parts(resp.parts),
                        "response_usage": {
                            "input_tokens": resp.usage.input_tokens,
                            "output_tokens": resp.usage.output_tokens,
                        },
                    },
                )
            elif Agent.is_end_node(node):
                append_event(deps, step, "run_end", {"output": node.data.output.model_dump()})
        return run.result.output
