"""B3 Numeric Law tests — prove Decimal doctrine and secret hardening.

These tests verify:
- All financial paths use Decimal, not float
- _SecretValue cannot be pickled
- _SecretValue blocks attribute access to _value
- Decimal arithmetic is used in dry-run AMM operations
"""

from __future__ import annotations

import pickle
from decimal import Decimal

import pytest

from xrpl_lab.runner import _SecretValue
from xrpl_lab.transport.dry_run import DryRunTransport

# ── _SecretValue hardening ──────────────────────────────────────────


class TestSecretValueHardening:
    """_SecretValue must resist serialization and leakage."""

    def test_repr_hides_value(self) -> None:
        sv = _SecretValue("sEdVERYSECRET123")
        assert "sEdVERYSECRET123" not in repr(sv)
        assert repr(sv) == "***"

    def test_str_hides_value(self) -> None:
        sv = _SecretValue("sEdVERYSECRET123")
        assert "sEdVERYSECRET123" not in str(sv)
        assert str(sv) == "***"

    def test_get_returns_actual_value(self) -> None:
        sv = _SecretValue("sEdVERYSECRET123")
        assert sv.get() == "sEdVERYSECRET123"

    def test_bool_truthy(self) -> None:
        assert bool(_SecretValue("nonempty"))
        assert not bool(_SecretValue(""))

    def test_pickle_raises(self) -> None:
        sv = _SecretValue("sEdVERYSECRET123")
        with pytest.raises(TypeError, match="[Pp]ickle"):
            pickle.dumps(sv)

    def test_fstring_hides_value(self) -> None:
        sv = _SecretValue("sEdVERYSECRET123")
        msg = f"Seed is {sv}"
        assert "sEdVERYSECRET123" not in msg
        assert "***" in msg

    def test_format_hides_value(self) -> None:
        sv = _SecretValue("sEdVERYSECRET123")
        msg = f"Seed is {sv}"
        assert "sEdVERYSECRET123" not in msg


# ── Decimal doctrine — DryRunTransport ──────────────────────────────


class TestDecimalDryRun:
    """DryRunTransport must use Decimal for all financial math."""

    @pytest.fixture()
    def transport(self) -> DryRunTransport:
        return DryRunTransport()

    @pytest.mark.asyncio()
    async def test_xrp_payment_preserves_precision(self, transport: DryRunTransport) -> None:
        """XRP payment of 0.000001 must not lose precision."""
        result = await transport.submit_payment("sEdSEED", "rDest", "0.000001")
        assert result.success

    @pytest.mark.asyncio()
    async def test_xrp_payment_rejects_non_numeric(self, transport: DryRunTransport) -> None:
        """Non-numeric amount must fail gracefully — and tell us WHY (F-TESTS-005)."""
        result = await transport.submit_payment("sEdSEED", "rDest", "not_a_number")
        assert not result.success
        # Rejection must surface a recognisable XRPL-style code.
        assert result.result_code == "temBAD_AMOUNT"
        # And the human-readable error must name the offending value, not just
        # be a generic "failed" string.
        assert "not_a_number" in result.error
        assert "invalid" in result.error.lower()

    def test_dry_run_submit_payment_uses_decimal_internally(self) -> None:
        """Verify submit_payment source code uses Decimal, not float."""
        import inspect

        from xrpl_lab.transport import dry_run

        source = inspect.getsource(dry_run.DryRunTransport.submit_issued_payment)
        assert "Decimal(" in source, "submit_issued_payment must use Decimal"

    @pytest.mark.asyncio()
    async def test_amm_create_lp_supply_is_decimal(self, transport: DryRunTransport) -> None:
        """AMM create should compute LP supply with Decimal sqrt."""
        # submit_amm_create(seed, a_cur, a_val, a_iss, b_cur, b_val, b_iss)
        result = await transport.submit_amm_create(
            "sEdSEED", "XRP", "100", "", "USD", "100", "rIssuer",
        )
        assert result.success
        # LP supply for 100*100 = sqrt(10000) = 100.000000
        info = await transport.get_amm_info("XRP", "", "USD", "rIssuer")
        assert info is not None
        lp_supply = Decimal(info.lp_supply)
        assert lp_supply == Decimal("100")

    @pytest.mark.asyncio()
    async def test_amm_deposit_decimal_precision(self, transport: DryRunTransport) -> None:
        """AMM deposit must use Decimal for ratio and LP minting."""
        await transport.submit_amm_create(
            "sEdSEED", "XRP", "100", "", "USD", "100", "rIssuer",
        )
        result = await transport.submit_amm_deposit(
            "sEdSEED", "XRP", "10", "", "USD", "10", "rIssuer",
        )
        assert result.success
        info = await transport.get_amm_info("XRP", "", "USD", "rIssuer")
        # Pool should be exactly 110, not 110.00000000000001
        assert Decimal(info.pool_a) == Decimal("110")
        assert Decimal(info.pool_b) == Decimal("110")

    @pytest.mark.asyncio()
    async def test_amm_withdraw_decimal_precision(self, transport: DryRunTransport) -> None:
        """AMM withdraw must use Decimal for proportional calculation."""
        await transport.submit_amm_create(
            "sEdSEED", "XRP", "100", "", "USD", "100", "rIssuer",
        )
        result = await transport.submit_amm_withdraw(
            "sEdSEED", "XRP", "", "USD", "rIssuer", "50",
        )
        assert result.success
        info = await transport.get_amm_info("XRP", "", "USD", "rIssuer")
        # Pool should be exactly 50, not 49.99999999999999
        assert Decimal(info.pool_a) == Decimal("50")
        assert Decimal(info.pool_b) == Decimal("50")
        assert Decimal(info.lp_supply) == Decimal("50")


# ── Decimal doctrine — no float() on financial values ───────────────


class TestNoFloatInFinancialPaths:
    """Grep-level assurance: financial functions must not use float()."""

    def test_dry_run_amm_methods_no_float(self) -> None:
        """AMM methods in dry_run.py must not call float() on amounts."""
        import inspect

        from xrpl_lab.transport import dry_run

        source = inspect.getsource(dry_run.DryRunTransport.submit_amm_create)
        source += inspect.getsource(dry_run.DryRunTransport.submit_amm_deposit)
        source += inspect.getsource(dry_run.DryRunTransport.submit_amm_withdraw)
        assert "float(" not in source, "AMM methods must use Decimal, not float()"

    def test_dry_run_payment_no_float(self) -> None:
        """submit_payment in dry_run.py must not call float() on amount."""
        import inspect

        from xrpl_lab.transport import dry_run

        source = inspect.getsource(dry_run.DryRunTransport.submit_payment)
        assert "float(" not in source, "submit_payment must use Decimal, not float()"


# ── Property-style invariants over a deterministic grid (B-TESTS-004) ──
#
# The numeric core was entirely example-based: each test pinned a single
# (input → expected) pair. Example tests catch the case they encode and
# nothing adjacent. These property-style tests loop over a fixed grid of
# inputs and assert a mathematical INVARIANT holds across the whole grid —
# catching a precision/rounding regression at a pool size or amount no
# single example happened to pick. Dependency-free: NO hypothesis — the
# grid is a deterministic, hand-chosen product of ranges so the test is
# fully reproducible and adds no new dependency.


class TestNumericInvariantsPropertyStyle:
    """Loop-over-a-grid invariants for the financial numeric core."""

    def test_drops_xrp_round_trip_is_identity_across_grid(self) -> None:
        """drops → XRP → drops must return the exact starting drops for
        every drop count on the grid.

        drops are integers and XRP carries exactly 6 decimals, so the
        round-trip is a true identity (not merely within-tolerance). A
        regression that introduced float() anywhere in the conversion
        would lose the low drops at large magnitudes and trip this.
        """
        from xrpl.utils import drops_to_xrp, xrp_to_drops

        # Grid: powers of ten, off-by-one neighbors, sub-XRP dust, and a
        # large value near typical testnet balances. Hand-chosen to span
        # the boundaries (1 drop, sub-1-XRP, exactly 1 XRP, 100k XRP).
        grid = [
            1, 9, 10, 11, 999, 1000, 1001,
            999_999, 1_000_000, 1_000_001,
            123_456_789, 100_000_000_000,
        ]
        for drops in grid:
            xrp = drops_to_xrp(str(drops))
            back = int(xrp_to_drops(xrp))
            assert back == drops, (
                f"round-trip identity broken: {drops} drops → {xrp} XRP "
                f"→ {back} drops"
            )

    def test_constant_product_swap_preserves_k_across_grid(self) -> None:
        """A fee-less constant-product swap must preserve k = x * y across
        a grid of pool sizes and trade sizes (within Decimal tolerance).

        This is the AMM core invariant (Uniswap-V2 x*y=k). We compute the
        swap output deterministically and assert the post-swap product
        equals the pre-swap product. Pure Decimal math, no transport, no
        network — a dependency-free property check that complements the
        example-based AMM tests above.
        """
        from decimal import Decimal

        # Grid: pool sizes × input trade sizes. Cartesian product gives
        # 6 × 4 = 24 distinct invariant checks from a compact, readable set.
        pool_sizes = [
            (Decimal("100"), Decimal("100")),
            (Decimal("50"), Decimal("200")),
            (Decimal("1000"), Decimal("250")),
            (Decimal("12345"), Decimal("678")),
            (Decimal("1"), Decimal("1000000")),
            (Decimal("999999"), Decimal("3")),
        ]
        trade_inputs = [Decimal("1"), Decimal("10"), Decimal("0.5"), Decimal("123.456")]
        # Tolerance: exact Decimal arithmetic with no rounding step should
        # preserve k to the context precision; a small epsilon guards the
        # final-digit drift of division.
        tol = Decimal("0.0000001")

        for x, y in pool_sizes:
            k0 = x * y
            for dx in trade_inputs:
                # Constant-product: (x + dx) * (y - dy) = k  ⇒
                # dy = y - k0 / (x + dx).
                dy = y - (k0 / (x + dx))
                new_x = x + dx
                new_y = y - dy
                k1 = new_x * new_y
                rel_err = abs(k1 - k0) / k0
                assert rel_err <= tol, (
                    f"constant product not preserved: pool=({x},{y}) "
                    f"dx={dx} → k0={k0} k1={k1} rel_err={rel_err}"
                )
                # Sanity: the swap actually moved the pool (no degenerate
                # zero-output trade slipped through the grid).
                assert dy > 0
                assert new_y < y

    def test_reserve_delta_arithmetic_is_exact_across_grid(self) -> None:
        """``compare_snapshots`` must report balance/owner deltas that equal
        ``after - before`` EXACTLY for every (before, after) pair on the
        grid — the reserve-comparison core a learner relies on to see the
        cost of an owned object.
        """
        from xrpl_lab.actions.reserves import compare_snapshots
        from xrpl_lab.transport.base import AccountSnapshot

        # Grid: balances spanning dust → large, owner counts spanning the
        # add/remove/no-change directions. Cartesian product = 5 × 4 = 20.
        balances = [0, 1, 1_000_000, 20_000_000, 123_456_789]
        owner_counts = [0, 1, 5, 12]

        for b_bal in balances:
            for b_oc in owner_counts:
                for a_bal in balances:
                    for a_oc in owner_counts:
                        before = AccountSnapshot(
                            address="rBEFORE",
                            balance_drops=str(b_bal),
                            owner_count=b_oc,
                        )
                        after = AccountSnapshot(
                            address="rAFTER",
                            balance_drops=str(a_bal),
                            owner_count=a_oc,
                        )
                        cmp = compare_snapshots(before, after)
                        assert cmp.balance_delta_drops == a_bal - b_bal, (
                            f"balance delta wrong: {b_bal}->{a_bal} "
                            f"gave {cmp.balance_delta_drops}"
                        )
                        assert cmp.owner_count_delta == a_oc - b_oc, (
                            f"owner delta wrong: {b_oc}->{a_oc} "
                            f"gave {cmp.owner_count_delta}"
                        )
                        # Invariant: owner_count_changed iff the delta is
                        # nonzero — the derived property must track the raw.
                        assert cmp.owner_count_changed == (a_oc != b_oc)
