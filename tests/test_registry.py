"""Tests for the action registry."""

import pytest

from xrpl_lab.registry import (
    ActionDef,
    DuplicateActionError,
    PayloadError,
    PayloadField,
    PayloadSchema,
    UnknownActionError,
    all_actions,
    is_registered,
    register,
    resolve,
)


@pytest.fixture(autouse=True)
def _ensure_handlers_loaded():
    """Ensure handlers are registered (import triggers _register_all)."""
    import xrpl_lab.handlers  # noqa: F401
    yield


# ── Registry basics ──────────────────────────────────────────────────


class TestRegistry:
    def test_known_action_resolves(self):
        """All module actions from handlers.py should be registered."""
        # Import handlers to trigger registration
        import xrpl_lab.handlers  # noqa: F401

        action_def = resolve("ensure_wallet")
        assert action_def.name == "ensure_wallet"
        assert callable(action_def.handler)

    def test_unknown_action_fails(self):
        with pytest.raises(UnknownActionError, match="bogus_action"):
            resolve("bogus_action")

    def test_duplicate_registration_fails(self):
        async def _noop(step, state, transport, seed, ctx, console):
            return ctx

        # Use a unique name that won't collide with real actions
        name = "test_dup_check_9999"
        action_def = ActionDef(name=name, handler=_noop)
        register(action_def)
        try:
            with pytest.raises(DuplicateActionError, match=name):
                register(action_def)
        finally:
            # Clean up: remove the test entry from the global registry
            from xrpl_lab.registry import _REGISTRY
            _REGISTRY.pop(name, None)

    def test_is_registered(self):
        import xrpl_lab.handlers  # noqa: F401

        assert is_registered("submit_payment")
        assert not is_registered("completely_fake_action")

    def test_all_actions_complete(self):
        """Every action from the original dispatch should be in the registry."""
        import xrpl_lab.handlers  # noqa: F401

        expected = {
            "ensure_wallet", "ensure_funded",
            "submit_payment", "submit_payment_fail", "verify_tx",
            "create_issuer_wallet", "fund_issuer",
            "set_trust_line", "issue_token", "issue_token_expect_fail",
            "verify_trust_line", "remove_trust_line", "verify_trust_line_removed",
            "create_offer", "verify_offer_present", "cancel_offer", "verify_offer_absent",
            "snapshot_account", "verify_reserve_change", "run_audit",
            "ensure_amm_pair", "get_amm_info", "amm_deposit", "verify_lp_received",
            "amm_withdraw", "verify_withdrawal",
            "snapshot_position", "strategy_offer_bid", "strategy_offer_ask",
            "verify_module_offers", "cancel_module_offers", "verify_module_offers_absent",
            "verify_position_delta", "check_inventory", "place_safe_sides",
            "hygiene_summary", "write_report",
        }
        registered = set(all_actions().keys())
        assert expected <= registered, f"Missing: {expected - registered}"

    def test_wallet_required_metadata(self):
        """Actions that mutate the ledger should be flagged wallet_required."""
        import xrpl_lab.handlers  # noqa: F401

        wallet_required = {
            name for name, ad in all_actions().items() if ad.wallet_required
        }
        assert "submit_payment" in wallet_required
        assert "set_trust_line" in wallet_required
        assert "ensure_wallet" not in wallet_required
        assert "verify_tx" not in wallet_required


# ── Payload schema validation ────────────────────────────────────────


class TestPayloadSchema:
    def test_valid_string(self):
        schema = PayloadSchema(fields=(PayloadField(name="currency", default="XRP"),))
        result = schema.validate({"currency": "LAB"})
        assert result["currency"] == "LAB"

    def test_default_applied(self):
        schema = PayloadSchema(fields=(PayloadField(name="amount", default="10"),))
        result = schema.validate({})
        assert result["amount"] == "10"

    def test_missing_required(self):
        schema = PayloadSchema(fields=(PayloadField(name="dest", required=True),))
        with pytest.raises(PayloadError, match="Missing required"):
            schema.validate({})

    def test_unknown_field(self):
        schema = PayloadSchema(fields=(PayloadField(name="currency"),))
        with pytest.raises(PayloadError, match="Unknown field"):
            schema.validate({"currency": "X", "bogus": "y"})

    def test_int_coercion(self):
        schema = PayloadSchema(fields=(PayloadField(name="count", type="int"),))
        result = schema.validate({"count": "42"})
        assert result["count"] == 42

    def test_int_invalid(self):
        schema = PayloadSchema(fields=(PayloadField(name="count", type="int"),))
        with pytest.raises(PayloadError, match="Invalid int"):
            schema.validate({"count": "abc"})

    def test_decimal_coercion(self):
        from decimal import Decimal

        schema = PayloadSchema(fields=(PayloadField(name="amount", type="decimal"),))
        result = schema.validate({"amount": "3.14"})
        assert result["amount"] == Decimal("3.14")

    def test_bool_coercion(self):
        schema = PayloadSchema(fields=(PayloadField(name="flag", type="bool"),))
        assert schema.validate({"flag": "true"})["flag"] is True
        assert schema.validate({"flag": "false"})["flag"] is False
        assert schema.validate({"flag": "1"})["flag"] is True

    def test_enum_valid(self):
        schema = PayloadSchema(fields=(
            PayloadField(name="mode", type="enum", choices=("fast", "slow")),
        ))
        result = schema.validate({"mode": "fast"})
        assert result["mode"] == "fast"

    def test_enum_invalid(self):
        schema = PayloadSchema(fields=(
            PayloadField(name="mode", type="enum", choices=("fast", "slow")),
        ))
        with pytest.raises(PayloadError, match="Invalid value"):
            schema.validate({"mode": "turbo"})

    def test_list_coercion(self):
        schema = PayloadSchema(fields=(PayloadField(name="tags", type="list"),))
        result = schema.validate({"tags": "a,b,c"})
        assert result["tags"] == ["a", "b", "c"]
