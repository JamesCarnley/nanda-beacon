"""Live, read-only reader for ERC-8004 registries on Base Sepolia.

Confirmed against the official deployment (eth_call only — never writes, never signs):
  ownerOf(uint256)                          -> address
  tokenURI(uint256)                         -> string   (data:..base64 | ipfs:// | https://)
  getAgentWallet(uint256)                   -> address  (may be 0x0)
  getClients(uint256)                       -> address[]
  getSummary(uint256,address[],string,string) -> (uint64 count, int128 value, uint8 decimals)
                                              (REVERTS if clientAddresses is empty)
"""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
from urllib.parse import urlparse

import httpx
from web3 import AsyncWeb3, Web3
from web3.exceptions import BadFunctionCallOutput, ContractLogicError

from beacon.chain.interface import ChainReader, IdentityEvidence, ReputationEvidence
from beacon.config import USER_AGENT, get_settings

_TIMEOUT = 12
_MAX_CARD_BYTES = 256 * 1024  # cap untrusted AgentCard fetches

_IDENTITY_ABI = [
    {"name": "ownerOf", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "tokenId", "type": "uint256"}],
     "outputs": [{"name": "", "type": "address"}]},
    {"name": "tokenURI", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "tokenId", "type": "uint256"}],
     "outputs": [{"name": "", "type": "string"}]},
    {"name": "getAgentWallet", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "agentId", "type": "uint256"}],
     "outputs": [{"name": "", "type": "address"}]},
]

_REPUTATION_ABI = [
    {"name": "getClients", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "agentId", "type": "uint256"}],
     "outputs": [{"name": "", "type": "address[]"}]},
    {"name": "getSummary", "type": "function", "stateMutability": "view",
     "inputs": [
         {"name": "agentId", "type": "uint256"},
         {"name": "clientAddresses", "type": "address[]"},
         {"name": "tag1", "type": "string"},
         {"name": "tag2", "type": "string"},
     ],
     "outputs": [
         {"name": "count", "type": "uint64"},
         {"name": "summaryValue", "type": "int128"},
         {"name": "summaryValueDecimals", "type": "uint8"},
     ]},
]


def _make_w3(rpc_url: str) -> AsyncWeb3:
    # Both headers must be set explicitly: web3 only sends its default header block
    # (which carries Content-Type) when the caller supplies no `headers` key at all.
    provider = AsyncWeb3.AsyncHTTPProvider(
        rpc_url,
        request_kwargs={
            "headers": {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
        },
    )
    return AsyncWeb3(provider)


class BaseSepoliaReader(ChainReader):
    def __init__(self) -> None:
        s = get_settings()
        self._rpcs = [s.base_sepolia_rpc, s.base_sepolia_rpc_fallback]
        self._w3 = _make_w3(self._rpcs[0])
        self._identity_addr = Web3.to_checksum_address(s.identity_registry)
        self._reputation_addr = Web3.to_checksum_address(s.reputation_registry)
        self._identity = self._w3.eth.contract(address=self._identity_addr, abi=_IDENTITY_ABI)
        self._reputation = self._w3.eth.contract(address=self._reputation_addr, abi=_REPUTATION_ABI)

    async def _call(self, coro_factory):
        """Run a contract call with a timeout, retrying once on the fallback RPC.

        Contract-level errors (reverts, decode failures) are deterministic, so they
        are re-raised immediately; only transient/network errors hit the fallback.
        """
        try:
            return await asyncio.wait_for(coro_factory(self._w3, self._identity, self._reputation), _TIMEOUT)
        except (ContractLogicError, BadFunctionCallOutput):
            raise
        except Exception:
            # one fallback attempt on the secondary RPC (transient/network only)
            w3 = _make_w3(self._rpcs[1])
            identity = w3.eth.contract(address=self._identity_addr, abi=_IDENTITY_ABI)
            reputation = w3.eth.contract(address=self._reputation_addr, abi=_REPUTATION_ABI)
            return await asyncio.wait_for(coro_factory(w3, identity, reputation), _TIMEOUT)

    async def get_identity(self, token_id: int) -> IdentityEvidence:
        try:
            owner = await self._call(lambda w3, idc, rep: idc.functions.ownerOf(token_id).call())
        except Exception as e:  # token does not exist / revert
            return IdentityEvidence(token_id=token_id, exists=False, error=f"ownerOf: {type(e).__name__}")

        ev = IdentityEvidence(token_id=token_id, exists=True, owner_address=owner)

        try:
            ev.block_number = await self._call(lambda w3, idc, rep: w3.eth.block_number)
        except Exception:
            ev.block_number = None

        try:
            wallet = await self._call(lambda w3, idc, rep: idc.functions.getAgentWallet(token_id).call())
            ev.agent_wallet = wallet if wallet and int(wallet, 16) != 0 else None
        except Exception:
            ev.agent_wallet = None

        try:
            uri = await self._call(lambda w3, idc, rep: idc.functions.tokenURI(token_id).call())
            card, kind = await _resolve_token_uri(uri)
            ev.token_uri_kind = kind
            ev.raw_agent_card = card
            if card:
                ev.on_chain_name = card.get("name")
                ev.description = card.get("description")
                ev.endpoints = card.get("endpoints") or card.get("services") or []
                ev.x402_support = card.get("x402Support")
                ev.active = card.get("active")
                ev.supported_trust = card.get("supportedTrust") or []
        except Exception as e:
            ev.error = f"tokenURI: {type(e).__name__}"

        if ev.agent_wallet is None and ev.raw_agent_card:
            ev.agent_wallet = _wallet_from_card(ev.raw_agent_card)

        return ev

    async def get_reputation(self, token_id: int) -> ReputationEvidence:
        try:
            clients = await self._call(lambda w3, idc, rep: rep.functions.getClients(token_id).call())
        except Exception as e:
            return ReputationEvidence(token_id=token_id, has_reputation=False, error=f"getClients: {type(e).__name__}")

        if not clients:
            # getSummary reverts on an empty client list — empty reputation is valid evidence.
            return ReputationEvidence(token_id=token_id, clients_observed=0, has_reputation=False)

        try:
            count, value, decimals = await self._call(
                lambda w3, idc, rep: rep.functions.getSummary(token_id, clients, "", "").call()
            )
        except Exception as e:
            return ReputationEvidence(
                token_id=token_id, clients_observed=len(clients),
                client_addresses=list(clients), has_reputation=False,
                error=f"getSummary: {type(e).__name__}",
            )

        denom = 10**decimals if decimals else 1
        return ReputationEvidence(
            token_id=token_id,
            clients_observed=len(clients),
            client_addresses=list(clients),
            interaction_count=int(count),
            summary_value_raw=int(value),
            summary_value_decimals=int(decimals),
            summary_value=str(int(value) / denom),
            has_reputation=int(count) > 0,
        )


def _wallet_from_card(card: dict) -> str | None:
    """Some AgentCards expose the wallet as a service endpoint like eip155:8453:0x..."""
    for svc in card.get("services", []) or []:
        if isinstance(svc, dict) and svc.get("name") == "agentWallet":
            ep = str(svc.get("endpoint", ""))
            if "0x" in ep:
                return "0x" + ep.split("0x", 1)[1]
    return None


def _is_blocked_host(host: str) -> bool:
    """Block SSRF targets: private, loopback, link-local, reserved, multicast IPs."""
    if not host:
        return True
    if host.lower() in {"localhost", "localhost.localdomain"}:
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False  # a hostname, not a literal IP — allowed
    return (
        addr.is_private or addr.is_loopback or addr.is_link_local
        or addr.is_reserved or addr.is_multicast or addr.is_unspecified
    )


async def _resolve_token_uri(uri: str) -> tuple[dict | None, str]:
    """Decode an ERC-8004 tokenURI into an AgentCard dict. Deterministic for base64.

    tokenURI content is attacker-controlled (any token owner sets it), so remote
    fetches are scheme-restricted and SSRF-guarded; redirects are not followed.
    """
    if uri.startswith("data:") and "base64," in uri:
        payload = uri.split("base64,", 1)[1]
        return json.loads(base64.b64decode(payload)), "data-base64"
    if uri.startswith("ipfs://"):
        cid = uri[len("ipfs://"):]
        return await _fetch_json(f"https://ipfs.io/ipfs/{cid}"), "ipfs"
    if uri.startswith("https://") or uri.startswith("http://"):
        if _is_blocked_host(urlparse(uri).hostname or ""):
            return None, "blocked"
        kind = "https" if uri.startswith("https://") else "http"
        return await _fetch_json(uri), kind
    return None, "unknown"


async def _fetch_json(url: str) -> dict | None:
    async with httpx.AsyncClient(
        timeout=_TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=False
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        if len(r.content) > _MAX_CARD_BYTES:
            raise ValueError("agent card exceeds size cap")
        return r.json()
