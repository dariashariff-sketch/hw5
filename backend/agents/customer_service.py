"""Customer Service agent. Drafts kind, clear customer messages that stay on the board and are never sent.

Prompt: backend/prompts/customer_service.md
MCP tools: see ROLE_TOOLS["customer_service"] in backend/mcp_tools.py
"""

from ..models import SpecialistReport
from .base import build_agent

ROLE = "customer_service"
agent = build_agent(ROLE, SpecialistReport)
