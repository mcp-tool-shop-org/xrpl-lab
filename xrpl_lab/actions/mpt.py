"""MPT actions — create a Multi-Purpose Token issuance and verify it on-ledger (XLS-33)."""

from __future__ import annotations

from dataclasses import dataclass

from ..transport.base import MPTIssuanceInfo, SubmitResult, Transport


async def create_mpt_issuance(
    transport: Transport,
    wallet_seed: str,
    maximum_amount: str,
    asset_scale: int = 0,
    transfer_fee: int = 0,
    can_transfer: bool = True,
) -> SubmitResult:
    """Create a Multi-Purpose Token issuance (MPTokenIssuanceCreate)."""
    return await transport.submit_mpt_issuance_create(
        wallet_seed, maximum_amount, asset_scale, transfer_fee, can_transfer
    )


@dataclass
class MPTVerifyResult:
    """Result of verifying an MPT issuance on-ledger."""

    found: bool
    issuance: MPTIssuanceInfo | None
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


async def verify_mpt_issuance(
    transport: Transport,
    address: str,
    expected_maximum: str | None = None,
) -> MPTVerifyResult:
    """Verify the account created an MPT issuance (optionally with a given max supply)."""
    issuances = await transport.get_mpt_issuances(address)
    checks: list[str] = []
    failures: list[str] = []
    if not issuances:
        failures.append("No MPT issuances found for this account")
        return MPTVerifyResult(False, None, checks, failures)

    match = issuances[-1]
    checks.append(f"MPT issuance found: {match.issuance_id[:24]}...")
    checks.append(f"Maximum supply: {match.maximum_amount}")
    checks.append(f"Asset scale: {match.asset_scale}")
    checks.append(f"Transferable: {'yes' if match.flags & 0x20 else 'no'}")
    if match.transfer_fee:
        checks.append(f"Transfer fee: {match.transfer_fee / 1000:.3f}%")

    if expected_maximum is not None and match.maximum_amount != str(expected_maximum):
        failures.append(
            f"Max supply mismatch: expected {expected_maximum}, got {match.maximum_amount}"
        )
    return MPTVerifyResult(True, match, checks, failures)


# ── MPT distribution (FT-CURRIC-004): holder authorize + issuer payment ──


async def authorize_mpt(
    transport: Transport,
    holder_seed: str,
    issuance_id: str,
    unauthorize: bool = False,
    holder_address: str = "",
) -> SubmitResult:
    """Holder opts in to (or out of) holding an MPT issuance (MPTokenAuthorize).

    ``holder_address`` is the opting-in account, forwarded for the
    dry-run transport's per-holder authorization set (the testnet path
    ignores it and derives the account from the seed). Pass it whenever
    the holder is addressed by real address later — :func:`send_mpt` and
    :func:`verify_mpt_balance` both are, so without it the opt-in and the
    payment key different holders and the payment fails tecNO_AUTH.
    """
    return await transport.submit_mpt_authorize(
        holder_seed, issuance_id, unauthorize, holder_address=holder_address,
    )


async def send_mpt(
    transport: Transport,
    issuer_seed: str,
    destination: str,
    issuance_id: str,
    amount: str,
) -> SubmitResult:
    """Pay an amount of an MPT to a holder (Payment with an MPT Amount)."""
    return await transport.submit_mpt_payment(issuer_seed, destination, issuance_id, amount)


@dataclass
class MPTBalanceResult:
    """Result of reading + checking a holder's MPT balance."""

    balance: str
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


async def verify_mpt_balance(
    transport: Transport,
    holder: str,
    issuance_id: str,
    expected: str | None = None,
) -> MPTBalanceResult:
    """Read the holder's MPT balance, optionally asserting it equals ``expected``."""
    bal = await transport.get_mpt_balance(holder, issuance_id)
    checks: list[str] = [f"Holder MPT balance: {bal}"]
    failures: list[str] = []
    if expected is not None and str(bal) != str(expected):
        failures.append(f"MPT balance mismatch: expected {expected}, got {bal}")
    return MPTBalanceResult(bal, checks, failures)
