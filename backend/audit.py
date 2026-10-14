"""Append-only audit trail at output/audit_trail.json.

The file is a JSON array. Each call appends one event and rewrites the file atomically.
Existing events are never removed; if the file can't be parsed we stop rather than
overwrite it.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from pydantic_ai.usage import RunUsage

from .config import AUDIT_TRAIL
from .models import AuditEvent, TeamDeps

_LOCK = threading.Lock()
MAX_FIELD_CHARS = 4000


def _clip(value: Any) -> Any:
    """Keep the trail readable: long strings are cut, with the original length noted."""
    if isinstance(value, str) and len(value) > MAX_FIELD_CHARS:
        return value[:MAX_FIELD_CHARS] + f"... [truncated, {len(value)} chars]"
    if isinstance(value, dict):
        return {k: _clip(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clip(v) for v in value]
    return value


def usage_dict(usage: RunUsage) -> dict:
    return {
        "requests": usage.requests,
        "tool_calls": usage.tool_calls,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
    }


def append_event(deps: TeamDeps, step: int, event: str, detail: dict) -> None:
    _append(
        AuditEvent(
            ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            run_id=deps.run_id,
            ticket_id=deps.ticket_id,
            agent=deps.role,
            chain=list(deps.chain),
            depth=deps.depth,
            step=step,
            event=event,
            detail=_clip(json.loads(json.dumps(detail, default=str))),
            usage=usage_dict(deps.usage),
        ).model_dump()
    )


def append_human_event(ticket_id: int | None, event: str, detail: dict, who: str) -> None:
    """Record a human action from the dashboard (approve, reject, reset) in the same trail."""
    _append(
        AuditEvent(
            ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            run_id="human",
            ticket_id=ticket_id or 0,
            agent="human",
            chain=[f"human:{who}"],
            depth=0,
            step=0,
            event=event,
            detail=_clip(json.loads(json.dumps(detail, default=str))),
            usage={},
        ).model_dump()
    )


def read_events() -> list[dict]:
    with _LOCK:
        if not AUDIT_TRAIL.exists() or AUDIT_TRAIL.stat().st_size == 0:
            return []
        return json.loads(AUDIT_TRAIL.read_text(encoding="utf-8"))


def _append(record: dict) -> None:
    with _LOCK:
        AUDIT_TRAIL.parent.mkdir(parents=True, exist_ok=True)
        events: list = []
        if AUDIT_TRAIL.exists() and AUDIT_TRAIL.stat().st_size > 0:
            events = json.loads(AUDIT_TRAIL.read_text(encoding="utf-8"))
            if not isinstance(events, list):
                raise ValueError(f"{AUDIT_TRAIL} is not a JSON array; refusing to overwrite it")
        events.append(record)
        tmp = AUDIT_TRAIL.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(events, indent=2), encoding="utf-8")
        os.replace(tmp, AUDIT_TRAIL)
