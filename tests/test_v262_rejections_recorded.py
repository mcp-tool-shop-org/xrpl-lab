"""2.6.2 (#20 item 8): a deliberate rejection is recorded and acknowledged.

Book Keeper's 2.6.1 release sweep: six lessons validated their expected tec on
the ledger but left it out of ``tx_index``, so the report's "Transactions ...
failed (M expected)" line and the proof pack left the tec out, and a receipt
couldn't show by itself that the rejection was the expected one. Every judged
expected-failure handler now records its rejection, and the judge acknowledges
that record by txid.
"""

from __future__ import annotations

import ast
import inspect
import re
import textwrap
from pathlib import Path

import pytest

import xrpl_lab.handlers as handlers
from tests._shipped_module import run_shipped_module


def _judged_handlers() -> list[str]:
    return sorted(
        name for name, fn in inspect.getmembers(handlers, inspect.iscoroutinefunction)
        if "_judge_expected_failure(" in inspect.getsource(fn)
    )


def _records_on_the_failure_path(name: str) -> bool:
    """A record call that runs when the submit failed: unconditional, or on
    the failure side of an ``if <result>.success`` test."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(getattr(handlers, name))))

    def records(nodes) -> bool:
        for node in nodes:
            for call in ast.walk(node):
                if not isinstance(call, ast.Call):
                    continue
                fname = getattr(call.func, "attr", "") or getattr(call.func, "id", "")
                if fname == "_record_submit":
                    return True
                if fname == "record_tx" and any(
                    k.arg == "success" and isinstance(k.value, ast.Constant)
                    and k.value.value is False for k in call.keywords
                ):
                    return True
        return False

    guarded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and ast.unparse(node.test).endswith(".success"):
            for sub in ast.walk(node):
                guarded.add(id(sub))
            negated = ast.unparse(node.test).startswith("not ")
            if records(node.body if negated else node.orelse):
                return True
    unguarded = [n for n in ast.walk(tree) if id(n) not in guarded]
    return any(
        isinstance(n, ast.Call)
        and (getattr(n.func, "attr", "") or getattr(n.func, "id", "")) == "_record_submit"
        for n in unguarded
    )


def test_there_are_judged_handlers() -> None:
    assert len(_judged_handlers()) >= 19


@pytest.mark.parametrize("name", _judged_handlers())
def test_every_judged_handler_records_its_rejection(name: str) -> None:
    assert _records_on_the_failure_path(name), (
        f"{name} judges an expected failure but doesn't record the rejection, "
        "so the report and the proof pack leave it out"
    )


# The lessons Book Keeper's sweep named, plus every other lesson that teaches
# a rejection. Each must finish verified, with its rejections recorded and all
# of them acknowledged as expected.
_REJECTION_LESSONS = [
    "failure_literacy.md", "token_escrow_101.md", "deposit_gate_101.md",
    "custodial_crediting_101.md", "checks_101.md", "nft_marketplace_101.md",
    "dnft_evolving_item_101.md", "multisig_treasury_101.md", "clawback_101.md",
    "credentials_101.md", "permissioned_domains_101.md", "trust_line_failures.md",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("module_file", _REJECTION_LESSONS)
async def test_a_rejection_lesson_reports_its_rejections_as_expected(
    module_file: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    await run_shipped_module(module_file, tmp_path, monkeypatch)
    reports = sorted((tmp_path / "ws" / "reports").glob("*.md"))
    assert reports, "no report written"
    text = reports[-1].read_text(encoding="utf-8")
    assert re.search(r"Steps: \d+ passed, 0 failed", text), text[:400]
    m = re.search(r"Transactions: \d+ successful, (\d+) failed(?: \((\d+) expected\))?", text)
    assert m, text[:400]
    failed, expected = int(m.group(1)), int(m.group(2) or 0)
    assert failed >= 1, f"{module_file}: its rejection isn't in the record"
    assert expected == failed, f"{module_file}: {failed} failed, {expected} expected"


@pytest.mark.asyncio
@pytest.mark.parametrize("module_file", ["failure_literacy.md", "deposit_gate_101.md"])
async def test_the_receipt_marks_the_rejection_expected(
    module_file: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from xrpl_lab.reporting import generate_proof_pack
    from xrpl_lab.state import load_state

    await run_shipped_module(module_file, tmp_path, monkeypatch)
    state = load_state()
    failed = [r for r in state.tx_index if not r.success]
    assert failed and all(r.expected for r in failed)
    assert not any(r.expected for r in state.tx_index if r.success)

    pack = generate_proof_pack(state)
    assert pack["expected_failures"] == pack["failed_transactions"] == len(failed)
    assert all(t["expected"] for t in pack["transactions"] if not t["success"])
    assert all(row["expected"] for row in pack["receipt_table"] if row["status"] == "FAIL")


def test_doctor_and_feedback_skip_an_expected_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xrpl_lab.doctor as doctor
    import xrpl_lab.feedback as feedback
    from xrpl_lab.state import LabState, TxRecord

    state = LabState()
    state.tx_index.append(TxRecord(
        txid="T1", module_id="failure_literacy", timestamp=1.0,
        network="testnet", success=False, expected=True,
    ))
    monkeypatch.setattr(doctor, "load_state", lambda: state)
    monkeypatch.setattr(feedback, "load_state", lambda: state)

    async def _no_checks():
        return doctor.DoctorReport()

    monkeypatch.setattr(feedback, "run_doctor", _no_checks)

    assert doctor._check_last_error().detail == "No failed transactions"
    text = feedback.generate_feedback()
    assert "### Last Error" not in text
    assert "1 (0 ok, 1 failed (1 expected))" in text

    # A real failure still shows.
    state.tx_index.append(TxRecord(
        txid="T2", module_id="m", timestamp=2.0, network="testnet", success=False,
    ))
    assert doctor._check_last_error().detail.startswith("Last failure in 'm'")
    assert "- TXID: `T2`" in feedback.generate_feedback()


def test_support_bundle_and_last_module_check_mark_expected_rejections(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Argon, 2.6.2 round 1, F1 (and the same gap in doctor's last-module check)."""
    import xrpl_lab.doctor as doctor
    import xrpl_lab.workshop as workshop
    from xrpl_lab.state import LabState, TxRecord

    state = LabState()
    state.tx_index.append(TxRecord(
        txid="AAAAAAAAAAAAAAAAAAAAAAAAAAAA", module_id="deposit_gate_101", timestamp=1.0,
        network="testnet", success=False, expected=True,
    ))
    monkeypatch.setattr(doctor, "load_state", lambda: state)
    monkeypatch.setattr(doctor, "state_path", lambda: tmp_path)
    detail = doctor._check_last_module_state().detail
    assert "in-flight: deposit_gate_101" in detail and "last failed tx" not in detail

    async def _no_checks():
        return doctor.DoctorReport()

    monkeypatch.setattr(doctor, "run_doctor", _no_checks)  # imported inside the function
    md = workshop.generate_support_bundle(state).to_markdown()
    assert "[FAIL (expected)] AAAAAAAAAAAAAAAAAAAAAAAA..." in md
    assert "[FAIL] " not in md
