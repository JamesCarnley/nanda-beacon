# 🔦 Beacon

**A NANDA City-of-Agents citizen that returns on-chain trust evidence. A witness, not a judge.**

A vanilla agent in the city can't read Ethereum — no wallet, no RPC, no ABI. Beacon
crosses that gap for it. Hand Beacon an agent and it resolves the agent through the
**NANDA registry first**, then reads Ethereum's **ERC-8004** Identity and Reputation
registries on **Base Sepolia**, and returns trust **evidence** — not a verdict.

> Beacon reports the receipts and leaves the trust decision to the caller and to NANDA.

## Live deployment

Beacon is deployed and registered as a citizen in the NANDA City of Agents.

| | |
|---|---|
| Service | https://nanda-beacon-production.up.railway.app |
| Agent card | https://nanda-beacon-production.up.railway.app/.well-known/agent.json |
| SKILL.MD | https://nanda-beacon-production.up.railway.app/SKILL.MD |
| City registry | `agent_id: beacon` — `GET http://67.205.176.71/api/registry/lookup/beacon` |

Try it (reads real ERC-8004 data on Base Sepolia, live):

```bash
curl -s -X POST https://nanda-beacon-production.up.railway.app/chat \
  -H 'content-type: application/json' \
  -d '{"message":"enrich agent 17"}'
```

Or run the narrated end-to-end demo (no dependencies):

```bash
python3 demo.py            # hits the live deployment
python3 demo.py --pause    # step through it on a screen-share
```

## Why

Trust on the agentic web is shifting from human oversight to protocol design. NANDA's
registry gives agents *discovery and identity* (the **Brief/Claim** tiers in the
Hu & Rong taxonomy). What it doesn't carry is the **Reputation** and **Proof+Stake**
tiers — and those live on-chain in ERC-8004. Beacon is the bridge: it lets any city
citizen consult that on-chain evidence without becoming a web3 developer. NANDA stays
the front door; Beacon just adds the trust column.

## Evidence tiers

Output maps to the inter-agent trust taxonomy of Hu & Rong, *Inter-Agent Trust Models*
(AAAI 2026), over the NANDA Index (Raskar et al., 2025):

| Tier        | Source                              | What it shows                              |
|-------------|-------------------------------------|--------------------------------------------|
| Brief       | NANDA city registry (read first)    | name, description, capabilities, tags      |
| Claim       | ERC-8004 Identity Registry tokenURI | on-chain AgentCard, `supportedTrust`, active |
| Reputation  | ERC-8004 Reputation Registry        | interaction count + aggregate summary      |
| Proof+Stake | ERC-721 `ownerOf` at a block height | the controlling address (proof of control) |

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

# offline (mock) — for tests and demo safety
CHAIN_MODE=mock pytest -q

# live — reads real Base Sepolia data
uvicorn beacon.main:app --host 0.0.0.0 --port 6000
curl -s localhost:6000/health
curl -s -X POST localhost:6000/chat -H 'content-type: application/json' \
  -d '{"message":"enrich agent 17"}' | python -m json.tool
```

## Endpoints

| Route                       | Purpose                                            |
|-----------------------------|----------------------------------------------------|
| `GET /health`               | `{"agent_id":"beacon","status":"ok"}`              |
| `GET /.well-known/agent.json` | the NANDA agent card                             |
| `POST /chat`                | `{"message": "..."}` → evidence                    |
| `POST /a2a`                 | `{"from": "...", "message": "..."}` → evidence      |
| `GET /SKILL.MD`             | how a vanilla agent calls Beacon                   |

## Invariants

- **Read-only.** No private key exists anywhere in the service; `eth_call` only.
- **NANDA first.** The registry lookup always runs before any chain read.
- **Witness, not judge.** No verdict/decision field is ever emitted (enforced in tests).
- **Deterministic decode** of on-chain AgentCards.

## License

MIT © 2026 James Carnley
