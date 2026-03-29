"""AMM actions — create pools, deposit, withdraw, verify LP tokens."""

from __future__ import annotations

from dataclasses import dataclass

from ..transport.base import AmmInfo, SubmitResult, Transport


async def ensure_amm_pair(
    transport: Transport,
    wallet_seed: str,
    asset_a_currency: str,
    asset_a_value: str,
    asset_a_issuer: str,
    asset_b_currency: str,
    asset_b_value: str,
    asset_b_issuer: str,
    trading_fee: int = 500,
) -> tuple[AmmInfo, SubmitResult | None]:
    """Ensure an AMM exists for the pair. Creates one if missing.

    Returns (amm_info, submit_result_or_None).
    """
    info = await transport.get_amm_info(
        asset_a_currency, asset_a_issuer,
        asset_b_currency, asset_b_issuer,
    )
    if info:
        return info, None

    result = await transport.submit_amm_create(
        wallet_seed=wallet_seed,
        asset_a_currency=asset_a_currency,
        asset_a_value=asset_a_value,
        asset_a_issuer=asset_a_issuer,
        asset_b_currency=asset_b_currency,
        asset_b_value=asset_b_value,
        asset_b_issuer=asset_b_issuer,
        trading_fee=trading_fee,
    )

    if not result.success:
        return AmmInfo(asset_a=asset_a_currency, asset_b=asset_b_currency), result

    info = await transport.get_amm_info(
        asset_a_currency, asset_a_issuer,
        asset_b_currency, asset_b_issuer,
    )
    return info or AmmInfo(asset_a=asset_a_currency, asset_b=asset_b_currency), result


async def amm_deposit(
    transport: Transport,
    wallet_seed: str,
    asset_a_currency: str,
    asset_a_value: str,
    asset_a_issuer: str,
    asset_b_currency: str,
    asset_b_value: str,
    asset_b_issuer: str,
) -> SubmitResult:
    """Deposit both assets into an AMM pool."""
    return await transport.submit_amm_deposit(
        wallet_seed=wallet_seed,
        asset_a_currency=asset_a_currency,
        asset_a_value=asset_a_value,
        asset_a_issuer=asset_a_issuer,
        asset_b_currency=asset_b_currency,
        asset_b_value=asset_b_value,
        asset_b_issuer=asset_b_issuer,
    )


async def amm_withdraw(
    transport: Transport,
    wallet_seed: str,
    asset_a_currency: str,
    asset_a_issuer: str,
    asset_b_currency: str,
    asset_b_issuer: str,
    lp_token_value: str = "",
) -> SubmitResult:
    """Withdraw from an AMM pool by returning LP tokens."""
    return await transport.submit_amm_withdraw(
        wallet_seed=wallet_seed,
        asset_a_currency=asset_a_currency,
        asset_a_issuer=asset_a_issuer,
        asset_b_currency=asset_b_currency,
        asset_b_issuer=asset_b_issuer,
        lp_token_value=lp_token_value,
    )


@dataclass
class AmmVerifyResult:
    """Result of verifying AMM/LP state."""

    ok: bool
    checks: list[str]
    failures: list[str]
    lp_balance: str = "0"
    pool_info: AmmInfo | None = None

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


async def verify_lp_received(
    transport: Transport,
    address: str,
    amm_info: AmmInfo,
    min_expected: float = 0.0,
) -> AmmVerifyResult:
    """Verify LP tokens were received after deposit."""
    checks: list[str] = []
    failures: list[str] = []

    lp_balance = await transport.get_lp_token_balance(
        address, amm_info.lp_token_currency, amm_info.lp_token_issuer,
    )
    try:
        balance_f = float(lp_balance)
    except (ValueError, TypeError):
        balance_f = 0.0
        failures.append(f"Could not parse LP balance: {lp_balance!r}")

    if balance_f > 0:
        checks.append(f"LP token balance: {lp_balance}")
    else:
        failures.append("No LP tokens received")

    if min_expected > 0 and balance_f < min_expected:
        failures.append(
            f"LP balance {lp_balance} below expected minimum {min_expected}"
        )

    # Refresh pool info using canonical issuer fields
    a_currency = (
        amm_info.asset_a.split("/")[0] if "/" in amm_info.asset_a else amm_info.asset_a
    )
    b_currency = (
        amm_info.asset_b.split("/")[0] if "/" in amm_info.asset_b else amm_info.asset_b
    )
    pool = await transport.get_amm_info(
        a_currency,
        amm_info.asset_a_issuer,
        b_currency,
        amm_info.asset_b_issuer,
    )
    if pool:
        checks.append(f"Pool A: {pool.pool_a}")
        checks.append(f"Pool B: {pool.pool_b}")
        checks.append(f"LP supply: {pool.lp_supply}")

    return AmmVerifyResult(
        ok=len(failures) == 0,
        checks=checks,
        failures=failures,
        lp_balance=lp_balance,
        pool_info=pool,
    )


async def verify_withdrawal(
    transport: Transport,
    address: str,
    amm_info: AmmInfo,
    lp_before: str = "0",
) -> AmmVerifyResult:
    """Verify LP tokens were returned/burned after withdrawal."""
    checks: list[str] = []
    failures: list[str] = []

    lp_balance = await transport.get_lp_token_balance(
        address, amm_info.lp_token_currency, amm_info.lp_token_issuer,
    )
    try:
        balance_f = float(lp_balance)
    except (ValueError, TypeError):
        balance_f = 0.0
        failures.append(f"Could not parse LP balance: {lp_balance!r}")
    try:
        before_f = float(lp_before)
    except (ValueError, TypeError):
        before_f = 0.0
        failures.append(f"Could not parse LP balance: {lp_before!r}")

    if balance_f == 0 and before_f == 0:
        failures.append(
            "LP balance was 0 before and after — no withdrawal detected"
        )
    elif balance_f < before_f:
        checks.append(
            f"LP tokens decreased: {lp_before} -> {lp_balance}"
        )
    elif balance_f == before_f and before_f > 0:
        failures.append(
            f"LP balance unchanged at {lp_balance} — withdrawal may have failed"
        )
    else:
        checks.append(f"LP token balance: {lp_balance}")

    if balance_f == 0:
        checks.append("All LP tokens returned — full withdrawal")

    return AmmVerifyResult(
        ok=len(failures) == 0,
        checks=checks,
        failures=failures,
        lp_balance=lp_balance,
        pool_info=amm_info,
    )
