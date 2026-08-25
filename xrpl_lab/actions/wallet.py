"""Wallet management — create, load, save, show.

# WARNING: Wallet seeds are stored in plaintext JSON on disk.
# This is acceptable for testnet-only training but NEVER for mainnet.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from xrpl.wallet import Wallet

from .._atomic import atomic_write_json
from ..errors import LabError, LabException
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


def _windows_username() -> str:
    """Best-effort ``DOMAIN\\user`` identity string for icacls grants.

    ``USERDOMAIN`` is set for both domain accounts and plain local
    accounts (it mirrors ``COMPUTERNAME`` for the latter), so the
    qualified form resolves correctly in both cases. When ``USERDOMAIN``
    is unset (unusual/minimal environment), fall back to
    ``COMPUTERNAME\\USERNAME`` — icacls always echoes grants back in
    domain-qualified form, so a bare ``USERNAME`` grant would fail the
    post-grant self-check and get stripped (F-e4d178f0). Only if both
    domain sources are missing do we degrade to the bare username; the
    last-grantee guard in :func:`_windows_icacls_lockdown` then refuses
    to empty the ACL.
    """
    user = os.environ.get("USERNAME", "")
    domain = os.environ.get("USERDOMAIN", "") or os.environ.get("COMPUTERNAME", "")
    if domain and user:
        return f"{domain}\\{user}"
    return user


def _icacls_grantee_names(icacls_stdout: str, path: Path) -> list[str]:
    """Pull principal names out of ``icacls <path>``'s stdout.

    icacls's first output line is prefixed with the path itself;
    continuation lines are whitespace-padded to align under it. Each ACE
    line has the shape ``PRINCIPAL:(flags)(perm)[,(flags)(perm)...]`` —
    this returns just the ``PRINCIPAL`` portion of every ACE line,
    skipping the trailing "Successfully processed .../Failed processing
    ..." summary.
    """
    prefix = str(path)
    names: list[str] = []
    for raw_line in icacls_stdout.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("Successfully processed") or "Failed processing" in line:
            continue
        if line.startswith(prefix):
            line = line[len(prefix) :].strip()
        if ":" not in line:
            continue
        principal = line.split(":", 1)[0].strip()
        if principal:
            names.append(principal)
    return names


def _icacls_principal_is_self(principal: str, user: str) -> bool:
    """Match an icacls-echoed principal against the lockdown target identity.

    Compares on the qualified form icacls echoes. Also accepts a bare
    username on one side against ``DOMAIN\\user`` on the other so a
    residual bare-grant identity cannot self-strip (F-e4d178f0).
    """
    p = principal.lower()
    u = user.lower()
    if p == u:
        return True
    if "\\" not in u and "\\" in p:
        return p.rsplit("\\", 1)[-1] == u
    if "\\" not in p and "\\" in u:
        return u.rsplit("\\", 1)[-1] == p
    return False


def _windows_icacls_lockdown(path: Path, *, is_dir: bool) -> None:
    """Restrict *path* to the current user only via ``icacls`` (Windows ACLs).

    F-5531ceb5 (HIGH): Windows has no POSIX mode bits, so the 0o600/0o700
    discipline used on other platforms has no ``os.chmod`` equivalent. The
    pre-fix code knew this and did *nothing* about it beyond a log
    warning — every ACE already on the path (inherited from the parent,
    which on a shared machine — SECURITY.md's own threat model — can
    include "Users" or "Everyone") stayed in place forever. This is the
    real Windows equivalent of the POSIX tightening, in three steps:

    1. ``/inheritance:r`` strips every ACE actually marked inherited.
    2. ``/grant:r <user>:<perm>`` grants the current user, replacing any
       prior EXPLICIT grant for that same user. The ``r`` in both flags
       is load-bearing: ``/inheritance:c`` would only *convert* inherited
       ACEs to explicit copies (keeping them), and a bare ``/grant`` ADDS
       to existing grants instead of replacing them.
    3. Every OTHER grantee still on the ACL after steps 1-2 is removed
       explicitly. Step 3 is not optional: Windows seeds a freshly
       ``mkdir``'d directory with SYSTEM / Administrators / OWNER RIGHTS
       as EXPLICIT (not inherited) ACEs at creation time, so step 1 never
       touches them and step 2 only replaces the named user's own entry —
       verified empirically (a directory hardened by steps 1-2 alone
       still carried all three). Re-querying the ACL and removing every
       surviving non-target principal is what actually gets to "this
       user, and only this user," regardless of which of a path's ACEs
       happened to be inherited vs. explicit going in.

    Directories get ``(OI)(CI)`` (object-inherit/container-inherit) on
    the grant so files created underneath — the wallet file itself,
    moments later in ``save_wallet`` — inherit the lockdown instead of
    picking up whatever looser ACL the directory had before this call.

    Never swallows a failure: raises ``LabException`` (code
    ``PERM_WALLET_ACL_FAILED``) if ``icacls`` is unavailable, times out,
    or reports a non-zero exit code at any step, so a machine where this
    cannot be verified fails loudly instead of shipping an unprotected
    seed file under a false sense of security — the exact "log and
    continue" defect this replaces.

    F-e4d178f0: self-identification uses the qualified form icacls echoes
    (see :func:`_windows_username` / :func:`_icacls_principal_is_self`).
    If no listed principal matches the current user, this raises
    ``PERM_WALLET_ACL_FAILED`` instead of ``/remove:g``-ing every ACE
    into an empty DACL and returning normally.
    """
    user = _windows_username()
    perm = "(OI)(CI)F" if is_dir else "F"

    def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10, check=False
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise LabException(
                LabError(
                    code="PERM_WALLET_ACL_FAILED",
                    message=(
                        f"Could not restrict permissions on {path.name} "
                        "(Windows ACL lockdown)."
                    ),
                    hint=(
                        "icacls is required to secure the wallet on Windows "
                        "and could not be run. Confirm it is on PATH (it "
                        "ships with Windows at "
                        "C:\\Windows\\System32\\icacls.exe), or move "
                        "XRPL_LAB_HOME to an NTFS volume."
                    ),
                    cause=str(exc),
                )
            ) from exc
        if result.returncode != 0:
            raise LabException(
                LabError(
                    code="PERM_WALLET_ACL_FAILED",
                    message=(
                        f"Could not restrict permissions on {path.name} "
                        "(Windows ACL lockdown)."
                    ),
                    hint=(
                        "icacls reported a failure applying the lockdown. "
                        "The wallet was NOT saved with a verified "
                        "restrictive ACL — investigate before storing a "
                        "real seed at this path."
                    ),
                    cause=(result.stderr or result.stdout or "").strip()
                    or f"icacls exited {result.returncode}",
                )
            )
        return result

    run(["icacls", str(path), "/inheritance:r"])
    run(["icacls", str(path), "/grant:r", f"{user}:{perm}"])

    listing = run(["icacls", str(path)])
    principals = _icacls_grantee_names(listing.stdout, path)
    keep = [p for p in principals if _icacls_principal_is_self(p, user)]
    remove = [p for p in principals if not _icacls_principal_is_self(p, user)]
    if not keep:
        raise LabException(
            LabError(
                code="PERM_WALLET_ACL_FAILED",
                message=(
                    f"Could not restrict permissions on {path.name} "
                    "(Windows ACL lockdown)."
                ),
                hint=(
                    "After granting the current user, icacls did not list "
                    "that user as a remaining grantee. Refusing to strip "
                    "the ACL to empty (self-lockout). Check USERDOMAIN / "
                    "COMPUTERNAME / USERNAME and retry."
                ),
                cause=(
                    f"no self principal matching {user!r} in icacls listing; "
                    f"grantees={principals!r}"
                ),
            )
        )
    # keep is non-empty, so stripping *remove leaves the self ACE(s).
    for principal in remove:
        run(["icacls", str(path), "/remove:g", principal])


def _ensure_secure_parent(path: Path) -> None:
    """Create ``path.parent`` at mode 0o700 (POSIX) / owner-only ACL (Windows),
    and tighten it if it already exists looser.

    ``Path.mkdir(mode=...)`` only honors ``mode`` on creation, so directories
    left over from earlier xrpl-lab versions stay at their original (often
    0o755, world-searchable) mode. Tightening on every save closes the
    upgrade-path information-disclosure gap where a local user could
    enumerate ``wallet.json`` in a shared-system home directory.

    chmod failures propagate intentionally — wave 1 set the discipline that
    the user must know when their wallet directory is in a state we cannot
    secure. F-5531ceb5: Windows uses ACLs rather than POSIX modes, so it now
    gets the equivalent treatment via :func:`_windows_icacls_lockdown`
    instead of being silently skipped — a failure there propagates a
    ``LabException`` for the same reason a POSIX ``chmod`` failure
    propagates here.
    """
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if sys.platform != "win32":
        current = parent.stat().st_mode & 0o777
        if current != 0o700:
            os.chmod(parent, 0o700)
    else:
        _windows_icacls_lockdown(parent, is_dir=True)


def save_wallet(wallet: Wallet, path: Path | None = None) -> Path:
    """Save wallet to disk with restricted permissions.

    On POSIX, the seed file is created via os.open with mode 0o600 from
    the start, eliminating the TOCTOU window where a previous
    write_text+chmod sequence left the file world-readable between create
    and chmod. The parent directory is also tightened to 0o700 (covering
    both new installs and the upgrade path from earlier versions that
    created it at 0o755).

    F-5531ceb5 (HIGH) — what this now guarantees on win32: the parent
    directory and the wallet file both end up with an ACL that strips
    every inherited entry and grants Full Control to the current user
    ONLY (no SYSTEM, Administrators, Users, or Everyone), applied via
    :func:`_windows_icacls_lockdown`. Unlike ``os.chmod``'s mode argument,
    ``icacls`` can only act on a path that already exists, so it cannot
    be passed to ``os.open`` at create time the way POSIX's 0o600 is —
    there is an unavoidable instant where the file exists before its ACL
    is locked down. This function minimizes what a reader racing that
    instant can see: the file is created EMPTY first, locked down, and
    ONLY THEN is the seed written into it — so the worst a racing reader
    can observe is "a file exists", never the seed itself. If the lockdown
    cannot be verified (icacls missing, times out, or reports failure),
    ``save_wallet`` raises ``LabException`` (code ``PERM_WALLET_ACL_FAILED``)
    instead of the previous behavior of logging a warning and silently
    continuing with an unprotected file.

    Delegates the actual content write to ``_atomic.atomic_write_json`` in
    non-atomic mode (O_TRUNC, no tmp+rename): a corrupt seed is
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

    if sys.platform == "win32":
        # Create empty (no seed bytes on disk yet), lock the ACL down,
        # THEN write the real content — see the docstring above for why
        # this ordering matters. Failures anywhere in this sequence
        # (including the lockdown itself) propagate; nothing here is
        # silently swallowed.
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.close(fd)
        _windows_icacls_lockdown(p, is_dir=False)

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
