"""2.7.1 (#20 item 12): a record says whether its transaction is on a ledger.

Book Keeper's 2.6.2 live sweep: an expected record didn't say whether the
rejection validated (the 17 tecs) or never reached a ledger (deposit_gate's
tem, multisig's tef). The tem's record linked to an explorer page for a tx on
no ledger, and the tef kept no hash, so its record read "failed" with a dead
``/transactions/failed`` link.
"""

from __future__ import annotations

import pytest
from xrpl.models.transactions import Payment
from xrpl.transaction import multisign, sign
from xrpl.wallet import Wallet

from xrpl_lab.handlers import _record_submit
from xrpl_lab.reporting import generate_proof_pack
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import SubmitResult
from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

TEC_HASH = "A" * 64
TEM_HASH = "B" * 64


def test_record_tx_defaults() -> None:
    state = LabState()
    state.record_tx(txid=TEC_HASH, module_id="m", network="testnet", success=True)
    state.record_tx(txid="failed", module_id="m", network="testnet", success=False)
    assert [r.validated for r in state.tx_index] == [True, None]


def test_record_submit_carries_the_results_validated_flag(monkeypatch) -> None:
    import xrpl_lab.handlers as handlers

    monkeypatch.setattr(handlers, "save_state", lambda state: None)
    state = LabState(network="testnet")
    ctx = {"module_id": "m"}
    _record_submit(state, ctx, SubmitResult(success=False, txid=TEC_HASH,
                                            result_code="tecNO_PERMISSION", validated=True))
    _record_submit(state, ctx, SubmitResult(success=False, txid=TEM_HASH,
                                            result_code="temCANNOT_PREAUTH_SELF",
                                            validated=False))
    assert [r.validated for r in state.tx_index] == [True, False]


def test_the_proof_pack_links_only_what_is_on_a_ledger() -> None:
    state = LabState(network="testnet")
    state.record_tx(txid=TEC_HASH, module_id="m", network="testnet", success=False,
                    validated=True)
    state.record_tx(txid=TEM_HASH, module_id="m", network="testnet", success=False,
                    validated=False)
    state.record_tx(txid="failed", module_id="m", network="testnet", success=False)
    txs = generate_proof_pack(state)["transactions"]
    assert txs[0]["explorer_url"].endswith(TEC_HASH) and txs[0]["validated"] is True
    assert txs[1]["explorer_url"] == "" and txs[1]["validated"] is False
    assert txs[2]["explorer_url"] == ""  # no /transactions/failed link
    rows = generate_proof_pack(state)["receipt_table"]
    assert [r["validated"] for r in rows] == [True, False, None]


@pytest.mark.asyncio
async def test_a_multisigned_tx_keeps_its_hash() -> None:
    """_presign tried to re-sign a fully multisigned tx with no wallet and gave
    up, so a tefBAD_QUORUM was recorded with no hash."""
    account = Wallet.create()
    signers = [Wallet.create(), Wallet.create()]
    tx = Payment(account=account.address, destination=signers[0].address, amount="1",
                 sequence=1, fee="36", last_ledger_sequence=100, signing_pub_key="")
    combined = multisign(tx, [sign(tx, w, multisign=True) for w in signers])
    signed = await XRPLTestnetTransport()._presign(combined, None, "Payment(multisig)")
    assert signed is combined
    assert len(signed.get_hash()) == 64
