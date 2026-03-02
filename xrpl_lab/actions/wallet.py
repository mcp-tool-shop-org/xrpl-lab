"""Wallet management — create, load, save, show."""

from __future__ import annotations

import contextlib
import json
import os
import stat
from pathlib import Path

from xrpl.wallet import Wallet

from ..state import get_home_dir

DEFAULT_WALLET_FILENAME = "wallet.json"


def default_wallet_path() -> Path:
    """Default wallet location: ~/.xrpl-lab/wallet.json."""
    return get_home_dir() / DEFAULT_WALLET_FILENAME


def create_wallet() -> Wallet:
    """Generate a new XRPL wallet."""
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
        return Wallet.from_seed(data["seed"])
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
