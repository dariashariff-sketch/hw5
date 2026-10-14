"""Accounting agent. Watches cash, invoices, costs and margins; prepares payments and purchase orders for human approval.

Prompt: backend/prompts/accounting.md
MCP tools: see ROLE_TOOLS["accounting"] in backend/mcp_tools.py
"""

from ..models import SpecialistReport
from .base import build_agent

ROLE = "accounting"
agent = build_agent(ROLE, SpecialistReport)
