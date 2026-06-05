"""Request/response models and the witness contract.

Beacon is a WITNESS, not a judge. It returns evidence and explicitly defers the
trust decision to the caller. These words must never appear as decision fields in
any response Beacon emits.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# The persistent witness statement, present on every enrich response.
# Carefully worded to avoid the banned decision-words below.
WITNESS_STATEMENT = (
    "Beacon is a read-only witness: it reports on-chain evidence and leaves the "
    "trust decision to the calling agent and the NANDA registry."
)

# Words that would turn Beacon into an authority/judge. The enrich path asserts
# none of these appear anywhere in a response (enforced in tests).
BANNED_DECISION_WORDS = ("verdict", "approved", "rejected", "trusted", "untrustworthy")


class ChatRequest(BaseModel):
    message: str


class A2ARequest(BaseModel):
    # A2A envelopes use "from", which is a Python keyword; expose it as `sender`.
    sender: str | None = Field(default=None, alias="from")
    message: str

    model_config = {"populate_by_name": True}
