"""Test bootstrap: force offline mode before beacon is imported anywhere.

Uses setdefault so an explicit CHAIN_MODE=live (for the opt-in live smoke test)
still wins.
"""

import os

os.environ.setdefault("CHAIN_MODE", "mock")
