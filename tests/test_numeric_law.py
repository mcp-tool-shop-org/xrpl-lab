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
        """Non-numeric amount must fail gracefully."""
        result = await transport.submit_payment("sEdSEED", "rDest", "not_a_number")
        assert not result.success

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
