"""The ChainReader contract. Read-only. No method here can write or sign."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class IdentityEvidence:
    token_id: int
    exists: bool
    owner_address: str | None = None
    agent_wallet: str | None = None  # may be 0x0 on-chain; falls back to card endpoint
    on_chain_name: str | None = None
    description: str | None = None
    endpoints: list = field(default_factory=list)
    x402_support: bool | None = None
    active: bool | None = None
    supported_trust: list = field(default_factory=list)
    raw_agent_card: dict | None = None
    token_uri_kind: str | None = None  # "data-base64" | "ipfs" | "https" | None
    block_number: int | None = None
    error: str | None = None


@dataclass
class ReputationEvidence:
    token_id: int
    clients_observed: int = 0
    client_addresses: list = field(default_factory=list)
    interaction_count: int = 0
    summary_value_raw: int = 0
    summary_value_decimals: int = 0
    summary_value: str = "0"
    has_reputation: bool = False
    error: str | None = None


class ChainReader(ABC):
    """Read-only access to ERC-8004 registries. Never writes, never signs."""

    @abstractmethod
    async def get_identity(self, token_id: int) -> IdentityEvidence: ...

    @abstractmethod
    async def get_reputation(self, token_id: int) -> ReputationEvidence: ...
