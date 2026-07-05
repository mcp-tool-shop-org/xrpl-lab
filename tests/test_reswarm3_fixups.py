"""Regression tests for the Stage-A adversarial-verify FIX-UPS (re-swarm v3).

The 3-lens verify pass found family-of-call-sites residuals the amend wave
missed. Each test pins one fix-up so the sibling gap cannot silently reopen:

- Offer-family XRP-leg validation (submit_offer_create / submit_nft_create_offer
  were the unmigrated siblings of the payment/escrow/channel _validate_xrp_amount
  wiring).
- `verify --tx` exit code (the sibling of the `audit` exit-0-on-failure bug).
- The SIMULATED signal on proof-pack / certificate verify surfaces (CL-001 landed
  it on the audit pack but not on these shareable-credential siblings).
- cohort-status TABLE path-leak (CL-005 fixed the json branch but not the table).
"""

import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from xrpl_lab.actions.verify import VerifyResult
from xrpl_lab.server import create_app
from xrpl_lab.transport.base import TxInfo
from xrpl_lab.transport.dry_run import DryRunTransport

# ── Offer-family XRP-leg validation ────────────────────────────────────────


@pytest.mark.asyncio
async def test_offer_create_rejects_negative_xrp_leg():
    r = await DryRunTransport().submit_offer_create(
        "sMAKER", "XRP", "-5", "", "LAB", "10", "rISSUER"
    )
    assert r.success is False
    assert r.result_code == "temBAD_AMOUNT"


@pytest.mark.asyncio
async def test_offer_create_rejects_over_max_xrp_leg():
    r = await DryRunTransport().submit_offer_create(
        "sMAKER", "LAB", "10", "rISSUER", "XRP", "200000000000", ""
    )
    assert r.success is False
    assert r.result_code == "temBAD_AMOUNT"


@pytest.mark.asyncio
async def test_offer_create_accepts_valid_xrp_leg():
    r = await DryRunTransport().submit_offer_create(
        "sMAKER", "XRP", "10", "", "LAB", "50", "rISSUER"
    )
    assert r.success is True


@pytest.mark.asyncio
async def test_nft_create_offer_rejects_negative_xrp_price():
    # sell=False (buy offer) so the negative-amount guard fires before any
    # NFT-ownership check.
    r = await DryRunTransport().submit_nft_create_offer(
        "sBUYER", "NFT123", "-5", sell=False, currency="XRP"
    )
    assert r.success is False
    assert r.result_code == "temBAD_AMOUNT"


# ── verify --tx exit code ──────────────────────────────────────────────────


def _fake_verify(passed: bool):
    result = VerifyResult(
        passed=passed,
        tx_info=TxInfo(txid="ABC", tx_type="Payment", account="rA", amount="1"),
        checks=["Result: tesSUCCESS"] if passed else [],
        failures=[] if passed else ["Expected tesSUCCESS, got tecFAILED"],
    )

    async def _fn(transport, txid):
        return result

    return _fn


def test_verify_tx_exits_nonzero_on_failed_verdict(monkeypatch):
    from xrpl_lab import cli

    monkeypatch.setattr(cli, "verify_tx", _fake_verify(False))
    res = CliRunner().invoke(cli.main, ["verify", "--tx", "ABC", "--dry-run"])
    assert res.exit_code == 1


def test_verify_tx_exits_zero_on_passed_verdict(monkeypatch):
    from xrpl_lab import cli

    monkeypatch.setattr(cli, "verify_tx", _fake_verify(True))
    res = CliRunner().invoke(cli.main, ["verify", "--tx", "ABC", "--dry-run"])
    assert res.exit_code == 0


# ── SIMULATED signal on proof/cert verify surfaces ─────────────────────────


def _write_pack(tmp_path, network, marker="xrpl_lab_proof_pack", all_verified=True):
    pack = {
        marker: True, "version": "2.2.0", "network": network, "address": "rTEST",
        "completed_modules": [], "total_transactions": 0, "sha256": "deadbeef",
        "all_verified": all_verified,
    }
    p = tmp_path / "pack.json"
    p.write_text(json.dumps(pack), encoding="utf-8")
    return p


def test_proof_verify_json_flags_simulated_for_dry_run(tmp_path):
    from xrpl_lab import cli

    p = _write_pack(tmp_path, "dry-run")
    res = CliRunner().invoke(cli.main, ["proof", "verify", str(p), "--json"])
    assert json.loads(res.output)["simulated"] is True


def test_proof_verify_json_not_simulated_for_testnet(tmp_path):
    from xrpl_lab import cli

    p = _write_pack(tmp_path, "testnet")
    res = CliRunner().invoke(cli.main, ["proof", "verify", str(p), "--json"])
    assert json.loads(res.output)["simulated"] is False


def test_proof_verify_banner_shows_simulated_for_dry_run(tmp_path):
    from xrpl_lab import cli

    p = _write_pack(tmp_path, "dry-run")
    res = CliRunner().invoke(cli.main, ["proof", "verify", str(p)])
    assert "SIMULATED" in res.output


def test_proof_verify_banner_absent_for_testnet(tmp_path):
    from xrpl_lab import cli

    p = _write_pack(tmp_path, "testnet")
    res = CliRunner().invoke(cli.main, ["proof", "verify", str(p)])
    assert "SIMULATED" not in res.output


# ── UNVERIFIED signal (honest-pack: a module failed on-ledger verification) ──


def test_proof_verify_json_flags_unverified(tmp_path):
    from xrpl_lab import cli

    p = _write_pack(tmp_path, "testnet", all_verified=False)
    res = CliRunner().invoke(cli.main, ["proof", "verify", str(p), "--json"])
    assert json.loads(res.output)["all_verified"] is False


def test_proof_verify_banner_shows_unverified(tmp_path):
    from xrpl_lab import cli

    p = _write_pack(tmp_path, "testnet", all_verified=False)
    res = CliRunner().invoke(cli.main, ["proof", "verify", str(p)])
    assert "UNVERIFIED" in res.output


def test_proof_verify_no_unverified_banner_when_all_verified(tmp_path):
    from xrpl_lab import cli

    p = _write_pack(tmp_path, "testnet", all_verified=True)
    res = CliRunner().invoke(cli.main, ["proof", "verify", str(p)])
    assert "UNVERIFIED" not in res.output


def test_api_verify_flags_unverified_pack():
    pack = {
        "xrpl_lab_proof_pack": True, "version": "2.2.0", "network": "testnet",
        "address": "rTEST", "completed_modules": [], "total_transactions": 0,
        "sha256": "deadbeef", "all_verified": False,
    }
    with TestClient(create_app()) as client:
        resp = client.post("/api/verify", json=pack)
    assert resp.status_code == 200
    assert resp.json()["all_verified"] is False


# ── cohort-status TABLE path-leak ──────────────────────────────────────────


def test_cohort_status_table_does_not_leak_absolute_path(tmp_path):
    from xrpl_lab import cli

    # Absolute --dir with no learner subdirs -> the empty-state message must show
    # only the basename, never the absolute path carrying the OS username/home.
    cohort = tmp_path / "fall2026"
    cohort.mkdir()
    res = CliRunner().invoke(cli.main, ["cohort-status", "--dir", str(cohort)])
    assert res.exit_code == 0
    assert str(cohort) not in res.output
    assert "fall2026" in res.output


# ── /api/verify SIMULATED field (the browser-reachable surface of F1) ──────


def test_api_verify_flags_simulated_for_dry_run_pack():
    pack = {
        "xrpl_lab_proof_pack": True, "version": "2.2.0", "network": "dry-run",
        "address": "rTEST", "completed_modules": [], "total_transactions": 0,
        "sha256": "deadbeef",
    }
    with TestClient(create_app()) as client:
        resp = client.post("/api/verify", json=pack)
    assert resp.status_code == 200
    assert resp.json()["simulated"] is True


def test_api_verify_not_simulated_for_testnet_pack():
    pack = {
        "xrpl_lab_proof_pack": True, "version": "2.2.0", "network": "testnet",
        "address": "rTEST", "completed_modules": [], "total_transactions": 0,
        "sha256": "deadbeef",
    }
    with TestClient(create_app()) as client:
        resp = client.post("/api/verify", json=pack)
    assert resp.status_code == 200
    assert resp.json()["simulated"] is False
