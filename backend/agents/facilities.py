"""Facilities agent. Owns the shop space: the lease, rent due dates, and lease or rent problems.

Prompt: backend/prompts/facilities.md
MCP tools: see ROLE_TOOLS["facilities"] in backend/mcp_tools.py
"""

from ..models import SpecialistReport
from .base import build_agent

ROLE = "facilities"
agent = build_agent(ROLE, SpecialistReport)
