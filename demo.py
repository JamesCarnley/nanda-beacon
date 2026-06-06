#!/usr/bin/env python3
"""Narrated Beacon demo — runs the full story against a live (or local) instance.

Usage:
    python3 demo.py                 # hits the live Railway deployment
    python3 demo.py --pause         # waits for Enter between steps (good on a screen-share)
    BASE=http://localhost:6000 python3 demo.py    # demo a local server instead

No dependencies — standard library only. Resilient to the (flaky) NANDA droplet:
network calls retry, and the optional registry step degrades gracefully.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

BASE = os.environ.get("BASE", "https://nanda-beacon-production.up.railway.app").rstrip("/")
REGISTRY = "http://67.205.176.71/api/registry/lookup/beacon"
PAUSE = "--pause" in sys.argv

BOLD, DIM, CYAN, GREEN, YELLOW, RESET = (
    "\033[1m", "\033[2m", "\033[36m", "\033[32m", "\033[33m", "\033[0m"
)


def _req(url: str, data: bytes | None = None, attempts: int = 3) -> dict:
    last: Exception | None = None
    for _ in range(attempts):
        try:
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json", "User-Agent": "beacon-demo/1.0"},
            )
            return json.load(urllib.request.urlopen(req, timeout=45))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.6)
    raise last  # type: ignore[misc]


def _post(message: str) -> dict:
    return _req(f"{BASE}/chat", json.dumps({"message": message}).encode())


def header(n: int, title: str) -> None:
    print(f"\n{BOLD}{CYAN}── Step {n} — {title}{RESET}")
    if PAUSE:
        input(f"{DIM}   (press Enter){RESET}")


def main() -> None:
    print(f"{BOLD}🔦 Beacon — on-chain trust evidence for the City of Agents{RESET}")
    print(f"{DIM}   target: {BASE}{RESET}")

    header(1, "Discover Beacon in the NANDA city registry")
    print(f"   GET {REGISTRY}")
    try:
        rec = _req(REGISTRY)
        print(f"   → {GREEN}{rec['agent_id']}{RESET}  status={rec['status']}  "
              f"caps={rec['capabilities']}")
    except Exception:  # noqa: BLE001
        print(f"   {YELLOW}→ registry blipped (it's flaky); Beacon also reads it internally below.{RESET}")

    header(2, "Enrich a NANDA citizen with no on-chain identity (NANDA first)")
    t = _post("enrich agent tools")["evidence"]["tiers"]
    print(f'   POST /chat {{"message": "enrich agent tools"}}')
    print(f"   Brief (NANDA) : {t['brief']['status']} — {t['brief'].get('name')}")
    print(f"   On-chain      : {t['claim']['status']}")
    print(f"   {DIM}→ NANDA is the front door; Beacon honestly reports 'no on-chain identity yet.'{RESET}")

    header(3, "Enrich an ERC-8004 agent — real on-chain trust evidence")
    ev = _post("enrich agent 17")["evidence"]
    t = ev["tiers"]
    print(f'   POST /chat {{"message": "enrich agent 17"}}')
    print(f"   {DIM}{ev['witness_statement']}{RESET}")
    print(f"   Brief        : {t['brief']['source']} — {t['brief']['status']}")
    print(f"   Claim        : {GREEN}{t['claim']['on_chain_name']}{RESET}  "
          f"active={t['claim']['active']}  supportedTrust={t['claim']['supported_trust']}")
    print(f"   Reputation   : {GREEN}{t['reputation']['interaction_count']}{RESET} interactions / "
          f"{t['reputation']['clients_observed']} clients  (value {t['reputation']['summary_value']})")
    print(f"   Proof+Stake  : owner {t['proof_stake']['owner_address']}  "
          f"@ block {GREEN}{t['proof_stake']['block_number']}{RESET}  ({t['proof_stake']['chain']})")
    print(f"   {DIM}→ Real Base Sepolia reads. No wallet, no RPC. Evidence, not a verdict.{RESET}")

    header(4, "Evidence check — a fact, not a decision")
    fact = _post("evidence-check agent 17 min_interactions=10")["evidence_check"]["fact"]
    print(f'   POST /chat {{"message": "evidence-check agent 17 min_interactions=10"}}')
    print(f"   → interaction_count={fact['interaction_count']}  "
          f"meets_threshold={fact['meets_threshold']}  {DIM}(the caller decides){RESET}")

    print(f"\n{BOLD}{GREEN}✓ Beacon: NANDA-first, ERC-8004-backed, witness-not-judge.{RESET}\n")


if __name__ == "__main__":
    main()
