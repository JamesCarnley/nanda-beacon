"""On-chain read layer. Swap live/mock via CHAIN_MODE."""

from __future__ import annotations

from beacon.chain.interface import ChainReader, IdentityEvidence, ReputationEvidence
from beacon.config import get_settings

_reader: ChainReader | None = None


def get_chain_reader() -> ChainReader:
    """Return a process-wide singleton reader selected by CHAIN_MODE."""
    global _reader
    if _reader is None:
        if get_settings().chain_mode == "mock":
            from beacon.chain.mock import MockReader

            _reader = MockReader()
        else:
            from beacon.chain.base_sepolia import BaseSepoliaReader

            _reader = BaseSepoliaReader()
    return _reader


__all__ = [
    "ChainReader",
    "IdentityEvidence",
    "ReputationEvidence",
    "get_chain_reader",
]
