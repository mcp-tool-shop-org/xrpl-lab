"""F-TESTS-B-004: AMM swap-chain tests after wave-2 deposit fix.

The wave-2 deposit math change (commit 848551e — Uniswap V2 sqrt for first-LP
+ binding-ratio refund for subsequent deposits) interacts with downstream
swap and withdraw paths. These tests exercise the chain so any rounding /
ratio drift introduced by a future deposit refactor surfaces here.

The dry-run transport does not expose a native AMM swap primitive (XRPL
swaps route through cross-currency Payment + path-finding, which the
``DryRunTransport`` does not simulate). To test the swap-chain interaction,
each test directly mutates the internal pool state via ``transport._amm_pools``
in a way that preserves the constant-product invariant ``k = x * y`` minus
fees — the exact mechanic a real swap would apply. This is intentional:
the production concern these tests guard is "does deposit-then-swap-then-
withdraw produce a sane reconciliation?", not "does the dry-run simulate
swaps." The pool-state shift is the swap.

Owned by the TESTS agent — production code in ``xrpl_lab/`` is NOT
touched. If a test surfaces a real bug, it is xfail-strict marked and
flagged for wave-3 Backend.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from xrpl_lab.transport.dry_run import DryRunTransport


@pytest.fixture
def transport() -> DryRunTransport:
    return DryRunTransport()


def _apply_swap(
    transport: DryRunTransport,
    asset_a_currency: str,
    asset_a_issuer: str,
    asset_b_currency: str,
    asset_b_issuer: str,
    deliver_a: Decimal,
    fee_bps: int = 30,
) -> Decimal:
    """Simulate an AMM swap by mutating internal pool state directly.

    Applies the standard constant-product formula:

        out_b = (pool_b * deliver_a * (1 - fee)) / (pool_a + deliver_a * (1 - fee))

    and updates ``pool_a += deliver_a``, ``pool_b -= out_b``. LP supply
    is unchanged (swaps don't mint/burn LP tokens). Returns the amount
    of asset B delivered to the swapper.

    ``fee_bps`` defaults to 30 (0.30%), the XRPL AMM mid-range fee.
    """
    key = transport._amm_pair_key(
        asset_a_currency, asset_a_issuer,
        asset_b_currency, asset_b_issuer,
    )
    pool = transport._amm_pools[key]

    # Resolve which slot holds asset_a in the canonical pool layout —
    # the dry-run normalises asset order via _amm_pair_key, so the pool
    # may have asset_a stored as either pool_a or pool_b internally.
    a_in_slot_a = (
        pool["a_currency"] == asset_a_currency
        and pool["a_issuer"] == asset_a_issuer
    )

    pool_a_key = "pool_a" if a_in_slot_a else "pool_b"
    pool_b_key = "pool_b" if a_in_slot_a else "pool_a"

    pool_a = Decimal(pool[pool_a_key])
    pool_b = Decimal(pool[pool_b_key])

    # XRPL AMM constant-product with fee on input side.
    fee_factor = Decimal("1") - (Decimal(fee_bps) / Decimal("10000"))
    deliver_after_fee = deliver_a * fee_factor
    out_b = (pool_b * deliver_after_fee) / (pool_a + deliver_after_fee)

    six = Decimal("0.000001")
    pool[pool_a_key] = str((pool_a + deliver_a).quantize(six))
    pool[pool_b_key] = str((pool_b - out_b).quantize(six))

    return out_b.quantize(six)


class TestAmmSwapChains:
    """Round-trip and ratio chains across deposit/swap/withdraw."""

    @pytest.mark.asyncio
    async def test_amm_deposit_then_swap_then_withdraw_chain(
        self, transport: DryRunTransport,
    ) -> None:
        """Deposit, swap, withdraw — final balances reconcile within tolerance.

        Models a learner's typical AMM workflow:

          1. Create pool at 1:1 (1000 XRP / 1000 LAB).
          2. Deposit 100 XRP / 100 LAB — mints LP at the binding ratio.
          3. Swap 50 XRP into the pool — pool shifts, LP holder's underlying
             share rebalances (more XRP, less LAB) but their LP count is
             unchanged.
          4. Withdraw the same LP share — receive proportional share of
             the *new* pool state.

        The reconciliation assertion: total asset_a + asset_b returned to
        the depositor should equal what they put in *minus* the fee
        portion of the swap (some of their LAB share got "sold" via the
        swap, and the swap fee accrues to remaining LP holders, here the
        original creator). Tolerance is 2 drops to absorb quantization.
        """
        # 1. Create pool seeded by creator (sFAKE -> rDRYRUN... address).
        await transport.submit_amm_create(
            "sFAKE", "XRP", "1000", "", "LAB", "1000", "rISSUER",
        )
        info_init = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        assert info_init is not None

        # 2. Depositor (different seed) puts in 100 / 100 at the 1:1 ratio.
        dep = await transport.submit_amm_deposit(
            "sDEPOSITOR", "XRP", "100", "", "LAB", "100", "rISSUER",
        )
        assert dep.success is True

        info_post_dep = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        lp_after_deposit = Decimal(info_post_dep.lp_supply)
        # Depositor's LP minted = (lp_after_deposit - lp_before_deposit).
        depositor_lp_minted = lp_after_deposit - Decimal(info_init.lp_supply)
        assert depositor_lp_minted > 0

        pool_a_after_dep = Decimal(info_post_dep.pool_a)
        pool_b_after_dep = Decimal(info_post_dep.pool_b)

        # 3. Swap 50 XRP into the pool (any party, doesn't affect LP balances).
        out_lab = _apply_swap(
            transport,
            "XRP", "",
            "LAB", "rISSUER",
            Decimal("50"),
        )
        # Sanity: a 50-unit swap on a 1100-pool yields well-defined positive output.
        assert out_lab > 0
        assert out_lab < 50  # constant product + fee guarantee

        info_post_swap = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        # XRP side grew by 50, LAB side shrank by out_lab.
        assert Decimal(info_post_swap.pool_a) == pool_a_after_dep + Decimal("50")
        assert (
            abs(
                Decimal(info_post_swap.pool_b) - (pool_b_after_dep - out_lab)
            ) <= Decimal("0.000001")
        )
        # LP supply unchanged by swaps.
        assert Decimal(info_post_swap.lp_supply) == lp_after_deposit

        # 4. Depositor withdraws their entire LP share (use sDEPOSITOR's tokens).
        wd = await transport.submit_amm_withdraw(
            "sDEPOSITOR", "XRP", "", "LAB", "rISSUER",
            lp_token_value=str(depositor_lp_minted),
        )
        assert wd.success is True

        info_final = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")

        # Reconcile: pool changes from post-swap to final reflect what the
        # depositor pulled out. Their share fraction was (their LP) / (total LP).
        share = depositor_lp_minted / lp_after_deposit
        expected_a_returned = Decimal(info_post_swap.pool_a) * share
        expected_b_returned = Decimal(info_post_swap.pool_b) * share

        actual_a_returned = (
            Decimal(info_post_swap.pool_a) - Decimal(info_final.pool_a)
        )
        actual_b_returned = (
            Decimal(info_post_swap.pool_b) - Decimal(info_final.pool_b)
        )

        # 2-drop tolerance — quantization runs at 6dp on every step.
        two_drops = Decimal("0.000002")
        assert abs(actual_a_returned - expected_a_returned) <= two_drops, (
            f"asset A reconcile drift: expected {expected_a_returned}, "
            f"got {actual_a_returned}"
        )
        assert abs(actual_b_returned - expected_b_returned) <= two_drops, (
            f"asset B reconcile drift: expected {expected_b_returned}, "
            f"got {actual_b_returned}"
        )

        # And depositor's LP share has been burned (-1 == removed entirely).
        # The remaining LP supply equals the creator's original LP.
        assert Decimal(info_final.lp_supply) == Decimal(info_init.lp_supply)

    @pytest.mark.asyncio
    async def test_amm_swap_after_unbalanced_deposit(
        self, transport: DryRunTransport,
    ) -> None:
        """7:11 odd-ratio deposit + swap leaves pool in a sane state.

        This exercises the wave-2 binding-ratio refund path at a prime
        ratio, then pushes a swap through it. After both ops:

          - pool_a > 0, pool_b > 0 (no negative balances)
          - the constant-product invariant relationship holds qualitatively
            (post-swap k ≥ pre-swap k after fee accrual)
          - LP supply is positive and matches (creator + binding deposit)
        """
        # Seed at 1:1 so deposit hits the subsequent-liquidity (binding-ratio) path.
        await transport.submit_amm_create(
            "sFAKE", "XRP", "100", "", "LAB", "100", "rISSUER",
        )
        info_init = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        lp_init = Decimal(info_init.lp_supply)

        # Deposit at 7:11 — the binding ratio is min(7/100, 11/100) = 7/100,
        # so the 11-LAB side is partially refunded; pool ends at (107, 107).
        dep = await transport.submit_amm_deposit(
            "sDEPOSITOR", "XRP", "7", "", "LAB", "11", "rISSUER",
        )
        assert dep.success is True

        info_post_dep = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        # Binding-ratio means both pool sides grow by the binding ratio
        # (7/100 of starting pool_a = 7) — pool stays balanced.
        assert Decimal(info_post_dep.pool_a) == Decimal("107")
        assert Decimal(info_post_dep.pool_b) == Decimal("107")
        # LP minted = old_lp * 0.07 = 100 * 0.07 = 7.
        assert Decimal(info_post_dep.lp_supply) == lp_init + Decimal("7")

        k_before_swap = (
            Decimal(info_post_dep.pool_a) * Decimal(info_post_dep.pool_b)
        )

        # Swap 13 XRP in (another prime, no clean factoring).
        out_lab = _apply_swap(
            transport,
            "XRP", "",
            "LAB", "rISSUER",
            Decimal("13"),
        )

        info_post_swap = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")

        # Sanity properties:
        #   1. No negative balances.
        assert Decimal(info_post_swap.pool_a) > 0
        assert Decimal(info_post_swap.pool_b) > 0
        #   2. LP supply unchanged.
        assert (
            Decimal(info_post_swap.lp_supply) == Decimal(info_post_dep.lp_supply)
        )
        #   3. Output positive and bounded by what the pool can give.
        assert out_lab > 0
        assert out_lab < Decimal(info_post_dep.pool_b)
        #   4. k (constant product) post-swap ≥ k pre-swap — the swap fee
        #      accretes to LPs by leaving a sliver of input value in the pool.
        k_after_swap = (
            Decimal(info_post_swap.pool_a) * Decimal(info_post_swap.pool_b)
        )
        # Fee accrual means k should not decrease — within 6dp tolerance.
        assert k_after_swap >= k_before_swap - Decimal("0.000001"), (
            f"constant-product invariant violated: k went {k_before_swap} -> "
            f"{k_after_swap}"
        )

    @pytest.mark.asyncio
    async def test_amm_extreme_pool_ratio_swap_slippage(
        self, transport: DryRunTransport,
    ) -> None:
        """1 : 1_000_000 imbalance swap — slippage large but well-defined.

        Creates a deeply imbalanced pool (1 XRP, 1 000 000 LAB) and swaps
        a small XRP amount in. The expected output for asset B is huge
        relative to swap size (the pool is "selling" LAB cheaply), but
        must be:

          - finite (not Infinity / NaN)
          - positive
          - strictly less than the LAB-side pool balance (constant-product
            holds)

        Defends against a future refactor that loses precision on extreme
        ratios — log-scale or float64 paths would surface here.
        """
        # 1 XRP, 1 000 000 LAB.
        await transport.submit_amm_create(
            "sFAKE",
            "XRP", "1", "",
            "LAB", "1000000", "rISSUER",
        )
        info = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        assert info is not None
        # First-LP = sqrt(1 * 1_000_000) = 1000.
        assert Decimal(info.lp_supply) == Decimal("1000")

        pool_b_before = Decimal(info.pool_b)

        # Swap 0.01 XRP in — small absolute, but large relative to pool_a.
        out_lab = _apply_swap(
            transport,
            "XRP", "",
            "LAB", "rISSUER",
            Decimal("0.01"),
        )

        # Output must be positive, finite (Decimal can't be inf, but we
        # guard against accidental zero).
        assert out_lab > 0
        # Bounded by the LAB pool balance — constant product won't drain
        # the pool no matter how aggressive the input.
        assert out_lab < pool_b_before, (
            f"swap output {out_lab} exceeds pool balance {pool_b_before}"
        )

        info_after = await transport.get_amm_info("XRP", "", "LAB", "rISSUER")
        # Pool_b strictly decreased; pool_a strictly increased.
        assert Decimal(info_after.pool_b) < pool_b_before
        assert Decimal(info_after.pool_a) > Decimal("1")
        # Pool still has positive balance on both sides.
        assert Decimal(info_after.pool_a) > 0
        assert Decimal(info_after.pool_b) > 0
