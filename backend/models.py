"""Data types shared by the Campus Customs agent team."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai.usage import RunUsage

Role = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
ROLES: tuple[Role, ...] = ("boss", "inventory", "accounting", "facilities", "customer_service")

TicketStatus = Literal["open", "in_progress", "waiting_on_human", "waiting_on_stock", "resolved"]


# --------------------------------------------------------------------------- run state


@dataclass
class TeamDeps:
    """Passed to every agent run. A teammate gets a child copy with its own role and a
    longer chain, but shares the same usage counter so the whole ticket stays in budget."""

    run_id: str
    ticket_id: int
    role: Role
    usage: RunUsage
    chain: list[Role] = field(default_factory=list)  # who asked whom, e.g. [boss, inventory]

    @property
    def depth(self) -> int:
        return len(self.chain) - 1

    def child(self, role: Role) -> "TeamDeps":
        return TeamDeps(
            run_id=self.run_id,
            ticket_id=self.ticket_id,
            role=role,
            usage=self.usage,
            chain=[*self.chain, role],
        )


# --------------------------------------------------------------------------- agent outputs


class Fact(BaseModel):
    """One fact an agent relied on, tied to the MCP tool that returned it."""

    statement: str = Field(description="The fact in plain words, with the exact number/date")
    source_tool: str = Field(description="MCP tool that returned it, e.g. check_stock_and_vendors")


class SpecialistReport(BaseModel):
    """What Inventory, Accounting, Facilities and Customer Service hand back."""

    role: Role
    ticket_id: int
    summary: str = Field(description="2-4 sentences: what you found and what you did")
    facts: list[Fact] = Field(description="Every number or date you relied on, with its source tool")
    actions_taken: list[str] = Field(
        default_factory=list,
        description="Board posts, payment requests or POs you filed, with their ids",
    )
    approval_ids: list[int] = Field(
        default_factory=list, description="Approval ids you created that wait on a human"
    )
    recommendation: str = Field(description="What you recommend Boss decides")
    blockers: list[str] = Field(default_factory=list, description="Anything stopping progress")
    needs_human_review: bool = Field(
        default=False, description="True if a human should look before anything else happens"
    )


class TicketResolution(BaseModel):
    """Boss's final call on a ticket."""

    ticket_id: int
    final_status: TicketStatus
    assigned_roles: list[Role] = Field(description="Teammates Boss brought in")
    decision: str = Field(description="The final call, in 2-5 sentences")
    rationale: str = Field(description="Why, citing the facts and rules that drove it")
    approval_ids: list[int] = Field(
        default_factory=list, description="Payment / PO approvals waiting on a human"
    )
    board_post_ids: list[int] = Field(
        default_factory=list, description="Drafts and notes posted for this ticket"
    )
    escalated_to_human: bool = Field(description="True if a human must review this ticket")
    next_steps: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- run results


class TicketRunResult(BaseModel):
    run_id: str
    ticket_id: int
    ok: bool
    resolution: TicketResolution | None = None
    error: str | None = None
    total_tokens: int = 0
    requests: int = 0
    tool_calls: int = 0


class AuditEvent(BaseModel):
    """One line in output/audit_trail.json: one step of one agent loop."""

    ts: str
    run_id: str
    ticket_id: int
    agent: str
    chain: list[str]
    depth: int
    step: int
    event: str  # run_start | user_prompt | model_request | model_response | tool_results | run_end | error | ...
    detail: dict
    usage: dict
