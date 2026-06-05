"""Builds the NANDA agent card served at /.well-known/agent.json.

Capabilities are drawn ONLY from the NANDA charter catalog (no free-form tokens).
Exactly one slot:* tag declares Beacon's neighborhood.
"""

from __future__ import annotations

from beacon.config import get_settings


def build_agent_card() -> dict:
    base = get_settings().public_url.rstrip("/")
    return {
        "schema_version": "1.0",
        "agent_id": "beacon",
        "name": "Beacon",
        "description": (
            "Beacon is a read-only witness for the City of Agents. Give it a NANDA "
            "agent (or an ERC-8004 token id) and it resolves the agent through the "
            "NANDA registry first, then reads the ERC-8004 Identity and Reputation "
            "registries on Base Sepolia, returning trust evidence in four tiers "
            "(Brief / Claim / Reputation / Proof+Stake, per Hu & Rong, AAAI 2026). "
            "It reports evidence and leaves the trust decision to you — no wallet or "
            "RPC required by the caller."
        ),
        "url": base,
        # All from the NANDA charter capability catalog.
        "capabilities": ["verification", "attestation", "authentication", "audit"],
        "tags": ["slot:trust", "phase-1", "erc8004", "base-sepolia", "witness"],
        "endpoints": {
            "chat": f"{base}/chat",
            "a2a": f"{base}/a2a",
            "health": f"{base}/health",
        },
        "version": "1.0.0",
        "skills": [
            {
                "id": "enrich",
                "name": "Enrich with on-chain trust evidence",
                "description": (
                    "Resolve an agent via the NANDA registry, then return its ERC-8004 "
                    "on-chain identity, reputation and proof-of-control as tiered evidence."
                ),
                "tags": ["verification", "attestation", "audit"],
                "examples": [
                    "enrich agent 17",
                    "tell me about agent 0x8004A818BFB912233c491871b3d84c89A494BD9e",
                    "what trust evidence exists for agent 1",
                ],
            },
            {
                "id": "evidence_check",
                "name": "Evidence check (factual threshold)",
                "description": (
                    "Report whether an agent's recorded interaction count meets a "
                    "numeric threshold. Returns the fact; the caller decides."
                ),
                "tags": ["verification", "audit"],
                "examples": ["evidence-check agent 17 min_interactions=10"],
            },
        ],
        "skill_md_url": f"{base}/SKILL.MD",
    }
