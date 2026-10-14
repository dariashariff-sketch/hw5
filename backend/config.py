"""Shared settings for the Campus Customs agent team.

The model, gateway, file paths and token budgets live here and nowhere else, so every
agent is guaranteed to use the same single model through Portkey.
"""

import os
from pathlib import Path

from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

ROOT = Path(__file__).resolve().parent.parent

# Load PORTKEY_API_KEY (and optional CC_* limits) from a local .env if one exists.
# The real .env is git-ignored; see .env.example.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass
ORIGINAL_DB = ROOT / "data" / "campus_customs.db"
WORKING_DB = ROOT / "data" / "campus_customs_new.db"
MCP_SERVER_SCRIPT = ROOT / "mcp_server" / "server.py"
AUDIT_TRAIL = ROOT / "output" / "audit_trail.json"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
# Seconds to wait for the MCP server process to start (it takes a few seconds on Windows).
MCP_INIT_TIMEOUT = 60.0

# ---- the one and only model -------------------------------------------------------
MODEL_NAME = "openai-gpt-luna-6"  # "GPT-6 Luna", the only model any agent may use
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# ---- token / loop budgets -----------------------------------------------------------
# One budget per ticket, shared by Boss and every teammate it pulls in. If the team hits
# any of these the run stops, the ticket is escalated to a human, and the audit trail
# records why.
TICKET_TOTAL_TOKENS_LIMIT = int(os.getenv("CC_TICKET_TOKEN_LIMIT", "150000"))
TICKET_REQUEST_LIMIT = int(os.getenv("CC_TICKET_REQUEST_LIMIT", "30"))
TICKET_TOOL_CALLS_LIMIT = int(os.getenv("CC_TICKET_TOOL_CALLS_LIMIT", "60"))
MAX_OUTPUT_TOKENS_PER_RESPONSE = int(os.getenv("CC_MAX_OUTPUT_TOKENS", "4000"))
# How deep a chain of teammates can go (Boss -> Inventory -> Accounting is depth 2).
MAX_DELEGATION_DEPTH = 3


def ticket_usage_limits() -> UsageLimits:
    return UsageLimits(
        total_tokens_limit=TICKET_TOTAL_TOKENS_LIMIT,
        request_limit=TICKET_REQUEST_LIMIT,
        tool_calls_limit=TICKET_TOOL_CALLS_LIMIT,
    )


MODEL_SETTINGS = ModelSettings(max_tokens=MAX_OUTPUT_TOKENS_PER_RESPONSE)


def build_model() -> OpenAIChatModel:
    """GPT-6 Luna through the Portkey gateway, authenticated with PORTKEY_API_KEY."""
    api_key = os.environ.get("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set")
    client = AsyncOpenAI(
        base_url=PORTKEY_BASE_URL,
        api_key=api_key,
        default_headers={"x-portkey-api-key": api_key},
    )
    return OpenAIChatModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
