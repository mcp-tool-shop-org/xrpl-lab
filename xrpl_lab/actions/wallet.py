"""Wallet management — create, load, save, show.

# WARNING: Wallet seeds are stored in plaintext JSON on disk.
# This is acceptable for testnet-only training but NEVER for mainnet.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import stat
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
    """Save wallet to disk with restricted permissions."""
    p = path or default_wallet_path()
    p.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "address": wallet.address,
        "seed": wallet.seed,
        "public_key": wallet.public_key,
    }
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Restrict permissions (best-effort on Windows)
    if sys.platform == "win32":
        logger.warning(
            "Wallet file permissions cannot be restricted on Windows. "
            "This wallet is for testnet use only."
        )
    else:
        with contextlib.suppress(OSError):
            os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)

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
