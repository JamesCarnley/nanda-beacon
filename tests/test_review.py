"""Focused review suite for Beacon. Runs fully offline (CHAIN_MODE=mock).

Covers intent parsing, the witness invariant under adversarial on-chain data,
HTTP routes via TestClient, NANDA-first tier behavior with no on-chain identity,
deterministic base64 tokenURI decode, and evidence_check threshold boundaries.

DO NOT modify code under beacon/. Where the code is buggy, the assertion below
expresses the CORRECT expected behavior so the test fails and surfaces the bug.
"""

from __future__ import annotations

import base64
import json
import os

os.environ["CHAIN_MODE"] = "mock"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import beacon.enrichment as enrichment  # noqa: E402
import beacon.nanda_client as nanda_client  # noqa: E402
from beacon.agent_card import build_agent_card  # noqa: E402
from beacon.chain import base_sepolia  # noqa: E402
from beacon.chain.interface import (  # noqa: E402
    ChainReader,
    IdentityEvidence,
    ReputationEvidence,
)
from beacon.enrichment import assert_witness_only, enrich, evidence_check  # noqa: E402
from beacon.intent import extract_intent  # noqa: E402
from beacon.main import app  # noqa: E402
from beacon.models import BANNED_DECISION_WORDS  # noqa: E402

TOKEN = 17


# --------------------------------------------------------------------------- #
# 1. Intent parsing (table-driven)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "message, expected_skill, expected_agent_id",
    [
        ("enrich agent 17", "enrich", 17),
        (
            "tell me about agent 0x8004A818BFB912233c491871b3d84c89A494BD9e",
            "enrich",
            "0x8004A818BFB912233c491871b3d84c89A494BD9e",
        ),
        ("enrich agent tools", "enrich", "tools"),
        ("who is agent 1", "enrich", 1),
        # The tricky ones: the *agent id* is 17, not the threshold 10.
        ("evidence-check agent 17 min_interactions=10", "evidence_check", 17),
        ("for agent 17 at least 10", "evidence_check", 17),
    ],
)
def test_extract_intent_table(message, expected_skill, expected_agent_id):
    intent = extract_intent(message)
    assert intent.skill == expected_skill, (
        f"message={message!r} -> skill {intent.skill!r}, expected {expected_skill!r}"
    )
    assert intent.agent_id == expected_agent_id, (
        f"message={message!r} -> agent_id {intent.agent_id!r}, "
        f"expected {expected_agent_id!r} (must not grab the threshold number)"
    )


def test_extract_intent_threshold_param_parsed():
    """The threshold should land in params, distinct from the agent id."""
    intent = extract_intent("evidence-check agent 17 min_interactions=10")
    assert intent.params.get("min_interactions") == 10


def test_extract_intent_unknown():
    intent = extract_intent("hello there, nice weather")
    assert intent.skill == "unknown"
    assert intent.agent_id is None


# --------------------------------------------------------------------------- #
# 2. Witness invariant under adversarial on-chain data
# --------------------------------------------------------------------------- #

class _AdversarialReader(ChainReader):
    """A reader whose on-chain AgentCard smuggles a banned decision word."""

    async def get_identity(self, token_id: int) -> IdentityEvidence:
        return IdentityEvidence(
            token_id=token_id,
            exists=True,
            owner_address="0xdeadbeef00000000000000000000000000000000",
            agent_wallet="0xdeadbeef00000000000000000000000000000000",
            on_chain_name="Malicious Agent",
            # Adversarial: a banned decision word planted in on-chain text.
            description="This agent was rejected by everyone. Do not trust.",
            endpoints=[],
            x402_support=False,
            active=True,
            supported_trust=[],
            raw_agent_card={"name": "Malicious Agent"},
            token_uri_kind="data-base64",
            block_number=123456,
        )

    async def get_reputation(self, token_id: int) -> ReputationEvidence:
        return ReputationEvidence(token_id=token_id, has_reputation=False)


async def test_adversarial_onchain_text_is_reported_not_authored(monkeypatch):
    """A banned word in on-chain data is faithfully QUOTED, but is not Beacon
    authoring a decision: it lands under the Claim tier (sourced to ERC-8004),
    and the witness guard — which scans only Beacon-authored fields — does not trip.
    """
    monkeypatch.setattr(enrichment, "get_chain_reader", lambda: _AdversarialReader())

    result = await enrich(TOKEN)

    # The on-chain word is reported (quoted) under the Claim tier, attributed to ERC-8004.
    assert "rejected" in (result["tiers"]["claim"]["description"] or "").lower()
    assert result["tiers"]["claim"]["source"].startswith("ERC-8004")

    # Beacon did not AUTHOR a decision, so the witness guard does not raise.
    assert_witness_only(result)  # must not raise


async def test_clean_mock_passes_witness_guard():
    """The standard mock fixture (token 17) must NOT trip the witness guard."""
    result = await enrich(TOKEN)
    assert_witness_only(result)  # must not raise
    blob = str(result).lower()
    for word in BANNED_DECISION_WORDS:
        assert word not in blob


def test_witness_guard_word_boundary():
    """The guard matches whole words in Beacon-authored fields only."""
    # Benign text merely CONTAINING a banned word as a substring does not trip.
    assert_witness_only({"note": "the caller distrusted the result"})  # no raise
    # A banned word under a NON-authored key (quoted evidence) does not trip.
    assert_witness_only({"description": "this agent was rejected by peers"})  # no raise
    # A standalone decision word in a Beacon-authored field DOES trip.
    with pytest.raises(AssertionError):
        assert_witness_only({"note": "this request was rejected"})


# --------------------------------------------------------------------------- #
# 3. HTTP routes via TestClient
# --------------------------------------------------------------------------- #

@pytest.fixture()
def client():
    return TestClient(app)


def test_health_shape(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["agent_id"] == "beacon"


def test_agent_json_required_fields(client):
    r = client.get("/.well-known/agent.json")
    assert r.status_code == 200
    card = r.json()

    for field in ("schema_version", "agent_id", "name", "url",
                  "capabilities", "skills", "skill_md_url"):
        assert field in card, f"agent card missing required field: {field}"

    endpoints = card["endpoints"]
    for ep in ("chat", "a2a", "health"):
        assert ep in endpoints, f"agent card missing endpoint: {ep}"

    # Capabilities must be drawn from the NANDA charter catalog (sane set).
    sane = {"verification", "attestation", "authentication", "audit"}
    assert card["capabilities"], "capabilities must be non-empty"
    assert set(card["capabilities"]) <= sane, (
        f"capabilities out of catalog: {set(card['capabilities']) - sane}"
    )

    # Skills carry ids.
    skill_ids = {s["id"] for s in card["skills"]}
    assert {"enrich", "evidence_check"} <= skill_ids


def test_chat_enrich_returns_response_and_evidence(client):
    r = client.post("/chat", json={"message": "enrich agent 17"})
    assert r.status_code == 200
    body = r.json()
    assert "response" in body
    assert "evidence" in body
    tiers = body["evidence"]["tiers"]
    assert set(tiers) == {"brief", "claim", "reputation", "proof_stake"}
    assert tiers["brief"]["source"].startswith("NANDA")
    assert tiers["proof_stake"]["block_number"] is not None


def test_a2a_enrich_matches_chat_contract(client):
    r = client.post("/a2a", json={"message": "enrich agent 17"})
    assert r.status_code == 200
    body = r.json()
    assert "response" in body
    assert "evidence" in body
    assert body["evidence"]["tiers"]["brief"]["source"].startswith("NANDA")


def test_a2a_accepts_from_alias_field(client):
    """A2A envelopes use 'from'; the handler reads the raw 'message' key."""
    r = client.post("/a2a", json={"from": "agent://caller", "message": "enrich agent 17"})
    assert r.status_code == 200
    assert "evidence" in r.json()


def test_unknown_message_returns_help(client):
    r = client.post("/chat", json={"message": "hello there"})
    assert r.status_code == 200
    body = r.json()
    assert "response" in body
    assert "evidence" not in body
    assert "Beacon" in body["response"]


def test_chat_evidence_check_route(client):
    r = client.post("/chat", json={"message": "evidence-check agent 17 min_interactions=10"})
    assert r.status_code == 200
    body = r.json()
    assert "evidence_check" in body
    ec = body["evidence_check"]
    assert ec["query"]["agent_queried"] == 17, (
        f"evidence_check queried {ec['query']['agent_queried']!r}, expected 17"
    )
    assert ec["fact"]["interaction_count"] == 65
    assert ec["fact"]["meets_threshold"] is True


def test_skill_md_route(client):
    r = client.get("/SKILL.MD")
    assert r.status_code == 200
    assert "text/markdown" in r.headers["content-type"]
    assert len(r.text) > 0


def test_no_banned_words_in_any_http_response(client):
    """Witness invariant at the HTTP boundary for the standard fixture."""
    for path, payload in (
        ("/chat", {"message": "enrich agent 17"}),
        ("/a2a", {"message": "enrich agent 17"}),
        ("/chat", {"message": "evidence-check agent 17 min_interactions=10"}),
    ):
        r = client.post(path, json=payload)
        blob = json.dumps(r.json()).lower()
        for word in BANNED_DECISION_WORDS:
            assert word not in blob, f"{path}: banned word {word!r} leaked"


# --------------------------------------------------------------------------- #
# 4. NANDA tiers: record present, but no ERC-8004 identity
# --------------------------------------------------------------------------- #

async def test_nanda_record_without_erc8004_has_no_onchain_identity(monkeypatch):
    """A NANDA citizen with no erc8004 tag -> on-chain tiers report no identity,
    while the Brief tier is still NANDA-attributed."""

    async def _fake_lookup(agent_id: str) -> dict:
        return {
            "source": "NANDA registry (mock)",
            "status": "found",
            "agent_id": agent_id,
            "name": "TaglessAgent",
            "description": "A NANDA citizen with no on-chain ERC-8004 identity.",
            "capabilities": ["lookup"],
            "tags": ["slot:bazaar"],  # NOTE: no erc8004:* tag
        }

    monkeypatch.setattr(nanda_client, "lookup", _fake_lookup)

    # Use a non-integer agent id so no direct token id is inferred.
    result = await enrich("tagless-agent")

    assert result["tiers"]["brief"]["source"].startswith("NANDA")
    for tier in ("claim", "reputation", "proof_stake"):
        assert result["tiers"][tier]["status"] == "no_onchain_identity", (
            f"{tier} status was {result['tiers'][tier]['status']!r}"
        )


async def test_nanda_first_all_four_tiers_present_no_identity(monkeypatch):
    async def _fake_lookup(agent_id: str) -> dict:
        return {"source": "NANDA registry", "status": "found",
                "name": "X", "tags": []}

    monkeypatch.setattr(nanda_client, "lookup", _fake_lookup)
    result = await enrich("some-slug")
    assert set(result["tiers"]) == {"brief", "claim", "reputation", "proof_stake"}


# --------------------------------------------------------------------------- #
# 5. base64 tokenURI decode determinism (pure function)
# --------------------------------------------------------------------------- #

async def test_resolve_token_uri_base64_is_deterministic():
    card = {
        "name": "Decoded Agent",
        "description": "decoded from base64",
        "active": True,
        "supportedTrust": ["reputation"],
    }
    payload = base64.b64encode(json.dumps(card).encode()).decode()
    uri = f"data:application/json;base64,{payload}"

    decoded, kind = await base_sepolia._resolve_token_uri(uri)
    assert kind == "data-base64"
    assert decoded == card

    # Determinism: same input -> identical output.
    decoded2, kind2 = await base_sepolia._resolve_token_uri(uri)
    assert decoded2 == decoded
    assert kind2 == kind


async def test_resolve_token_uri_unknown_scheme():
    decoded, kind = await base_sepolia._resolve_token_uri("ftp://nope")
    assert decoded is None
    assert kind == "unknown"


# --------------------------------------------------------------------------- #
# 6. evidence_check threshold boundaries
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "min_interactions, expected_meets",
    [
        (0, True),     # 65 >= 0
        (64, True),    # below observed
        (65, True),    # exact boundary: 65 >= 65
        (66, False),   # just above observed
        (1000, False), # well above
    ],
)
async def test_evidence_check_threshold_boundaries(min_interactions, expected_meets):
    result = await evidence_check(TOKEN, {"min_interactions": min_interactions})
    assert result["fact"]["interaction_count"] == 65
    assert result["fact"]["meets_threshold"] is expected_meets, (
        f"min_interactions={min_interactions}: meets_threshold "
        f"{result['fact']['meets_threshold']}, expected {expected_meets}"
    )


async def test_evidence_check_default_threshold_zero():
    result = await evidence_check(TOKEN, {})
    assert result["query"]["min_interactions"] == 0
    assert result["fact"]["meets_threshold"] is True


# --------------------------------------------------------------------------- #
# 7. Optional live smoke test (skipped unless BEACON_LIVE_TESTS=1)
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(
    os.environ.get("BEACON_LIVE_TESTS") != "1",
    reason="live test; set BEACON_LIVE_TESTS=1 (and CHAIN_MODE=live) to run",
)
async def test_live_enrich_token_17_real_block_number():
    # Intentionally bypasses the mock by reading live chain. Requires network.
    result = await enrich(17)
    assert set(result["tiers"]) == {"brief", "claim", "reputation", "proof_stake"}
    assert result["tiers"]["brief"]["source"].startswith("NANDA")
    proof = result["tiers"]["proof_stake"]
    assert proof.get("block_number") is not None
    assert isinstance(proof["block_number"], int)
    assert proof["block_number"] > 0
