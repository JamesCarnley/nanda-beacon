"""Typed configuration loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# A polite, non-Python User-Agent: the public Base Sepolia RPC 403s the default
# urllib/python UA, so every outbound HTTP call sends this instead.
USER_AGENT = "nanda-beacon/1.0 (+https://github.com/JamesCarnley/nanda-beacon)"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    public_url: str = "http://localhost:6000"
    chain_mode: str = "live"  # "live" | "mock"

    base_sepolia_rpc: str = "https://sepolia.base.org"
    base_sepolia_rpc_fallback: str = "https://base-sepolia-rpc.publicnode.com"
    chain_id: int = 84532
    identity_registry: str = "0x8004A818BFB912233c491871b3d84c89A494BD9e"
    reputation_registry: str = "0x8004B663056A597Dffe9eCcC1965A193B7388713"

    demo_token_id: int = 17
    nanda_registry_url: str = "http://67.205.176.71"

    openai_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
