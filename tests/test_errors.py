"""Tests for structured errors — LabError, LabException, constructors."""

from __future__ import annotations

from xrpl_lab.errors import (
    LabError,
    LabException,
    corrupt_state,
    module_not_found,
    network_error,
    no_wallet,
    tx_failed,
)


class TestLabError:
    def test_required_fields(self):
        err = LabError(code="INPUT_TEST", message="Test message", hint="Test hint")
        assert err.code == "INPUT_TEST"
        assert err.message == "Test message"
        assert err.hint == "Test hint"

    def test_optional_cause_default_none(self):
        err = LabError(code="INPUT_TEST", message="msg", hint="hint")
        assert err.cause is None

    def test_optional_retryable_default_false(self):
        err = LabError(code="INPUT_TEST", message="msg", hint="hint")
        assert err.retryable is False


class TestSafeDict:
    def test_always_includes_code_message_hint(self):
        err = LabError(code="INPUT_X", message="msg", hint="hint")
        d = err.safe_dict()
        assert "code" in d
        assert "message" in d
        assert "hint" in d

    def test_no_stack_trace(self):
        err = LabError(code="INPUT_X", message="msg", hint="hint")
        d = err.safe_dict()
        # Ensure no raw Python traceback or exception repr bleeds in
        assert "Traceback" not in str(d)
        assert "Exception" not in str(d)

    def test_cause_included_when_set(self):
        err = LabError(code="IO_X", message="msg", hint="hint", cause="some detail")
        d = err.safe_dict()
        assert "cause" in d
        assert d["cause"] == "some detail"

    def test_cause_omitted_when_none(self):
        err = LabError(code="IO_X", message="msg", hint="hint")
        d = err.safe_dict()
        assert "cause" not in d

    def test_retryable_included_when_true(self):
        err = LabError(code="RUNTIME_X", message="msg", hint="hint", retryable=True)
        d = err.safe_dict()
        assert "retryable" in d
        assert d["retryable"] is True

    def test_retryable_omitted_when_false(self):
        err = LabError(code="RUNTIME_X", message="msg", hint="hint", retryable=False)
        d = err.safe_dict()
        assert "retryable" not in d


class TestExitCodes:
    def test_input_prefix_exits_1(self):
        exc = LabException(LabError(code="INPUT_MODULE_NOT_FOUND", message="m", hint="h"))
        assert exc.exit_code == 1

    def test_config_prefix_exits_1(self):
        exc = LabException(LabError(code="CONFIG_BAD", message="m", hint="h"))
        assert exc.exit_code == 1

    def test_state_prefix_exits_1(self):
        exc = LabException(LabError(code="STATE_NO_WALLET", message="m", hint="h"))
        assert exc.exit_code == 1

    def test_io_prefix_exits_2(self):
        exc = LabException(LabError(code="IO_WRITE_FAIL", message="m", hint="h"))
        assert exc.exit_code == 2

    def test_dep_prefix_exits_2(self):
        exc = LabException(LabError(code="DEP_MISSING", message="m", hint="h"))
        assert exc.exit_code == 2

    def test_runtime_prefix_exits_2(self):
        exc = LabException(LabError(code="RUNTIME_NETWORK", message="m", hint="h"))
        assert exc.exit_code == 2

    def test_perm_prefix_exits_2(self):
        exc = LabException(LabError(code="PERM_DENIED", message="m", hint="h"))
        assert exc.exit_code == 2

    def test_partial_prefix_exits_3(self):
        exc = LabException(LabError(code="PARTIAL_BATCH", message="m", hint="h"))
        assert exc.exit_code == 3

    def test_unknown_prefix_exits_2(self):
        exc = LabException(LabError(code="UNKNOWN_THING", message="m", hint="h"))
        assert exc.exit_code == 2

    def test_exception_message_matches_error_message(self):
        err = LabError(code="INPUT_X", message="The error message", hint="h")
        exc = LabException(err)
        assert str(exc) == "The error message"

    def test_error_accessible_on_exception(self):
        err = LabError(code="INPUT_X", message="msg", hint="hint")
        exc = LabException(err)
        assert exc.error is err


class TestErrorConstructors:
    def test_module_not_found_code(self):
        err = module_not_found("receipt_literacy")
        assert err.code == "INPUT_MODULE_NOT_FOUND"

    def test_module_not_found_message_contains_id(self):
        err = module_not_found("receipt_literacy")
        assert "receipt_literacy" in err.message

    def test_module_not_found_has_hint(self):
        err = module_not_found("receipt_literacy")
        assert err.hint

    def test_no_wallet_code(self):
        err = no_wallet()
        assert err.code == "STATE_NO_WALLET"

    def test_no_wallet_message(self):
        err = no_wallet()
        assert err.message

    def test_no_wallet_hint(self):
        err = no_wallet()
        assert err.hint
        assert "wallet" in err.hint.lower()

    def test_network_error_code(self):
        err = network_error("connection refused")
        assert err.code == "RUNTIME_NETWORK"

    def test_network_error_retryable(self):
        err = network_error("timeout")
        assert err.retryable is True

    def test_network_error_cause_contains_detail(self):
        err = network_error("connection refused")
        assert err.cause == "connection refused"

    def test_corrupt_state_code(self):
        err = corrupt_state("bad json")
        assert err.code == "STATE_CORRUPT"

    def test_corrupt_state_cause(self):
        err = corrupt_state("bad json")
        assert err.cause == "bad json"

    def test_tx_failed_code(self):
        err = tx_failed("tecUNFUNDED")
        assert err.code == "RUNTIME_TX_FAILED"

    def test_tx_failed_message_contains_result_code(self):
        err = tx_failed("tecUNFUNDED")
        assert "tecUNFUNDED" in err.message

    def test_tx_failed_with_detail(self):
        err = tx_failed("tecNO_DST", detail="no destination account")
        assert err.cause == "no destination account"

    def test_tx_failed_no_detail_no_cause(self):
        err = tx_failed("tecNO_DST")
        assert err.cause is None
