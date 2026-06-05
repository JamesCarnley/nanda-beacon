"""Reads the NANDA city registry. This is Beacon's MANDATORY FIRST step.

Endpoints (confirmed live on the droplet):
  GET /api/registry/list             -> array of agent records
  GET /api/registry/lookup/{id}      -> single record (404 {"error":"agent not found"})

Every result carries a `source` starting with "NANDA" so the Brief tier is always
attributed to the city registry, even when unavailable.
"""

from __future__ import annotations

import asyncio

import httpx

from beacon.config import USER_AGENT, get_settings

_TIMEOUT = 6


def _mock_record(agent_id: str) -> dict:
    return {
        "source": "NANDA registry (mock)",
        "status": "found",
        "agent_id": agent_id,
        "name": "ExampleAgent (mock)",
        "description": "A mock NANDA citizen used for offline tests.",
        "capabilities": ["lookup"],
        "tags": ["slot:bazaar", "erc8004:17"],
    }


async def lookup(agent_id: str) -> dict:
    """Look up one agent in the NANDA city registry. Never raises."""
    settings = get_settings()
    if settings.chain_mode == "mock":
        return _mock_record(agent_id)

    url = f"{settings.nanda_registry_url}/api/registry/lookup/{agent_id}"
    last_err = "unknown"
    for attempt in range(2):  # the droplet blips under burst; retry once
        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT, headers={"User-Agent": USER_AGENT}
            ) as client:
                r = await client.get(url)
            if r.status_code == 200:
                rec = r.json()
                rec["source"] = "NANDA registry"
                rec["status"] = "found"
                return rec
            if r.status_code == 404:
                return {"source": "NANDA registry", "status": "not_found", "agent_id": agent_id}
            last_err = f"http_{r.status_code}"
        except Exception as e:  # noqa: BLE001
            last_err = type(e).__name__
        await asyncio.sleep(0.3)

    return {"source": "NANDA registry (unavailable)", "status": "unavailable",
            "agent_id": agent_id, "error": last_err}


async def list_agents() -> list[dict]:
    """Return the full NANDA roster (best-effort; empty list on failure)."""
    settings = get_settings()
    if settings.chain_mode == "mock":
        return [_mock_record("example")]
    url = f"{settings.nanda_registry_url}/api/registry/list"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
            r = await client.get(url)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else data.get("agents", [])
    except Exception:  # noqa: BLE001
        return []
