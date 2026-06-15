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
