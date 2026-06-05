"""Beacon HTTP service — the four NANDA routes (+ SKILL.MD), on port 6000."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse

from beacon.agent_card import build_agent_card
from beacon.enrichment import assert_witness_only, enrich, evidence_check
from beacon.intent import extract_intent
from beacon.models import A2ARequest, ChatRequest

app = FastAPI(title="Beacon", description="On-chain trust evidence for the City of Agents.")

_SKILL_MD = Path(__file__).resolve().parent.parent / "SKILL.MD"

_HELP = (
    "Beacon returns on-chain trust evidence. Try: 'enrich agent 17' or "
    "'evidence-check agent 17 min_interactions=10'."
)


@app.get("/health")
async def health() -> dict:
    return {"agent_id": "beacon", "status": "ok"}


@app.get("/.well-known/agent.json")
async def agent_json() -> JSONResponse:
    return JSONResponse(build_agent_card())


@app.get("/SKILL.MD")
@app.get("/skill.md")
async def skill_md() -> PlainTextResponse:
    text = _SKILL_MD.read_text() if _SKILL_MD.exists() else "SKILL.MD not found"
    return PlainTextResponse(text, media_type="text/markdown")


async def _handle(message: str) -> dict:
    intent = extract_intent(message)
    if intent.skill == "enrich":
        evidence = await enrich(intent.agent_id)
        assert_witness_only(evidence)  # Beacon never authors a decision
        return {"response": _summarize(evidence), "evidence": evidence}
    if intent.skill == "evidence_check":
        result = await evidence_check(intent.agent_id, intent.params)
        assert_witness_only(result)
        return {"response": result["note"], "evidence_check": result}
    return {"response": _HELP}


@app.post("/chat")
async def chat(req: ChatRequest) -> dict:
    return await _handle(req.message)


@app.post("/a2a")
async def a2a(req: A2ARequest) -> dict:
    return await _handle(req.message)


def _summarize(evidence: dict) -> str:
    t = evidence["tiers"]
    brief, claim, rep, proof = t["brief"], t["claim"], t["reputation"], t["proof_stake"]
    lines = [
        f"Trust evidence for agent {evidence['query']['agent_queried']} "
        f"(evidence only — you decide):",
        f"- Brief (NANDA): {brief.get('status')}"
        + (f", name={brief.get('name')}" if brief.get("name") else ""),
    ]
    if claim.get("on_chain_name"):
        lines.append(
            f"- Claim (ERC-8004): {claim['on_chain_name']}, active={claim.get('active')}, "
            f"supportedTrust={claim.get('supported_trust')}"
        )
        lines.append(
            f"- Reputation: {rep.get('interaction_count')} interactions across "
            f"{rep.get('clients_observed')} clients (value {rep.get('summary_value')})"
            if rep.get("has_reputation")
            else "- Reputation: none recorded on-chain yet"
        )
        lines.append(
            f"- Proof+Stake: ERC-721 owner {proof.get('owner_address')} @ block "
            f"{proof.get('block_number')} on base-sepolia"
        )
    else:
        lines.append(f"- Claim/Reputation/Proof: {claim.get('status')}")
    return "\n".join(lines)
