"""The enrichment core.

Order is deliberate and load-bearing:
  1. NANDA city registry lookup (FIRST, always) -> Brief tier.
  2. ERC-8004 on-chain reads (parallel)          -> Claim / Reputation / Proof+Stake tiers.
  3. Merge into tiered evidence (Hu & Rong, AAAI 2026 taxonomy).
  4. Witness framing — Beacon reports evidence; the caller decides.
"""

from __future__ import annotations

import asyncio
import re

from beacon import nanda_client
from beacon.chain import get_chain_reader
from beacon.config import get_settings
from beacon.models import BANNED_DECISION_WORDS, WITNESS_STATEMENT


def _chain_token_id(agent_id, nanda_record: dict) -> int | None:
    """Resolve which ERC-8004 token id to read.

    Direct integer wins; otherwise honor an `erc8004:<id>` pointer the NANDA
    record declares (this is how a city citizen links itself to an on-chain id).
    """
    if isinstance(agent_id, int):
        return agent_id
    for tag in nanda_record.get("tags", []) or []:
        if isinstance(tag, str) and tag.lower().startswith("erc8004:"):
            try:
                return int(tag.split(":", 1)[1])
            except ValueError:
                continue
    return None


async def enrich(agent_id: int | str) -> dict:
    """Return tiered trust evidence for an agent. NANDA first, then chain."""
    settings = get_settings()

    # Step 1 — NANDA registry FIRST (mandatory; populates the Brief tier).
    nanda_record = await nanda_client.lookup(str(agent_id))

    # Step 2 — decide the on-chain target, then read the chain (parallel).
    token_id = _chain_token_id(agent_id, nanda_record)
    identity = reputation = None
    if token_id is not None:
        reader = get_chain_reader()
        identity, reputation = await asyncio.gather(
            reader.get_identity(token_id),
            reader.get_reputation(token_id),
        )

    # Step 3 — Brief tier (always NANDA-attributed).
    brief = {
        "tier": "Brief",
        "source": nanda_record.get("source", "NANDA registry"),
        "status": nanda_record.get("status", "unknown"),
        "name": nanda_record.get("name"),
        "description": nanda_record.get("description"),
        "capabilities": nanda_record.get("capabilities"),
        "tags": nanda_record.get("tags"),
    }

    if identity is None:
        claim = {"tier": "Claim", "status": "no_onchain_identity",
                 "note": "No ERC-8004 token id is associated with this agent."}
        reputation_tier = {"tier": "Reputation", "status": "no_onchain_identity"}
        proof_stake = {"tier": "Proof+Stake", "status": "no_onchain_identity"}
    elif not identity.exists:
        claim = {"tier": "Claim", "status": "token_not_found", "token_id": token_id}
        reputation_tier = {"tier": "Reputation", "status": "token_not_found"}
        proof_stake = {"tier": "Proof+Stake", "status": "token_not_found"}
    else:
        claim = {
            "tier": "Claim",
            "source": "ERC-8004 Identity Registry tokenURI (on-chain AgentCard)",
            "token_id": identity.token_id,
            "on_chain_name": identity.on_chain_name,
            "description": identity.description,
            "active": identity.active,
            "x402_support": identity.x402_support,
            "supported_trust": identity.supported_trust,
            "agent_wallet": identity.agent_wallet,
            "token_uri_kind": identity.token_uri_kind,
        }
        reputation_tier = {
            "tier": "Reputation",
            "source": "ERC-8004 Reputation Registry (getClients + getSummary)",
            "has_reputation": reputation.has_reputation,
            "clients_observed": reputation.clients_observed,
            "interaction_count": reputation.interaction_count,
            "summary_value": reputation.summary_value,
            "summary_value_decimals": reputation.summary_value_decimals,
            "note": ("No on-chain feedback recorded yet — absence of reputation is "
                     "itself evidence." if not reputation.has_reputation else None),
        }
        proof_stake = {
            "tier": "Proof+Stake",
            "source": "ERC-721 ownerOf (cryptographic proof of identity control)",
            "token_standard": "ERC-721",
            "token_id": identity.token_id,
            "owner_address": identity.owner_address,
            "contract_address": settings.identity_registry,
            "chain": "base-sepolia",
            "chain_id": settings.chain_id,
            "block_number": identity.block_number,
            "note": "Whoever controls this key controls the identity — proof, backed by the stake of the key itself.",
        }

    # Informational cross-check (never a decision).
    cross_check = {"note": "Informational only. Beacon does not decide."}
    if identity is not None and identity.exists and brief.get("name") and identity.on_chain_name:
        cross_check["nanda_name_matches_chain"] = (
            brief["name"].strip().lower() == identity.on_chain_name.strip().lower()
        )

    return {
        "beacon_version": "1.0.0",
        "witness_statement": WITNESS_STATEMENT,
        "query": {
            "agent_queried": agent_id,
            "chain": "base-sepolia",
            "chain_id": settings.chain_id,
            "identity_registry": settings.identity_registry,
            "reputation_registry": settings.reputation_registry,
        },
        "tiers": {
            "brief": brief,
            "claim": claim,
            "reputation": reputation_tier,
            "proof_stake": proof_stake,
        },
        "cross_check": cross_check,
    }


async def evidence_check(agent_id: int | str, params: dict) -> dict:
    """Report a factual threshold comparison. Reports the fact; the caller decides."""
    ev = await enrich(agent_id)
    rep = ev["tiers"]["reputation"]
    threshold = int(params.get("min_interactions", 0))
    observed = int(rep.get("interaction_count", 0) or 0)
    return {
        "witness_statement": WITNESS_STATEMENT,
        "query": {"agent_queried": agent_id, "min_interactions": threshold},
        "fact": {
            "interaction_count": observed,
            "meets_threshold": observed >= threshold,
        },
        "note": (f"The chain records {observed} interaction(s); the threshold is "
                 f"{threshold}. Beacon reports the fact — you decide what it means."),
    }


# Keys whose string values are authored BY BEACON (its own framing). On-chain /
# NANDA text (name, description, tags, ...) is quoted evidence, not Beacon's voice,
# and is deliberately excluded — Beacon faithfully reports what an agent claims.
_AUTHORED_KEYS = {"witness_statement", "tier", "source", "status", "note"}


def _authored_strings(obj, key: str | None = None) -> list[str]:
    if isinstance(obj, dict):
        out: list[str] = []
        for k, v in obj.items():
            out += _authored_strings(v, k)
        return out
    if isinstance(obj, list):
        out = []
        for v in obj:
            out += _authored_strings(v, key)
        return out
    if isinstance(obj, str) and key in _AUTHORED_KEYS:
        return [obj]
    return []


def assert_witness_only(evidence: dict) -> None:
    """Guard: Beacon never AUTHORS a decision.

    Scans only Beacon-authored fields (not quoted on-chain/NANDA text) using
    word-boundary matching, so "TrustedAgent" or "distrusted" never false-trips,
    while a standalone decision word in Beacon's own framing does.
    """
    blob = " ".join(_authored_strings(evidence)).lower()
    for word in BANNED_DECISION_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", blob):
            raise AssertionError(f"witness violation: Beacon authored '{word}'")
