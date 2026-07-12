"""Multisig treasury actions — SignerListSet + multi-signed payments.

Multi-signing is NATIVE, MAINNET-LIVE XRPL (no amendment wait): an account
attaches a **SignerList** — 1..32 ``(Account, SignerWeight)`` entries plus a
``SignerQuorum`` — and from then on transactions can be authorized by any
combination of listed signers whose COMBINED weight meets the quorum. For a
game studio this is treasury hygiene: no single laptop, employee, or leaked
key can move the hot wallet; N-of-M keyholders must co-sign.

The rules the network enforces (and both transports must reject identically,
so a dry-run "pass" never masks a testnet failure):

  * **List shape (SignerListSet preflight, tem class):** 1-32 entries, no
    duplicate signer accounts, and the account **cannot list itself**
    (``temBAD_SIGNER``); every weight must be positive (``temBAD_WEIGHT``);
    the quorum cannot exceed the sum of the weights (``temBAD_QUORUM``) —
    otherwise no combination of signatures could ever authorize anything.
  * **Delete shape:** removing the list is ``SignerQuorum=0`` AND
    ``SignerEntries`` omitted. Doing only one of the two is ``temMALFORMED``.
  * **Multi-signed submission (tef class):** the transaction carries a
    ``Signers`` array (each ``{Account, SigningPubKey, TxnSignature}``) and
    its own top-level ``SigningPubKey`` is EMPTY ("") — that emptiness is how
    the ledger knows to consult the signer list. No list on the account →
    ``tefNOT_MULTI_SIGNING``; a signer not on the list → ``tefBAD_SIGNATURE``;
    combined weight below quorum → ``tefBAD_QUORUM``.
  * **Cost:** the fee is base_fee × (1 + number of signatures) — every
    co-signature is paid for — and the SignerList object itself holds one
    owner-reserve increment (~0.2 XRP) while it exists.

There is currently exactly one signer list per account (``SignerListID`` 0).
Signer entries do NOT need to be funded on-ledger accounts — a signature is
checked against the key that derives the listed address, so cold keys that
have never touched the ledger work fine.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..transport.base import SubmitResult, Transport

# The network's ceiling on SignerEntries (and xrpl-py's model constant).
MAX_SIGNER_ENTRIES = 32


def _preflight_signer_list(
    quorum: int,
    entries: list[tuple[str, int]],
    owner_address: str = "",
) -> SubmitResult | None:
    """Mirror the network's SignerListSet preflight; None means it passes.

    rippled rejects a malformed SignerListSet BEFORE the engine ever sees it
    (and xrpl-py's model raises at construction for the same set), so these
    are enforced locally with the network's own tem codes — the dry-run and
    testnet transports then reject identically, and the failing result
    teaches the rule instead of surfacing an opaque exception.
    """
    # Delete shape first: quorum=0 AND omit entries. Doing only one of the
    # two is temMALFORMED (the KB-verified bad-delete rule).
    if quorum == 0 and entries:
        return SubmitResult(
            success=False, result_code="temMALFORMED",
            error=(
                "Deleting a signer list requires SignerQuorum=0 AND omitting "
                "SignerEntries — a zero quorum WITH entries is temMALFORMED."
            ),
        )
    if quorum != 0 and not entries:
        return SubmitResult(
            success=False, result_code="temMALFORMED",
            error=(
                "A non-zero SignerQuorum requires SignerEntries — omitting "
                "them is only valid for a delete (SignerQuorum=0)."
            ),
        )
    if quorum == 0:
        return None  # a well-formed delete; nothing more to preflight
    if quorum < 0:
        return SubmitResult(
            success=False, result_code="temBAD_QUORUM",
            error="SignerQuorum cannot be negative (temBAD_QUORUM).",
        )
    if not 1 <= len(entries) <= MAX_SIGNER_ENTRIES:
        return SubmitResult(
            success=False, result_code="temMALFORMED",
            error=(
                f"A signer list holds 1-{MAX_SIGNER_ENTRIES} entries; got "
                f"{len(entries)} (temMALFORMED)."
            ),
        )
    accounts = [acct for acct, _w in entries]
    if owner_address and owner_address in accounts:
        return SubmitResult(
            success=False, result_code="temBAD_SIGNER",
            error=(
                "The account cannot appear in its OWN signer list "
                "(temBAD_SIGNER) — a signer list delegates authority to OTHER "
                "keys; the owner's key is governed by it, not part of it."
            ),
        )
    if len(set(accounts)) != len(accounts):
        return SubmitResult(
            success=False, result_code="temBAD_SIGNER",
            error=(
                "Duplicate signer account in SignerEntries (temBAD_SIGNER) — "
                "each signer may appear once; raise its SignerWeight instead "
                "of listing it twice."
            ),
        )
    if any(weight <= 0 for _a, weight in entries):
        return SubmitResult(
            success=False, result_code="temBAD_WEIGHT",
            error=(
                "Every SignerWeight must be a positive integer "
                "(temBAD_WEIGHT) — a zero-weight signer could never "
                "contribute toward the quorum."
            ),
        )
    weight_sum = sum(weight for _a, weight in entries)
    if quorum > weight_sum:
        return SubmitResult(
            success=False, result_code="temBAD_QUORUM",
            error=(
                f"SignerQuorum {quorum} exceeds the sum of the SignerWeights "
                f"({weight_sum}) — no combination of signatures could ever "
                "authorize a transaction (temBAD_QUORUM)."
            ),
        )
    return None


async def set_signer_list(
    transport: Transport,
    owner_seed: str,
    quorum: int,
    entries: list[tuple[str, int]],
    owner_address: str = "",
) -> SubmitResult:
    """Install (or wholesale-replace) the account's signer list (SignerListSet).

    ``entries`` is the FULL intended roster as ``(account, weight)`` pairs —
    the ledger replaces the whole list on every SignerListSet, never patches
    it. ``owner_address`` enables the owner-cannot-list-itself preflight here
    and keys the dry-run transport's per-account list state (the testnet path
    derives the owner from the seed).
    """
    entries = list(entries or [])
    rejected = _preflight_signer_list(quorum, entries, owner_address)
    if rejected is not None:
        return rejected
    return await transport.submit_signer_list_set(
        owner_seed, quorum, entries, owner_address
    )


async def delete_signer_list(
    transport: Transport,
    owner_seed: str,
    owner_address: str = "",
) -> SubmitResult:
    """Remove the account's signer list, freeing its owner reserve.

    The delete shape is exact: ``SignerQuorum=0`` AND ``SignerEntries``
    omitted (supplying only one of the two is ``temMALFORMED``). Safety rule
    worth knowing before mainnet: an account whose master key is disabled and
    that has no regular key CANNOT delete its signer list — the network
    refuses with ``tecNO_ALTERNATIVE_KEY`` rather than let the account brick
    itself. This module never disables the master key, so the delete is safe.
    """
    return await transport.submit_signer_list_set(owner_seed, 0, [], owner_address)


async def send_multisig_payment(
    transport: Transport,
    owner_address: str,
    destination: str,
    amount: str,
    signer_seeds: list[str],
    signer_addresses: list[str] | None = None,
    memo: str = "",
) -> SubmitResult:
    """Submit a multi-signed XRP Payment from the treasury account.

    Deliberately takes NO owner seed — the treasury's own key never signs.
    Each seed in ``signer_seeds`` contributes one entry to the transaction's
    ``Signers`` array; the ledger sums the listed weights of the valid
    signatures and compares against the quorum. The fee scales as
    base_fee × (1 + number of signatures). ``signer_addresses`` is the
    dry-run keying aid (parallel to ``signer_seeds``); the testnet path
    derives each address from its seed.
    """
    if not signer_seeds:
        return SubmitResult(
            success=False,
            result_code="local_error",
            error=(
                "No signers supplied. A multi-signed transaction carries a "
                "Signers array — with zero signatures there is no weight to "
                "sum and no quorum can ever be met."
            ),
        )
    if not destination:
        return SubmitResult(
            success=False,
            result_code="local_error",
            error="No destination supplied for the multi-signed payment.",
        )
    return await transport.submit_multisig_payment(
        owner_address, destination, amount, list(signer_seeds),
        signer_addresses=list(signer_addresses) if signer_addresses else None,
        memo=memo,
    )


@dataclass
class SignerListVerifyResult:
    """Result of verifying an account's signer list against expectations."""

    found: bool
    quorum: int
    entries: list[tuple[str, int]]
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


async def verify_signer_list(
    transport: Transport,
    owner: str,
    expected_quorum: int | None = None,
    expected_entries: list[tuple[str, int]] | None = None,
    expect_absent: bool = False,
) -> SignerListVerifyResult:
    """Read the account's SignerList back from the ledger and check it.

    With ``expect_absent=True`` the check inverts: the list must be GONE
    (the post-delete read-back). Otherwise the list must exist, and when
    ``expected_quorum`` / ``expected_entries`` are given they must match
    exactly — the roster is compared as a set of ``(account, weight)`` pairs,
    since the ledger stores entries in its own order.
    """
    checks: list[str] = []
    failures: list[str] = []

    info = await transport.get_signer_list(owner)

    if expect_absent:
        if info is None:
            checks.append(
                "No SignerList object on the account — the list is deleted "
                "and its owner reserve is freed"
            )
            return SignerListVerifyResult(False, 0, [], checks, failures)
        failures.append(
            f"A SignerList is still attached (quorum {info.signer_quorum}, "
            f"{len(info.entries)} signers) — the delete did not remove it"
        )
        return SignerListVerifyResult(
            True, info.signer_quorum, list(info.entries), checks, failures
        )

    if info is None:
        failures.append(
            "No SignerList object on the account — SignerListSet did not "
            "install one"
        )
        return SignerListVerifyResult(False, 0, [], checks, failures)

    checks.append(
        f"SignerList found: quorum {info.signer_quorum}, "
        f"{len(info.entries)} signer(s)"
    )
    if expected_quorum is not None:
        if info.signer_quorum == expected_quorum:
            checks.append(f"SignerQuorum matches ({expected_quorum})")
        else:
            failures.append(
                f"SignerQuorum is {info.signer_quorum}, expected {expected_quorum}"
            )
    if expected_entries is not None:
        want = {(acct, weight) for acct, weight in expected_entries}
        have = {(acct, weight) for acct, weight in info.entries}
        if want == have:
            checks.append(
                f"All {len(want)} signer entries match (accounts + weights)"
            )
        else:
            missing = want - have
            extra = have - want
            if missing:
                failures.append(
                    "Missing signer entries: "
                    + ", ".join(f"{a[:12]}... (w{w})" for a, w in sorted(missing))
                )
            if extra:
                failures.append(
                    "Unexpected signer entries: "
                    + ", ".join(f"{a[:12]}... (w{w})" for a, w in sorted(extra))
                )

    return SignerListVerifyResult(
        True, info.signer_quorum, list(info.entries), checks, failures
    )
