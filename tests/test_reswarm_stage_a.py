"""Regression tests pinning the 2026-06-22 re-swarm Stage-A fixes.

Each test anchors one finding so the fix cannot silently regress:

- A-BACKEND-001: doctor checks must not leak filesystem paths (OS username /
  home layout) into Check.detail, which flows to the issue-shareable feedback
  bundle.
- A-ACTIONS-001: verify_escrow_finished must NOT report an escrow "gone" when a
  still-present escrow has an unresolved (0) create-sequence.
- A-TRANSPORT-001 / A-ACTIONS-002: dry-run must reject the same inputs testnet
  rejects (>6dp XRP amounts; issued payments over the trust-line limit), so a
  dry-run "pass" never masks a real-network failure.
"""

from pathlib import Path

import pytest

from xrpl_lab.actions.escrow import verify_escrow_finished
from xrpl_lab.doctor import _check_state, _check_workspace, _redact_path
from xrpl_lab.transport.base import EscrowInfo
from xrpl_lab.transport.dry_run import DryRunTransport, _address_from_seed

# ── A-BACKEND-001: doctor path redaction ──────────────────────────────────


def test_redact_path_home_relativizes():
    out = _redact_path(Path.home() / ".xrpl-lab" / "state.json")
    assert out.startswith("~/")
    assert str(Path.home()) not in out
    # The username (last component of the home dir) must not survive.
    assert Path.home().name not in out


def test_check_state_oserror_does_not_leak_path(tmp_path, monkeypatch):
    # Point state_path at a directory: read_text() raises an OSError subclass
    # (IsADirectoryError on POSIX, PermissionError on Windows) whose str()
    # embeds the absolute path. The Check.detail must surface only the type.
    d = tmp_path / "state.json"
    d.mkdir()
    monkeypatch.setattr("xrpl_lab.doctor.state_path", lambda: d)

    check = _check_state()

    assert not check.passed
    assert str(d) not in check.detail
    assert check.detail.startswith("Unreadable (")


def test_check_workspace_detail_has_no_home_path(tmp_path, monkeypatch):
    monkeypatch.setattr("xrpl_lab.doctor.get_workspace_dir", lambda: tmp_path / "ws")

    check = _check_workspace()

    assert check.passed
    # The real leak guard: never expose the absolute home prefix, and never
    # emit the absolute resolved path (the buggy code did `ws.resolve()`).
    # _redact_path returns a ~/, ./, or bare-basename form depending on where
    # the workspace sits relative to home/cwd — all leak-free. We don't assert a
    # specific prefix because on a CI runner the tmp dir is under neither home
    # nor cwd, so the basename form is correct and expected (Windows tmp is
    # under home, so it renders ~/… there — the cross-platform divergence that
    # the absolute-path assertion below tolerates).
    assert str(Path.home()) not in check.detail
    assert str((tmp_path / "ws").resolve()) not in check.detail


# ── A-ACTIONS-001: escrow false-"gone" guard ──────────────────────────────


class _StubEscrowTransport:
    def __init__(self, escrows: list[EscrowInfo]):
        self._escrows = escrows

    async def get_escrows(self, address: str) -> list[EscrowInfo]:
        return self._escrows


@pytest.mark.asyncio
async def test_verify_escrow_finished_indeterminate_when_sequence_unresolved():
    # A still-present escrow whose create-sequence could not be resolved (the
    # testnet PreviousTxnID->account_tx join missed -> 0). The verifier must NOT
    # claim the escrow is gone / funds released.
    transport = _StubEscrowTransport([EscrowInfo(sequence=0, destination="rDEST")])

    res = await verify_escrow_finished(transport, "rADDR", offer_sequence=42)

    assert res.gone is False
    assert res.passed is False
    assert any("unresolved" in f.lower() for f in res.failures)


@pytest.mark.asyncio
async def test_verify_escrow_finished_gone_when_no_escrows():
    # Positive control: a genuinely empty escrow set is correctly "gone".
    transport = _StubEscrowTransport([])

    res = await verify_escrow_finished(transport, "rADDR", offer_sequence=42)

    assert res.gone is True


# ── A-TRANSPORT-001 / A-ACTIONS-002: dry-run <-> testnet parity ────────────


@pytest.mark.asyncio
async def test_dry_run_rejects_subdrop_xrp_amount():
    t = DryRunTransport()
    r = await t.submit_payment("sFAKE", "rDEST", "1.5555555")  # 7 decimal places
    assert r.success is False
    assert r.result_code == "temBAD_AMOUNT"


@pytest.mark.asyncio
async def test_dry_run_accepts_six_dp_xrp_amount():
    # Fresh transport per amount so a prior debit doesn't drive the unfunded
    # sender negative (that's the balance guard, not the precision guard).
    # Exactly 6 dp, and a trailing-zero 8dp that normalizes to <=6, are valid.
    assert (await DryRunTransport().submit_payment("sFAKE", "rDEST", "1.500000")).success is True
    assert (await DryRunTransport().submit_payment("sFAKE", "rDEST", "2.50000000")).success is True


@pytest.mark.asyncio
async def test_dry_run_issued_payment_respects_trust_limit():
    t = DryRunTransport()
    holder_seed, issuer_seed = "sHOLDER", "sISSUER"
    issuer_addr = _address_from_seed(issuer_seed)
    holder_addr = _address_from_seed(holder_seed)
    await t.submit_trust_set(holder_seed, issuer_addr, "LAB", "100")

    over = await t.submit_issued_payment(issuer_seed, holder_addr, "LAB", issuer_addr, "150")
    assert over.success is False
    assert over.result_code == "tecPATH_DRY"

    # An at-limit payment still succeeds (also confirms the trust line resolved,
    # so the rejection above is for the limit, not a missing line).
    at_limit = await t.submit_issued_payment(issuer_seed, holder_addr, "LAB", issuer_addr, "100")
    assert at_limit.success is True
