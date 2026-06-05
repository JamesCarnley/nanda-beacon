"""Plain-language intent extraction. Deterministic first; optional LLM fallback.

Beacon recognizes an ERC-8004 token id (integer), an Ethereum address (0x...),
or a NANDA agent slug, and maps the message to `enrich` or `evidence_check`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_ADDR_RE = re.compile(r"0x[0-9a-fA-F]{40}")
_TOKEN_RE = re.compile(r"\b(\d{1,7})\b")
_SLUG_RE = re.compile(r"agent[:\s]+([a-z0-9][a-z0-9\-_]{1,40})", re.IGNORECASE)
_MIN_INT_RE = re.compile(r"(?:min[_\s]?interactions|at least|over)[=\s]+(\d+)", re.IGNORECASE)
_EVIDENCE_RE = re.compile(r"evidence[-_\s]?check|threshold|at least|meets", re.IGNORECASE)


@dataclass
class Intent:
    skill: str  # "enrich" | "evidence_check" | "unknown"
    agent_id: int | str | None = None
    params: dict = field(default_factory=dict)


def _extract_agent_id(message: str) -> int | str | None:
    m = _ADDR_RE.search(message)
    if m:
        return m.group(0)
    # prefer an explicit "agent <slug>" that isn't purely numeric
    m = _SLUG_RE.search(message)
    if m and not m.group(1).isdigit():
        return m.group(1)
    # mask the threshold number's span so it is never mistaken for the agent id
    # (e.g. "at least 10 for agent 17" must resolve to 17, not 10)
    masked = message
    mi = _MIN_INT_RE.search(message)
    if mi:
        s, e = mi.span(1)
        masked = message[:s] + (" " * (e - s)) + message[e:]
    m = _TOKEN_RE.search(masked)
    if m:
        return int(m.group(1))
    return None


def extract_intent(message: str) -> Intent:
    agent_id = _extract_agent_id(message)

    if _EVIDENCE_RE.search(message):
        params: dict = {}
        mi = _MIN_INT_RE.search(message)
        if mi:
            params["min_interactions"] = int(mi.group(1))
        return Intent(skill="evidence_check", agent_id=agent_id, params=params)

    if agent_id is not None:
        return Intent(skill="enrich", agent_id=agent_id)

    return Intent(skill="unknown", agent_id=None)
