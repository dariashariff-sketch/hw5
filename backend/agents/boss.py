"""Boss agent. Reads every ticket, routes it to the right teammates, and makes the final call.

Prompt: backend/prompts/boss.md
MCP tools: see ROLE_TOOLS["boss"] in backend/mcp_tools.py
"""

from ..models import TicketResolution
from .base import build_agent

ROLE = "boss"
agent = build_agent(ROLE, TicketResolution)
