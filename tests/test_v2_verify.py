"""v2.0.0 ledger-anchored verification tests (f1-verify domain).

The SIGNATURE v2 feature: ``proof verify --live`` / ``cert-verify --live`` must
re-fetch every claimed txid from the public XRPL and confirm it exists, is
validated, and succeeded — so a hand-crafted pack with FAKE txids (but a
correct self-hash) is caught, even though it passes the offline integrity
check.

Everything here runs FULLY OFFLINE. The live verify logic takes an injected
transport, so we drive it with:
  * ``DryRunTransport`` + ``set_tx_fixtures`` for the resolves/validated cases, and
  * tiny stub transports for the network-failure (fetch_error) case.

No real network, no ``xrpl`` client calls.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from click.testing import CliRunner

from xrpl_lab.cli import main
from xrpl_lab.reporting import (
    LIVE_FAIL,
    LIVE_PASS,
    LIVE_SKIPPED,
    verify_certificate_live,
    verify_proof_pack_live,
)
from xrpl_lab.transport.base import TxInfo
from xrpl_lab.transport.dry_run import DryRunTransport

# A real-ish learner wallet address used as the pack's top-level address and
# the on-ledger account for "good" fixtures.
LEARNER_ADDR = "rLearnerWalletAAAAAAAAAAAAAAAAA"
# A 64-hex-ish txid shape (the value doesn't have to be a real hash for the
# fixture path — the dry-run transport keys fixtures by exact string).
TXID_GOOD = "A" * 64
TXID_GOOD_2 = "B" * 64
TXID_FAKE = "F" * 64


def _seal(pack: dict) -> dict:
    """Compute and embed the canonical SHA-256 self-hash (matches reporting)."""
    check = {k: v for k, v in pack.items() if k != "sha256"}
    content = json.dumps(check, sort_keys=True, separators=(",", ":"))
    pack["sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return pack


def _proof_pack(transactions, *, address=LEARNER_ADDR, network="testnet", marker=True):
    """Build a sealed proof pack with the given per-tx transactions list."""
    pack = {
        "xrpl_lab_proof_pack": marker,
        "version": "2.0.0",
        "network": network,
        "address": address,
        "completed_modules": [],
        "transactions": transactions,
        "total_transactions": len(transactions),
    }
    return _seal(pack)


def _good_txinfo(txid, *, account=LEARNER_ADDR, tx_type="Payment"):
    return TxInfo(
        txid=txid,
        tx_type=tx_type,
        account=account,
        destination="rDestinationXXXXXXXXXXXXXXXXXX",
        amount="10000000",
        fee="12",
        result_code="tesSUCCESS",
        ledger_index=42_000_000,
        memos=["XRPLLAB|testnet"],
        validated=True,
    )


class _FetchErrorTransport:
    """Stub transport whose fetch_tx always reports a network read-back error.

    Mirrors the testnet transport's behavior when the ledger is unreachable:
    it sets ``fetch_error`` (NOT result_code), which must be treated as
    "couldn't reach the ledger", NOT proof the tx is fake.
    """

    network_name = "testnet"

    async def fetch_tx(self, txid: str) -> TxInfo:
        return TxInfo(txid=txid, fetch_error="Timed out fetching transaction. Try again.")


class _NotFoundTransport:
    """Stub transport whose fetch_tx returns an empty/not-found TxInfo."""

    network_name = "testnet"

    async def fetch_tx(self, txid: str) -> TxInfo:
        # Empty result_code + not validated == "no such tx on the ledger".
        return TxInfo(txid=txid)


# ── (a) all txids resolve validated + tesSUCCESS → PASS ───────────────────


class TestLivePass:
    @pytest.mark.asyncio
    async def test_all_txids_validated_and_success_pass(self):
        pack = _proof_pack([
            {"txid": TXID_GOOD, "network": "testnet"},
            {"txid": TXID_GOOD_2, "network": "testnet"},
        ])
        transport = DryRunTransport()
        transport.set_tx_fixtures({
            TXID_GOOD: _good_txinfo(TXID_GOOD),
            TXID_GOOD_2: _good_txinfo(TXID_GOOD_2),
        })

        live = await verify_proof_pack_live(pack, transport=transport)

        assert live.overall_passed is True
        assert live.passed_count == 2
        assert live.failed_count == 0
        assert all(r.status == LIVE_PASS for r in live.real_tx_results)

    @pytest.mark.asyncio
    async def test_account_and_type_match_recorded_claims(self):
        """When the pack records tx_type, it must MATCH on-ledger."""
        pack = _proof_pack([
            {"txid": TXID_GOOD, "network": "testnet", "tx_type": "Payment"},
        ])
        transport = DryRunTransport()
        transport.set_tx_fixtures({
            TXID_GOOD: _good_txinfo(TXID_GOOD, tx_type="Payment"),
        })

        live = await verify_proof_pack_live(pack, transport=transport)
        assert live.overall_passed is True
        # The account-match + type-match checks are recorded.
        checks = live.tx_results[0].checks
        assert any("Account matches" in c for c in checks)
        assert any("Type matches" in c for c in checks)


# ── (b) not-found / not-validated / wrong result-code → FAIL with reason ───


class TestLiveFailReasons:
    @pytest.mark.asyncio
    async def test_not_validated_fails(self):
        pack = _proof_pack([{"txid": TXID_GOOD, "network": "testnet"}])
        tx = _good_txinfo(TXID_GOOD)
        tx.validated = False  # in mempool, not in a closed ledger
        transport = DryRunTransport()
        transport.set_tx_fixtures({TXID_GOOD: tx})

        live = await verify_proof_pack_live(pack, transport=transport)
        assert live.overall_passed is False
        assert live.tx_results[0].status == LIVE_FAIL
        assert "not validated" in live.tx_results[0].reason.lower()

    @pytest.mark.asyncio
    async def test_wrong_result_code_fails(self):
        pack = _proof_pack([{"txid": TXID_GOOD, "network": "testnet"}])
        tx = _good_txinfo(TXID_GOOD)
        tx.result_code = "tecUNFUNDED_PAYMENT"  # failed on-ledger
        transport = DryRunTransport()
        transport.set_tx_fixtures({TXID_GOOD: tx})

        live = await verify_proof_pack_live(pack, transport=transport)
        assert live.overall_passed is False
        assert live.tx_results[0].status == LIVE_FAIL
        assert "tesSUCCESS" in live.tx_results[0].reason

    @pytest.mark.asyncio
    async def test_account_mismatch_fails(self):
        """A borrowed/forged receipt sent FROM a different account fails."""
        pack = _proof_pack([{"txid": TXID_GOOD, "network": "testnet"}])
        tx = _good_txinfo(TXID_GOOD, account="rSomeoneElseAddrXXXXXXXXXXXXXX")
        transport = DryRunTransport()
        transport.set_tx_fixtures({TXID_GOOD: tx})

        live = await verify_proof_pack_live(pack, transport=transport)
        assert live.overall_passed is False
        assert live.tx_results[0].status == LIVE_FAIL
        assert "account" in live.tx_results[0].reason.lower()

    @pytest.mark.asyncio
    async def test_type_mismatch_fails(self):
        pack = _proof_pack([
            {"txid": TXID_GOOD, "network": "testnet", "tx_type": "NFTokenMint"},
        ])
        tx = _good_txinfo(TXID_GOOD, tx_type="Payment")  # ledger disagrees
        transport = DryRunTransport()
        transport.set_tx_fixtures({TXID_GOOD: tx})

        live = await verify_proof_pack_live(pack, transport=transport)
        assert live.overall_passed is False
        assert live.tx_results[0].status == LIVE_FAIL
        assert "type" in live.tx_results[0].reason.lower()


# ── (c) HEADLINE: fake txid passes the hash but FAILS on-ledger ───────────


class TestHeadlineFakeTxid:
    @pytest.mark.asyncio
    async def test_fake_txid_passes_hash_but_fails_ledger(self):
        """The signature finding made literally true.

        A pack with a FAKE txid that the learner hand-crafted has a perfectly
        valid self-hash (the offline check passes) — but the public ledger has
        no such transaction, so --live catches it.
        """
        from xrpl_lab.reporting import verify_proof_pack

        pack = _proof_pack([{"txid": TXID_FAKE, "network": "testnet"}])

        # The offline tamper-evidence layer is satisfied: the hand-crafted
        # pack was sealed correctly, so verify_proof_pack PASSES it.
        hash_ok, _ = verify_proof_pack(pack)
        assert hash_ok is True, "hash layer must pass — this is the whole trap"

        # But the fake txid is absent on-ledger (transport returns not-found).
        live = await verify_proof_pack_live(pack, transport=_NotFoundTransport())

        assert live.overall_passed is False
        assert live.tx_results[0].status == LIVE_FAIL
        assert "not found" in live.tx_results[0].reason.lower()

    def test_fake_txid_cli_live_exits_nonzero(self, tmp_path, monkeypatch):
        """End-to-end CLI: a sealed pack with a fake txid fails `--live`.

        Patches the default transport factory so the CLI never touches the
        network — the fake txid resolves to a not-found stub.
        """
        import xrpl_lab.reporting as reporting

        pack = _proof_pack([{"txid": TXID_FAKE, "network": "testnet"}])
        path = tmp_path / "proof.json"
        path.write_text(json.dumps(pack), encoding="utf-8")

        monkeypatch.setattr(
            reporting, "_default_transport_factory",
            lambda network: _NotFoundTransport(),
        )

        runner = CliRunner()
        result = runner.invoke(main, ["proof", "verify", str(path), "--live"])
        assert result.exit_code == 1
        # Offline integrity still passes; on-ledger verdict fails.
        assert "PASS" in result.output  # the SHA-256 integrity line
        assert "FAIL" in result.output  # the on-ledger verdict
        assert "not found" in result.output.lower()


# ── (d) dry-run pack → honest "no on-ledger txids", not a false failure ────


class TestDryRunHonesty:
    @pytest.mark.asyncio
    async def test_dry_run_pack_reports_no_onledger_txids(self):
        pack = _proof_pack(
            [{"txid": "DRYRUNxxxx", "network": "dry-run"}],
            network="dry-run",
        )
        # transport should never even be consulted for a dry-run-only pack;
        # pass one that would explode if a fetch happened.
        live = await verify_proof_pack_live(pack, transport=_NotFoundTransport())

        assert live.overall_passed is True, "dry-run is honest, not a failure"
        assert live.no_onledger_txids is True
        assert live.failed_count == 0
        assert live.tx_results[0].status == LIVE_SKIPPED

    @pytest.mark.asyncio
    async def test_mixed_pack_verifies_only_real_network_txids(self):
        """A pack spanning testnet + dry-run verifies only the testnet tx."""
        pack = _proof_pack([
            {"txid": TXID_GOOD, "network": "testnet"},
            {"txid": "DRYRUNyyyy", "network": "dry-run"},
        ], network="mixed")
        transport = DryRunTransport()
        transport.set_tx_fixtures({TXID_GOOD: _good_txinfo(TXID_GOOD)})

        live = await verify_proof_pack_live(pack, transport=transport)
        assert live.overall_passed is True
        assert live.passed_count == 1
        assert live.skipped_count == 1
        # The dry-run leg is skipped, the testnet leg passed.
        statuses = {r.network: r.status for r in live.tx_results}
        assert statuses["testnet"] == LIVE_PASS
        assert statuses["dry-run"] == LIVE_SKIPPED

    def test_dry_run_pack_cli_live_is_pass(self, tmp_path):
        pack = _proof_pack(
            [{"txid": "DRYRUNzzzz", "network": "dry-run"}],
            network="dry-run",
        )
        path = tmp_path / "proof.json"
        path.write_text(json.dumps(pack), encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(main, ["proof", "verify", str(path), "--live"])
        # No on-ledger txids → honest verdict, exit 0.
        assert result.exit_code == 0
        assert "no on-ledger" in result.output.lower()


# ── (e) the offline hash layer ALWAYS runs, even under --live ──────────────


class TestHashLayerAlwaysRuns:
    @pytest.mark.asyncio
    async def test_fetch_error_is_network_not_fake(self):
        """A read-back failure must NOT be reported as proof the tx is fake."""
        pack = _proof_pack([{"txid": TXID_GOOD, "network": "testnet"}])
        live = await verify_proof_pack_live(pack, transport=_FetchErrorTransport())

        assert live.overall_passed is False  # couldn't confirm the anchor
        r = live.tx_results[0]
        assert r.status == LIVE_FAIL
        # Reason must blame the NETWORK, not claim the tx doesn't exist.
        assert "couldn't reach the ledger" in r.reason.lower()
        assert "not found" not in r.reason.lower()

    def test_hash_tampered_pack_fails_even_with_live(self, tmp_path, monkeypatch):
        """A hash-tampered pack fails the HASH layer even under --live.

        The live check must NOT be attempted for a pack we already know was
        edited locally — and the command must exit non-zero on the hash failure.
        """
        import xrpl_lab.reporting as reporting

        pack = _proof_pack([{"txid": TXID_GOOD, "network": "testnet"}])
        pack["address"] = "rTamperedAfterSealXXXXXXXXXXXX"  # tamper after seal
        path = tmp_path / "proof.json"
        path.write_text(json.dumps(pack), encoding="utf-8")

        # If the live path were (wrongly) attempted, this stub would make the
        # tx PASS on-ledger — proving the command still fails purely on hash.
        monkeypatch.setattr(
            reporting, "_default_transport_factory",
            lambda network: _passing_factory_transport(),
        )

        runner = CliRunner()
        result = runner.invoke(main, ["proof", "verify", str(path), "--live"])
        assert result.exit_code == 1
        assert "FAIL" in result.output
        # On-ledger verification was skipped because the hash failed.
        assert "skipped" in result.output.lower()

    def test_valid_pack_cli_live_passes(self, tmp_path, monkeypatch):
        """Happy-path CLI: sealed pack with a real, resolving txid → exit 0."""
        import xrpl_lab.reporting as reporting

        pack = _proof_pack([{"txid": TXID_GOOD, "network": "testnet"}])
        path = tmp_path / "proof.json"
        path.write_text(json.dumps(pack), encoding="utf-8")

        monkeypatch.setattr(
            reporting, "_default_transport_factory",
            lambda network: _passing_factory_transport(),
        )

        runner = CliRunner()
        result = runner.invoke(main, ["proof", "verify", str(path), "--live"])
        assert result.exit_code == 0
        assert "On-ledger verdict: PASS" in result.output


def _passing_factory_transport():
    """A DryRunTransport pre-loaded so TXID_GOOD resolves validated+success."""
    t = DryRunTransport()
    t.set_tx_fixtures({TXID_GOOD: _good_txinfo(TXID_GOOD)})
    return t


# ── certificate --live: honest "no txids embedded" ────────────────────────


class TestCertificateLive:
    @pytest.mark.asyncio
    async def test_certificate_has_no_onledger_txids(self):
        cert = {
            "xrpl_lab_certificate": True,
            "version": "2.0.0",
            "network": "testnet",
            "address": LEARNER_ADDR,
            "total_modules": 3,
            "total_transactions": 10,
        }
        _seal(cert)
        live = await verify_certificate_live(cert, transport=_NotFoundTransport())
        assert live.overall_passed is True
        assert live.no_onledger_txids is True
        assert "proof pack" in live.note.lower()

    def test_cert_verify_cli_live_is_pass(self, tmp_path):
        cert = {
            "xrpl_lab_certificate": True,
            "version": "2.0.0",
            "network": "testnet",
            "address": LEARNER_ADDR,
            "total_modules": 3,
            "total_transactions": 10,
        }
        _seal(cert)
        path = tmp_path / "cert.json"
        path.write_text(json.dumps(cert), encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(main, ["cert-verify", str(path), "--live"])
        assert result.exit_code == 0
        assert "nothing to anchor" in result.output.lower()


# ── backward-compat: no --live preserves pure hash behavior exactly ───────


class TestBackwardCompat:
    def test_proof_verify_no_live_is_pure_hash(self, tmp_path):
        pack = _proof_pack([{"txid": TXID_FAKE, "network": "testnet"}])
        path = tmp_path / "proof.json"
        path.write_text(json.dumps(pack), encoding="utf-8")

        runner = CliRunner()
        # WITHOUT --live, a fake txid with a valid hash still PASSES (the old,
        # documented hash-only behavior is preserved for backward compat).
        result = runner.invoke(main, ["proof", "verify", str(path)])
        assert result.exit_code == 0
        assert "PASS" in result.output
        assert "On-ledger" not in result.output

    def test_legacy_pack_completed_modules_txids_resolve(self):
        """Packs predating the `transactions` block fall back to module txids."""
        pack = {
            "xrpl_lab_proof_pack": True,
            "version": "1.0.0",
            "network": "testnet",
            "address": LEARNER_ADDR,
            "completed_modules": [
                {"module_id": "m1", "txids": [TXID_GOOD]},
            ],
            "total_transactions": 1,
        }
        _seal(pack)
        transport = DryRunTransport()
        transport.set_tx_fixtures({TXID_GOOD: _good_txinfo(TXID_GOOD)})

        import asyncio
        live = asyncio.run(verify_proof_pack_live(pack, transport=transport))
        assert live.overall_passed is True
        assert live.passed_count == 1
