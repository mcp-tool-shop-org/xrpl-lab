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

from .._atomic import atomic_write_json
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


def _ensure_secure_parent(path: Path) -> None:
    """Create ``path.parent`` at mode 0o700 (POSIX) and tighten if it already exists looser.

    ``Path.mkdir(mode=...)`` only honors ``mode`` on creation, so directories
    left over from earlier xrpl-lab versions stay at their original (often
    0o755, world-searchable) mode. Tightening on every save closes the
    upgrade-path information-disclosure gap where a local user could
    enumerate ``wallet.json`` in a shared-system home directory.

    chmod failures propagate intentionally — wave 1 set the discipline that
    the user must know when their wallet directory is in a state we cannot
    secure. Windows uses ACLs rather than POSIX modes, so the chmod step is
    skipped there; the existing Windows warning in :func:`save_wallet`
    covers the limitation.
    """
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if sys.platform != "win32":
        current = parent.stat().st_mode & 0o777
        if current != 0o700:
            os.chmod(parent, 0o700)


def save_wallet(wallet: Wallet, path: Path | None = None) -> Path:
    """Save wallet to disk with restricted permissions.

    The seed file is created via os.open with mode 0o600 from the start,
    eliminating the TOCTOU window where a previous write_text+chmod sequence
    left the file world-readable between create and chmod. The parent
    directory is also tightened to 0o700 (covering both new installs and
    the upgrade path from earlier versions that created it at 0o755).

    Delegates the create-with-mode + write to ``_atomic.atomic_write_json``
    in non-atomic mode (O_TRUNC, no tmp+rename): a corrupt seed is
    recoverable from the user's mnemonic, so we accept the (vanishingly
    small) torn-write window in exchange for fewer moving parts. The
    state.json side uses ``atomic=True`` for the same helper.
    """
    p = path or default_wallet_path()
    _ensure_secure_parent(p)

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

    atomic_write_json(p, data, file_mode=0o600, atomic=False)

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
