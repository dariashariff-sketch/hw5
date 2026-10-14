"""Inventory agent. Checks stock by SKU and size, spots shortfalls, and finds which vendor can restock and when.

Prompt: backend/prompts/inventory.md
MCP tools: see ROLE_TOOLS["inventory"] in backend/mcp_tools.py
"""

from ..models import SpecialistReport
from .base import build_agent

ROLE = "inventory"
agent = build_agent(ROLE, SpecialistReport)
