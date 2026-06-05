"""Offline reader with a fixture mirroring real Base Sepolia token #17 (Silverback).

Used for tests and demo safety. No web3, no network.
"""

from __future__ import annotations

from beacon.chain.interface import ChainReader, IdentityEvidence, ReputationEvidence

_FIXTURE_CARD = {
    "type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
    "name": "Silverback (mock)",
    "description": "Autonomous DeFi infrastructure for the agent economy.",
    "tags": ["DeFi", "Trading", "x402"],
    "x402Support": True,
    "active": True,
    "supportedTrust": ["reputation"],
}


class MockReader(ChainReader):
    async def get_identity(self, token_id: int) -> IdentityEvidence:
        if token_id != 17:
            return IdentityEvidence(token_id=token_id, exists=False, error="token_not_found")
        return IdentityEvidence(
            token_id=17,
            exists=True,
            owner_address="0x21fdEd74C901129977B8e28C2588595163E1e235",
            agent_wallet="0x21fdEd74C901129977B8e28C2588595163E1e235",
            on_chain_name=_FIXTURE_CARD["name"],
            description=_FIXTURE_CARD["description"],
            endpoints=[],
            x402_support=True,
            active=True,
            supported_trust=["reputation"],
            raw_agent_card=_FIXTURE_CARD,
            token_uri_kind="data-base64",
            block_number=19482711,
        )

    async def get_reputation(self, token_id: int) -> ReputationEvidence:
        if token_id != 17:
            return ReputationEvidence(token_id=token_id, has_reputation=False)
        return ReputationEvidence(
            token_id=17,
            clients_observed=7,
            client_addresses=["0xAAA", "0xBBB", "0xCCC"],
            interaction_count=65,
            summary_value_raw=1010,
            summary_value_decimals=2,
            summary_value="10.10",
            has_reputation=True,
        )
