"""Testnet-transport AMM (XLS-30) implementation tests — network fully mocked.

The AMM block of ``XRPLTestnetTransport`` used to be stubs returning
``result_code="notSupported"``; it now submits real AMMCreate / AMMDeposit /
AMMWithdraw transactions and answers reads from ``amm_info`` /
``account_lines``. These tests pin that behavior OFFLINE — ``_rpc_client``,
``submit_and_wait`` and the sequence prefetch are patched exactly like
tests/test_reswarm4_transport.py, so no socket ever opens.

Pinned contracts:

- AMMCreate carries the XLS-30 special fee — the incremental owner reserve
  (``server_state.validated_ledger.reserve_inc``), pinned BEFORE signing —
  never the standard 10-drop fee.
- AMMDeposit is a two-asset deposit (tfTwoAsset), XRP leg in drops.
- AMMWithdraw with an empty ``lp_token_value`` uses tfWithdrawAll; a value
  uses tfLPToken with the pool's LP-token currency/issuer resolved via
  ``amm_info``.
- ``get_amm_info`` returns None on ``entryNotFound`` (the "no pool for this
  pair" answer) and on RPC failure; a populated pool parses to AmmInfo.
- ``get_lp_token_balance`` reads the matching trust line from
  ``account_lines``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from xrpl.asyncio.transaction import XRPLReliableSubmissionException
from xrpl.models.transactions import (
    AccountSetAsfFlag,
    AMMDepositFlag,
    AMMWithdrawFlag,
)
from xrpl.wallet import Wallet

from xrpl_lab.transport import xrpl_testnet as xt
from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

# A real-format testnet seed (same one test_reswarm4_transport.py uses) so
# Wallet.from_seed derives a valid account offline; no network call happens.
_SEED = "sEdTM1uX8pu2do5XvTnutH6HsouMaM2"
_EXPECTED_ACCOUNT = Wallet.from_seed(_SEED).address

_ISSUER = "rISSUERAAAAAAAAAAAAAAAAAAAAAAA"
_AMM_ACCOUNT = "rAMMAAAAAAAAAAAAAAAAAAAAAAA"
_LP_CURRENCY = "AB" * 20  # 40-hex — LP-Token currencies are non-standard 160-bit codes
_RESERVE_INC_DROPS = "2000000"  # 2 XRP — testnet's incremental owner reserve
_PINNED_SEQ = 5_010_042
_TXID = "E3FE" + "0" * 60


def _submit_ok(txid: str = _TXID, fee: str = _RESERVE_INC_DROPS) -> dict:
    """Minimal API-v2 submit response for a validated tesSUCCESS."""
    return {
        "hash": txid,
        "ledger_index": 12345678,
        "meta": {"TransactionResult": "tesSUCCESS"},
        "tx_json": {"Fee": fee, "Sequence": _PINNED_SEQ},
        "validated": True,
    }


def _amm_info_result() -> dict:
    """A realistic amm_info success payload for an XRP/LAB pool."""
    return {
        "amm": {
            "account": _AMM_ACCOUNT,
            "amount": "100000000",  # 100 XRP, in drops
            "amount2": {
                "currency": "LAB",
                "issuer": _ISSUER,
                "value": "100",
            },
            "lp_token": {
                "currency": _LP_CURRENCY,
                "issuer": _AMM_ACCOUNT,
                "value": "100",
            },
            "trading_fee": 500,
        },
        "ledger_current_index": 12345670,
        "validated": False,
    }


class _FakeClient:
    """Routes canned results by request class name; records the call log.

    The SAME instance is served by the patched ``_rpc_client`` for every
    context-manager entry in a test, so ``requests`` accumulates across the
    fee probe / amm_info / account_lines reads of one method call.
    """

    def __init__(self, results_by_name: dict, fail_names: frozenset = frozenset()):
        self._results = results_by_name
        self._fail_names = fail_names
        self.requests: list[str] = []

    async def request(self, req, *args, **kwargs):
        name = type(req).__name__
        self.requests.append(name)
        if name in self._fail_names:
            raise TimeoutError("simulated RPC timeout")
        return _FakeResponse(self._results.get(name, {}))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeResponse:
    def __init__(self, result: dict) -> None:
        self.result = result


def _patch_network(monkeypatch: pytest.MonkeyPatch, client: _FakeClient) -> list:
    """Patch the transport's network seams; returns the captured-tx list."""
    monkeypatch.delenv("XRPL_LAB_RPC_URL", raising=False)  # default testnet
    monkeypatch.setattr(xt, "_rpc_client", lambda url: client)

    submitted: list = []

    async def _fake_submit_and_wait(tx, client, wallet=None):
        submitted.append(tx)
        return _FakeResponse(_submit_ok())

    async def _fake_next_seq(account, c, *args, **kwargs):
        return _PINNED_SEQ

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(xt, "submit_and_wait", _fake_submit_and_wait)
    monkeypatch.setattr(xt, "get_next_valid_seq_number", _fake_next_seq)
    monkeypatch.setattr(xt.asyncio, "sleep", _no_sleep)
    return submitted


@pytest.fixture()
def transport(monkeypatch: pytest.MonkeyPatch) -> XRPLTestnetTransport:
    monkeypatch.delenv("XRPL_LAB_RPC_URL", raising=False)
    return XRPLTestnetTransport()


class TestAmmCreateTestnet:
    @pytest.mark.asyncio
    async def test_create_pins_owner_reserve_fee_and_two_assets(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _FakeClient({
            "ServerState": {
                "state": {
                    "validated_ledger": {
                        "reserve_base": "10000000",
                        "reserve_inc": _RESERVE_INC_DROPS,
                    }
                }
            }
        })
        submitted = _patch_network(monkeypatch, client)

        result = await transport.submit_amm_create(
            _SEED, "XRP", "100", "", "LAB", "100", _ISSUER,
            trading_fee=500, wallet_address=_EXPECTED_ACCOUNT,
        )

        assert result.success is True
        assert result.result_code == "tesSUCCESS"
        assert result.txid == _TXID
        assert result.explorer_url == f"https://testnet.xrpl.org/transactions/{_TXID}"

        assert len(submitted) == 1
        tx = submitted[0]
        assert type(tx).__name__ == "AMMCreate"
        # Account derives from the signing seed — the dry-run wallet_address
        # hint is the signer check when the seed isn't bound (2.7.0).
        assert tx.account == _EXPECTED_ACCOUNT
        # The XLS-30 special fee: EXACTLY the incremental owner reserve,
        # pinned before signing — not the standard 10-drop fee.
        assert tx.fee == _RESERVE_INC_DROPS
        # XRP leg converted to drops; token leg issued-amount; sequence
        # pinned by _submit_tx.
        assert str(tx.amount) == "100000000"
        assert tx.amount2.to_dict() == {
            "currency": "LAB",
            "issuer": _ISSUER,
            "value": "100",
        }
        assert tx.trading_fee == 500
        assert tx.sequence == _PINNED_SEQ
        assert "ServerState" in client.requests

    @pytest.mark.asyncio
    async def test_create_fee_probe_failure_falls_back_to_autofill(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If server_state is unreachable the fee stays unset (fee=None) so
        xrpl-py's autofill computes the same AMM_CREATE special fee itself."""
        client = _FakeClient({}, fail_names=frozenset({"ServerState"}))
        submitted = _patch_network(monkeypatch, client)

        result = await transport.submit_amm_create(
            _SEED, "XRP", "100", "", "LAB", "100", _ISSUER,
        )

        assert result.success is True
        assert submitted[0].fee is None

    @pytest.mark.asyncio
    async def test_create_validated_failure_maps_real_code(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A validated tec (e.g. tecDUPLICATE) parses to the REAL result code
        and submits exactly once — a landed tec must never be resubmitted."""
        client = _FakeClient({
            "ServerState": {
                "state": {"validated_ledger": {"reserve_inc": _RESERVE_INC_DROPS}}
            }
        })
        submitted = _patch_network(monkeypatch, client)

        async def _raise_tec(tx, client, wallet=None):
            submitted.append(tx)
            raise XRPLReliableSubmissionException("Transaction failed: tecDUPLICATE")

        monkeypatch.setattr(xt, "submit_and_wait", _raise_tec)

        result = await transport.submit_amm_create(
            _SEED, "XRP", "100", "", "LAB", "100", _ISSUER,
        )

        assert result.success is False
        assert result.result_code == "tecDUPLICATE"
        assert len(submitted) == 1

    @pytest.mark.asyncio
    async def test_create_never_returns_not_supported(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: the old stub's notSupported result is gone for good."""
        client = _FakeClient({})
        _patch_network(monkeypatch, client)

        result = await transport.submit_amm_create(
            _SEED, "XRP", "100", "", "LAB", "100", _ISSUER,
        )

        assert result.result_code != "notSupported"


class TestAmmDepositTestnet:
    @pytest.mark.asyncio
    async def test_deposit_is_two_asset_with_xrp_in_drops(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _FakeClient({})
        submitted = _patch_network(monkeypatch, client)

        result = await transport.submit_amm_deposit(
            _SEED, "XRP", "10", "", "LAB", "10", _ISSUER,
            wallet_address=_EXPECTED_ACCOUNT,
        )

        assert result.success is True
        assert result.result_code == "tesSUCCESS"

        tx = submitted[0]
        assert type(tx).__name__ == "AMMDeposit"
        assert tx.account == _EXPECTED_ACCOUNT
        assert int(tx.flags) == int(AMMDepositFlag.TF_TWO_ASSET)
        assert str(tx.amount) == "10000000"  # 10 XRP in drops
        assert tx.amount2.to_dict() == {"currency": "LAB", "issuer": _ISSUER, "value": "10"}
        # Deposits pay the standard fee via autofill — the special fee probe
        # belongs to AMMCreate only.
        assert "ServerState" not in client.requests

    @pytest.mark.asyncio
    async def test_deposit_validated_failure_maps_real_code(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _FakeClient({})
        _patch_network(monkeypatch, client)

        async def _raise_tec(tx, client, wallet=None):
            raise XRPLReliableSubmissionException("Transaction failed: tecAMM_NOT_FOUND")

        monkeypatch.setattr(xt, "submit_and_wait", _raise_tec)

        result = await transport.submit_amm_deposit(
            _SEED, "XRP", "10", "", "LAB", "10", _ISSUER,
        )

        assert result.success is False
        assert result.result_code == "tecAMM_NOT_FOUND"


class TestAmmWithdrawTestnet:
    @pytest.mark.asyncio
    async def test_withdraw_all_uses_tf_withdraw_all_without_pool_lookup(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty lp_token_value == the action layer's 'returning all LP
        tokens' — tfWithdrawAll, and no amm_info lookup is needed."""
        client = _FakeClient({})
        submitted = _patch_network(monkeypatch, client)

        result = await transport.submit_amm_withdraw(
            _SEED, "XRP", "", "LAB", _ISSUER,
        )

        assert result.success is True
        tx = submitted[0]
        assert type(tx).__name__ == "AMMWithdraw"
        assert int(tx.flags) == int(AMMWithdrawFlag.TF_WITHDRAW_ALL)
        assert tx.lp_token_in is None
        assert "AMMInfo" not in client.requests

    @pytest.mark.asyncio
    async def test_withdraw_lp_token_value_resolves_pool(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A numeric lp_token_value (tfLPToken) names the pool's OWN LP
        token — currency + AMM-account issuer resolved via amm_info."""
        client = _FakeClient({"AMMInfo": _amm_info_result()})
        submitted = _patch_network(monkeypatch, client)

        result = await transport.submit_amm_withdraw(
            _SEED, "XRP", "", "LAB", _ISSUER, lp_token_value="5",
        )

        assert result.success is True
        tx = submitted[0]
        assert int(tx.flags) == int(AMMWithdrawFlag.TF_LP_TOKEN)
        assert tx.lp_token_in.to_dict() == {
            "currency": _LP_CURRENCY,
            "issuer": _AMM_ACCOUNT,
            "value": "5",
        }
        assert "AMMInfo" in client.requests

    @pytest.mark.asyncio
    async def test_withdraw_lp_token_value_no_pool_fails_without_submit(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No pool → the LP token can never be resolved; fail tecAMM_NOT_FOUND
        (parity with the dry-run transport) BEFORE signing anything."""
        client = _FakeClient({"AMMInfo": {"error": "entryNotFound"}})
        submitted = _patch_network(monkeypatch, client)

        result = await transport.submit_amm_withdraw(
            _SEED, "XRP", "", "LAB", _ISSUER, lp_token_value="5",
        )

        assert result.success is False
        assert result.result_code == "tecAMM_NOT_FOUND"
        assert submitted == []


class TestGetAmmInfoTestnet:
    @pytest.mark.asyncio
    async def test_parses_pool_into_amm_info(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _FakeClient({"AMMInfo": _amm_info_result()})
        monkeypatch.setattr(xt, "_rpc_client", lambda url: client)

        info = await transport.get_amm_info("XRP", "", "LAB", _ISSUER)

        assert info is not None
        assert info.asset_a == "XRP"
        assert info.asset_b == f"LAB/{_ISSUER}"
        # Display convention matches the dry-run transport: whole units,
        # so the XRP leg is converted back out of drops.
        assert info.pool_a == "100"
        assert info.pool_b == "100"
        assert info.lp_token_currency == _LP_CURRENCY
        assert info.lp_token_issuer == _AMM_ACCOUNT
        assert info.lp_supply == "100"
        assert info.trading_fee == "500"
        assert info.asset_a_issuer == ""
        assert info.asset_b_issuer == _ISSUER

    @pytest.mark.asyncio
    async def test_entry_not_found_returns_none(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _FakeClient({"AMMInfo": {"error": "entryNotFound"}})
        monkeypatch.setattr(xt, "_rpc_client", lambda url: client)

        assert await transport.get_amm_info("XRP", "", "LAB", _ISSUER) is None

    @pytest.mark.asyncio
    async def test_rpc_failure_returns_none(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _FakeClient({}, fail_names=frozenset({"AMMInfo"}))
        monkeypatch.setattr(xt, "_rpc_client", lambda url: client)

        assert await transport.get_amm_info("XRP", "", "LAB", _ISSUER) is None


class TestGetLpTokenBalanceTestnet:
    @pytest.mark.asyncio
    async def test_reads_matching_trust_line(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _FakeClient({
            "AccountLines": {
                "lines": [
                    {"account": _ISSUER, "currency": "LAB", "balance": "990"},
                    {
                        "account": _AMM_ACCOUNT,
                        "currency": _LP_CURRENCY,
                        "balance": "110",
                    },
                ]
            }
        })
        monkeypatch.setattr(xt, "_rpc_client", lambda url: client)

        balance = await transport.get_lp_token_balance(
            _EXPECTED_ACCOUNT, _LP_CURRENCY, _AMM_ACCOUNT
        )

        assert balance == "110"

    @pytest.mark.asyncio
    async def test_no_matching_line_returns_zero(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _FakeClient({
            "AccountLines": {
                "lines": [{"account": _ISSUER, "currency": "LAB", "balance": "990"}]
            }
        })
        monkeypatch.setattr(xt, "_rpc_client", lambda url: client)

        balance = await transport.get_lp_token_balance(
            _EXPECTED_ACCOUNT, _LP_CURRENCY, _AMM_ACCOUNT
        )

        assert balance == "0"

    @pytest.mark.asyncio
    async def test_rpc_failure_returns_zero(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _FakeClient({}, fail_names=frozenset({"AccountLines"}))
        monkeypatch.setattr(xt, "_rpc_client", lambda url: client)

        assert (
            await transport.get_lp_token_balance(
                _EXPECTED_ACCOUNT, _LP_CURRENCY, _AMM_ACCOUNT
            )
            == "0"
        )


class TestDefaultRippleTestnet:
    """AccountSet asfDefaultRipple — the issuer-side prerequisite that keeps
    AMMCreate from failing with terNO_RIPPLE. Mirrors clawback's tests."""

    @pytest.mark.asyncio
    async def test_sets_asf_default_ripple_via_account_set(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        submitted = _patch_network(monkeypatch, _FakeClient({}))
        result = await transport.submit_default_ripple(_SEED, _EXPECTED_ACCOUNT)
        assert result.success is True
        assert result.result_code == "tesSUCCESS"
        (tx,) = submitted
        assert type(tx).__name__ == "AccountSet"
        assert tx.account == _EXPECTED_ACCOUNT  # derived from seed, not the aid arg
        assert tx.set_flag == AccountSetAsfFlag.ASF_DEFAULT_RIPPLE == 8

    @pytest.mark.asyncio
    async def test_validated_failure_maps_real_code(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _raise_tec(tx, client, wallet=None):
            raise XRPLReliableSubmissionException(
                "Transaction failed: tecINSUFFICIENT_RESERVE"
            )

        _patch_network(monkeypatch, _FakeClient({}))
        monkeypatch.setattr(xt, "submit_and_wait", _raise_tec)
        result = await transport.submit_default_ripple(_SEED)
        assert result.success is False
        assert result.result_code == "tecINSUFFICIENT_RESERVE"


class TestHasDefaultRippleTestnet:
    """``has_default_ripple`` reads lsfDefaultRipple (0x00800000) out of
    account_data.Flags; RPC failure degrades to False so the handler falls
    through to submitting (a redundant set is harmless on-ledger)."""

    @staticmethod
    def _account_info(flags: int) -> dict:
        return {"account_data": {"Account": _EXPECTED_ACCOUNT, "Flags": flags}}

    @pytest.mark.asyncio
    async def test_flag_set_returns_true(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _FakeClient({"AccountInfo": self._account_info(0x00800000)})
        _patch_network(monkeypatch, client)
        assert await transport.has_default_ripple(_EXPECTED_ACCOUNT) is True
        assert client.requests == ["AccountInfo"]

    @pytest.mark.asyncio
    async def test_flag_unset_returns_false(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # lsfDefaultRoot (0x00010000) set, lsfDefaultRipple not — the mask
        # must isolate exactly the ripple bit.
        client = _FakeClient({"AccountInfo": self._account_info(0x00010000)})
        _patch_network(monkeypatch, client)
        assert await transport.has_default_ripple(_EXPECTED_ACCOUNT) is False

    @pytest.mark.asyncio
    async def test_rpc_failure_returns_false(
        self, transport, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _FakeClient({}, fail_names=frozenset({"AccountInfo"}))
        _patch_network(monkeypatch, client)
        assert await transport.has_default_ripple(_EXPECTED_ACCOUNT) is False


class TestAmmMainnetRefusalSmoke:
    """test_network_safety.py owns the full refusal matrix; this is the
    AMM-local smoke check that the guard fires before any RPC happens."""

    @pytest.mark.asyncio
    async def test_amm_create_refused_on_mainnet_without_network(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XRPL_LAB_RPC_URL", "https://s1.ripple.com:51234")
        # Deliberately NOT patching _rpc_client: if the guard failed, this
        # would attempt a real socket and hang/raise instead of returning.
        with patch.object(xt, "submit_and_wait") as submit_spy:
            result = await XRPLTestnetTransport().submit_amm_create(
                "sEdSEEDDOESNOTMATTER", "XRP", "100", "", "LAB", "100", _ISSUER
            )
        assert result.success is False
        assert "Refusing" in result.error
        assert result.txid == ""
        submit_spy.assert_not_called()

    @pytest.mark.asyncio
    async def test_default_ripple_refused_on_mainnet_without_network(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XRPL_LAB_RPC_URL", "https://s1.ripple.com:51234")
        with patch.object(xt, "submit_and_wait") as submit_spy:
            result = await XRPLTestnetTransport().submit_default_ripple(
                "sEdSEEDDOESNOTMATTER", _ISSUER
            )
        assert result.success is False
        assert "Refusing" in result.error
        assert result.txid == ""
        submit_spy.assert_not_called()
