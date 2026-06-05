"""The shippable invariant test. Runs fully offline (CHAIN_MODE=mock)."""

from __future__ import annotations

import os

os.environ["CHAIN_MODE"] = "mock"

import pytest  # noqa: E402

from beacon.config import get_settings  # noqa: E402
from beacon.enrichment import assert_witness_only, enrich, evidence_check  # noqa: E402
from beacon.models import BANNED_DECISION_WORDS  # noqa: E402

TOKEN = 17


@pytest.mark.asyncio
async def test_enrich_returns_four_tiers_with_witness_framing():
    result = await enrich(TOKEN)

    # All four trust tiers present.
    for tier in ("brief", "claim", "reputation", "proof_stake"):
        assert tier in result["tiers"], f"missing tier: {tier}"

    # Witness framing present and non-empty.
    assert result["witness_statement"]
    assert "witness" in result["witness_statement"].lower()

    # NANDA is the protagonist: the Brief tier is always NANDA-attributed.
    assert result["tiers"]["brief"]["source"].startswith("NANDA")

    # Proof+Stake carries an on-chain block number (witnessed at a height).
    assert result["tiers"]["proof_stake"]["block_number"] is not None

    # Reputation is populated for the demo token.
    assert result["tiers"]["reputation"]["interaction_count"] == 65


@pytest.mark.asyncio
async def test_witness_not_judge_no_banned_words():
    result = await enrich(TOKEN)
    blob = str(result).lower()
    for word in BANNED_DECISION_WORDS:
        assert word not in blob, f"banned decision word leaked: {word}"
    assert_witness_only(result)  # must not raise


@pytest.mark.asyncio
async def test_evidence_check_reports_fact_not_decision():
    result = await evidence_check(TOKEN, {"min_interactions": 10})
    assert result["fact"]["meets_threshold"] is True
    assert result["fact"]["interaction_count"] == 65


def test_demo_token_is_seventeen():
    assert get_settings().demo_token_id == TOKEN
