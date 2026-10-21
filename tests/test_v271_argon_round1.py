"""2.7.1: Argon's round-1 findings (PASS at 9aa461b; three non-blocking), plus
the verify route that Argon couldn't see.

- F1: the dashboard session still said ``live`` for a mode: dry-run module
  the runner forced offline.
- F2: ``record_tx`` stored an explorer URL on a record that never validated.
- F3: a dry-run tem or tef recorded ``validated: true``.
- The dashboard's verify route built an explorer link without ``validated``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xrpl_lab.state import LabState
from xrpl_lab.transport.base import SubmitResult

HASH = "C" * 64


@pytest.mark.parametrize(
    ("code", "validated"),
    [
        ("temCANNOT_PREAUTH_SELF", False),
        ("tefBAD_QUORUM", False),
        ("terPRE_SEQ", False),
        ("telINSUF_FEE_P", False),
        ("local_error", False),
        ("tecNO_PERMISSION", True),
    ],
)
def test_a_failure_that_cant_be_on_a_ledger_is_never_validated(code, validated) -> None:
    assert SubmitResult(success=False, result_code=code).validated is validated
    assert SubmitResult(success=True, result_code="tesSUCCESS").validated is True


@pytest.mark.asyncio
@pytest.mark.parametrize(("module_file", "code"), [
    ("deposit_gate_101.md", "temCANNOT_PREAUTH_SELF"),
    ("multisig_treasury_101.md", "tefBAD_QUORUM"),
])
async def test_a_dry_run_records_its_tem_and_tef_as_not_validated(
    module_file: str, code: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests._shipped_module import run_shipped_module
    from xrpl_lab.state import load_state

    await run_shipped_module(module_file, tmp_path, monkeypatch)
    failed = [r for r in load_state().tx_index if not r.success]
    assert failed and any(r.validated is False for r in failed), code


def test_record_tx_stores_no_link_for_a_tx_on_no_ledger() -> None:
    state = LabState()
    url = f"https://testnet.xrpl.org/transactions/{HASH}"
    state.record_tx(txid=HASH, module_id="m", network="testnet", success=False,
                    explorer_url=url, validated=False)
    state.record_tx(txid="failed", module_id="m", network="testnet", success=False,
                    explorer_url="https://testnet.xrpl.org/transactions/failed")
    state.record_tx(txid=HASH, module_id="m", network="testnet", success=False,
                    explorer_url=url, validated=True)
    assert [r.explorer_url for r in state.tx_index] == ["", "", url]


def test_the_verify_route_links_only_what_is_on_a_ledger() -> None:
    from xrpl_lab.api.routes import _verify_explorer_url

    base = {"txid": HASH, "network": "testnet"}
    assert _verify_explorer_url({**base, "validated": True}).endswith(HASH)
    assert _verify_explorer_url({**base}).endswith(HASH)  # older packs: unknown
    assert _verify_explorer_url({**base, "validated": False}) == ""


@pytest.mark.asyncio
async def test_the_dashboard_session_follows_the_offline_swap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xrpl_lab.api.runner_ws as runner_ws
    from xrpl_lab.modules import ModuleDef

    mod = ModuleDef(id="m271", title="m271", time="1 min", level="beginner", requires=[],
                    produces=[], checks=[], raw_body="", steps=[], dry_run_only=True,
                    mode="dry-run")
    monkeypatch.setattr(runner_ws, "load_all_modules", lambda: {"m271": mod})
    seen = {}

    async def _fake_run(module, transport, **kwargs):
        seen["dry_run_at_start"] = session.dry_run
        return True

    monkeypatch.setattr(runner_ws, "run_module", _fake_run)
    session = runner_ws.ModuleRunSession(run_id="r1", module_id="m271", dry_run=False)
    await runner_ws._run_module_task(session)
    assert seen.get("dry_run_at_start") is True
    assert session.dry_run is True
