"""Wallet management — create, load, save, show.

# WARNING: Wallet seeds are stored in plaintext JSON on disk.
# This is acceptable for testnet-only training but NEVER for mainnet.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from xrpl.wallet import Wallet

from ..state import get_home_dir

logger = logging.getLogger(__name__)

DEFAULT_WALLET_FILENAME = "wallet.json"

_TESTNET_ONLY_WARNING = (
    "This wallet is for TESTNET use only. "
    "Never use xrpl-lab wallets on mainnet — seeds are stored in plaintext."
)


def default_wallet_path() -> Path:
    """Default wallet location: ~/.xrpl-lab/wallet.json."""
    return get_home_dir() / DEFAULT_WALLET_FILENAME


def create_wallet() -> Wallet:
    """Generate a new XRPL wallet."""
    print(_TESTNET_ONLY_WARNING)
    return Wallet.create()


def save_wallet(wallet: Wallet, path: Path | None = None) -> Path:
    """Save wallet to disk with restricted permissions.

    The seed file is created via os.open with mode 0o600 from the start,
    eliminating the TOCTOU window where a previous write_text+chmod sequence
    left the file world-readable between create and chmod.
    """
    p = path or default_wallet_path()
    p.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "address": wallet.address,
        "seed": wallet.seed,
        "public_key": wallet.public_key,
    }

    # Open with restrictive mode at create time (POSIX). On Windows the mode
    # arg is largely a no-op for ACLs — log the limitation as before but still
    # write atomically. Failures (write or open) propagate; we no longer
    # silently swallow OSError on permission setting.
    if sys.platform == "win32":
        logger.warning(
            "Wallet file permissions cannot be restricted on Windows. "
            "This wallet is for testnet use only."
        )

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(p, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return p


def load_wallet(path: Path | None = None) -> Wallet | None:
    """Load wallet from disk. Returns None if file doesn't exist."""
    p = path or default_wallet_path()
    if not p.exists():
        return None

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        derived = Wallet.from_seed(data["seed"])
        if derived.address != data.get("address"):
            logger.warning("Wallet address mismatch — file may be corrupted")
        return derived
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def wallet_exists(path: Path | None = None) -> bool:
    """Check if a wallet file exists."""
    p = path or default_wallet_path()
    return p.exists()


def wallet_info(wallet: Wallet) -> dict[str, str]:
    """Return non-sensitive wallet info for display."""
    return {
        "address": wallet.address,
        "public_key": wallet.public_key,
    }
