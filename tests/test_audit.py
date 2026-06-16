"""Tests for audit engine — parsing, verdicts, reports, and pack integrity."""

import hashlib
import json

import pytest

from xrpl_lab.audit import (
    ENGINE_RESULT_MISMATCH,
    MEMO_MISSING,
    NOT_FOUND,
    NOT_VALIDATED,
    TYPE_DISALLOWED,
    AuditConfig,
    audit_tx,
    parse_expectations,
    parse_txids_file,
    parse_txids_list,
    run_audit,
    write_audit_pack,
    write_audit_report_csv,
    write_audit_report_md,
)
from xrpl_lab.transport.base import TxInfo
from xrpl_lab.transport.dry_run import DryRunTransport

# ── Parsing tests ────────────────────────────────────────────────────


class TestParseTxids:
    def test_basic_file(self, tmp_path):
        f = tmp_path / "txids.txt"
        f.write_text("AAAA\nBBBB\nCCCC\n", encoding="utf-8")
        result = parse_txids_file(f)
        assert result == ["AAAA", "BBBB", "CCCC"]

    def test_comments_and_blanks(self, tmp_path):
        f = tmp_path / "txids.txt"
        f.write_text(
            "# Header comment\n"
            "AAAA\n"
            "\n"
            "# Another comment\n"
            "BBBB\n"
            "   \n"
            "CCCC\n",
            encoding="utf-8",
        )
        result = parse_txids_file(f)
        assert result == ["AAAA", "BBBB", "CCCC"]

    def test_empty_file(self, tmp_path):
        f = tmp_path / "txids.txt"
        f.write_text("# only comments\n\n", encoding="utf-8")
        result = parse_txids_file(f)
        assert result == []

    def test_whitespace_stripped(self, tmp_path):
        f = tmp_path / "txids.txt"
        f.write_text("  AAAA  \n  BBBB  \n", encoding="utf-8")
        result = parse_txids_file(f)
        assert result == ["AAAA", "BBBB"]

    def test_parse_list(self):
        result = parse_txids_list(["A", "", "B", "  ", "C"])
        assert result == ["A", "B", "C"]


class TestParseExpectations:
    def test_defaults_only(self, tmp_path):
        f = tmp_path / "expect.json"
        f.write_text(json.dumps({
            "defaults": {
                "require_validated": True,
                "require_success": True,
                "memo_prefix": "XRPLLAB|",
            }
        }), encoding="utf-8")
        config = parse_expectations(f)
        assert config.require_validated is True
        assert config.require_success is True
        assert config.memo_prefix == "XRPLLAB|"

    def test_with_overrides(self, tmp_path):
        f = tmp_path / "expect.json"
        f.write_text(json.dumps({
            "defaults": {"require_success": True},
            "overrides": {
                "TX_FAIL_1": {
                    "require_success": False,
                    "expected_engine_result": "tecPATH_DRY",
                }
            },
        }), encoding="utf-8")
        config = parse_expectations(f)
        assert "TX_FAIL_1" in config.overrides
        assert config.overrides["TX_FAIL_1"]["expected_engine_result"] == "tecPATH_DRY"

    def test_types_allowed(self, tmp_path):
        f = tmp_path / "expect.json"
        f.write_text(json.dumps({
            "defaults": {
                "types_allowed": ["Payment", "TrustSet"],
            }
        }), encoding="utf-8")
        config = parse_expectations(f)
        assert config.types_allowed == ["Payment", "TrustSet"]

    def test_empty_file(self, tmp_path):
        f = tmp_path / "expect.json"
        f.write_text("{}", encoding="utf-8")
        config = parse_expectations(f)
        assert config.require_validated is True  # defaults
        assert config.require_success is True


# ── Verdict logic tests ──────────────────────────────────────────────


class TestAuditVerdict:
    def test_success_pass(self):
        tx = TxInfo(
            txid="TX1",
            tx_type="Payment",
            account="rSENDER",
            destination="rDEST",
            result_code="tesSUCCESS",
            validated=True,
            fee="12",
        )
        v = audit_tx(tx, AuditConfig())
        assert v.status == "pass"
        assert not v.failures
        assert any("tesSUCCESS" in c for c in v.checks)

    def test_not_found(self):
        tx = TxInfo(
            txid="TX_MISSING",
            result_code="fetch_error: Timed out",
        )
        v = audit_tx(tx, AuditConfig())
        assert v.status == "not_found"
        assert NOT_FOUND in v.failure_reasons

    def test_not_validated(self):
        tx = TxInfo(
            txid="TX2",
            tx_type="Payment",
            result_code="tesSUCCESS",
            validated=False,
        )
        v = audit_tx(tx, AuditConfig(require_validated=True))
        assert v.status == "fail"
        assert NOT_VALIDATED in v.failure_reasons

    def test_engine_result_mismatch(self):
        tx = TxInfo(
            txid="TX3",
            tx_type="Payment",
            result_code="tecUNFUNDED_PAYMENT",
            validated=True,
        )
        v = audit_tx(tx, AuditConfig(require_success=True))
        assert v.status == "fail"
        assert ENGINE_RESULT_MISMATCH in v.failure_reasons

    def test_expected_failure_pass(self):
        """When we expect a specific failure code, it should pass."""
        tx = TxInfo(
            txid="TX_EXPECTED_FAIL",
            tx_type="Payment",
            result_code="tecPATH_DRY",
            validated=True,
        )
        config = AuditConfig(
            overrides={
                "TX_EXPECTED_FAIL": {
                    "require_success": False,
                    "expected_engine_result": "tecPATH_DRY",
                }
            }
        )
        v = audit_tx(tx, config)
        assert v.status == "pass"
        assert any("matches expected" in c.lower() for c in v.checks)

    def test_expected_failure_wrong_code(self):
        """Expected tecPATH_DRY but got tecNO_DST — should fail."""
        tx = TxInfo(
            txid="TX_WRONG_FAIL",
            tx_type="Payment",
            result_code="tecNO_DST",
            validated=True,
        )
        config = AuditConfig(
            overrides={
                "TX_WRONG_FAIL": {
                    "expected_engine_result": "tecPATH_DRY",
                }
            }
        )
        v = audit_tx(tx, config)
        assert v.status == "fail"
        assert ENGINE_RESULT_MISMATCH in v.failure_reasons

    def test_type_disallowed(self):
        tx = TxInfo(
            txid="TX4",
            tx_type="OfferCreate",
            result_code="tesSUCCESS",
            validated=True,
        )
        config = AuditConfig(types_allowed=["Payment", "TrustSet"])
        v = audit_tx(tx, config)
        assert v.status == "fail"
        assert TYPE_DISALLOWED in v.failure_reasons

    def test_type_allowed(self):
        tx = TxInfo(
            txid="TX5",
            tx_type="Payment",
            result_code="tesSUCCESS",
            validated=True,
        )
        config = AuditConfig(types_allowed=["Payment", "TrustSet"])
        v = audit_tx(tx, config)
        assert v.status == "pass"

    def test_memo_prefix_found(self):
        tx = TxInfo(
            txid="TX6",
            tx_type="Payment",
            result_code="tesSUCCESS",
            validated=True,
            memos=["XRPLLAB|test"],
        )
        config = AuditConfig(memo_prefix="XRPLLAB|")
        v = audit_tx(tx, config)
        assert v.status == "pass"
        assert any("prefix" in c.lower() and "found" in c.lower() for c in v.checks)

    def test_memo_prefix_missing(self):
        tx = TxInfo(
            txid="TX7",
            tx_type="Payment",
            result_code="tesSUCCESS",
            validated=True,
            memos=["OTHER|memo"],
        )
        config = AuditConfig(memo_prefix="XRPLLAB|")
        v = audit_tx(tx, config)
        assert v.status == "fail"
        assert MEMO_MISSING in v.failure_reasons

    def test_memo_no_memos(self):
        tx = TxInfo(
            txid="TX8",
            tx_type="Payment",
            result_code="tesSUCCESS",
            validated=True,
        )
        config = AuditConfig(memo_prefix="XRPLLAB|")
        v = audit_tx(tx, config)
        assert v.status == "fail"
        assert MEMO_MISSING in v.failure_reasons

    def test_multiple_failures(self):
        tx = TxInfo(
            txid="TX9",
            tx_type="OfferCreate",
            result_code="tecUNFUNDED",
            validated=False,
        )
        config = AuditConfig(
            require_validated=True,
            require_success=True,
            types_allowed=["Payment"],
            memo_prefix="XRPLLAB|",
        )
        v = audit_tx(tx, config)
        assert v.status == "fail"
        assert len(v.failure_reasons) == 4
        assert NOT_VALIDATED in v.failure_reasons
        assert ENGINE_RESULT_MISMATCH in v.failure_reasons
        assert TYPE_DISALLOWED in v.failure_reasons
        assert MEMO_MISSING in v.failure_reasons

    def test_no_requirements(self):
        """With all requirements off, any tx passes."""
        tx = TxInfo(
            txid="TX10",
            tx_type="Payment",
            result_code="tecFAILED",
            validated=False,
        )
        config = AuditConfig(
            require_validated=False,
            require_success=False,
        )
        v = audit_tx(tx, config)
        assert v.status == "pass"


# ── Run audit tests ──────────────────────────────────────────────────


class TestRunAudit:
    @pytest.mark.asyncio
    async def test_basic_audit(self):
        transport = DryRunTransport()
        report = await run_audit(transport, ["TX1", "TX2"])
        assert report.total == 2
        assert report.passed == 2  # dry-run default txs pass
        assert report.failed == 0

    @pytest.mark.asyncio
    async def test_audit_with_fixtures(self):
        transport = DryRunTransport()
        transport.set_tx_fixtures({
            "TX_OK": TxInfo(
                txid="TX_OK",
                tx_type="Payment",
                result_code="tesSUCCESS",
                validated=True,
            ),
            "TX_FAIL": TxInfo(
                txid="TX_FAIL",
                tx_type="Payment",
                result_code="tecUNFUNDED_PAYMENT",
                validated=True,
            ),
        })
        report = await run_audit(transport, ["TX_OK", "TX_FAIL"])
        assert report.total == 2
        assert report.passed == 1
        assert report.failed == 1

    @pytest.mark.asyncio
    async def test_failure_summary(self):
        transport = DryRunTransport()
        transport.set_tx_fixtures({
            "TX1": TxInfo(txid="TX1", result_code="fetch_error: not found"),
            "TX2": TxInfo(txid="TX2", result_code="fetch_error: timeout"),
            "TX3": TxInfo(
                txid="TX3", tx_type="Payment",
                result_code="tecFAILED", validated=True,
            ),
        })
        report = await run_audit(transport, ["TX1", "TX2", "TX3"])
        summary = report.failure_summary()
        assert NOT_FOUND in summary
        assert summary[NOT_FOUND] == 2
        assert ENGINE_RESULT_MISMATCH in summary


# ── Report generation tests ──────────────────────────────────────────


class TestReportGeneration:
    @pytest.mark.asyncio
    async def test_md_report(self, tmp_path):
        transport = DryRunTransport()
        report = await run_audit(transport, ["TX1"])
        path = tmp_path / "report.md"
        write_audit_report_md(report, path)
        content = path.read_text(encoding="utf-8")
        assert "Audit Report" in content
        assert "TX1" in content
        assert "PASS" in content

    @pytest.mark.asyncio
    async def test_csv_report(self, tmp_path):
        transport = DryRunTransport()
        report = await run_audit(transport, ["TX1"])
        path = tmp_path / "report.csv"
        write_audit_report_csv(report, path)
        content = path.read_text(encoding="utf-8")
        assert "txid" in content  # header
        assert "TX1" in content

    @pytest.mark.asyncio
    async def test_audit_pack(self, tmp_path):
        transport = DryRunTransport()
        report = await run_audit(transport, ["TX1"])
        path = tmp_path / "pack.json"
        write_audit_pack(report, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["tool"] == "xrpl-lab"
        assert data["summary"]["total"] == 1
        assert data["summary"]["passed"] == 1
        assert "integrity_sha256" in data
        assert len(data["integrity_sha256"]) == 64

    @pytest.mark.asyncio
    async def test_pack_hash_stable(self, tmp_path):
        """Same input should produce same hash."""
        transport = DryRunTransport()
        report = await run_audit(transport, ["TX1"])
        p1 = tmp_path / "pack1.json"
        p2 = tmp_path / "pack2.json"
        write_audit_pack(report, p1)
        write_audit_pack(report, p2)
        d1 = json.loads(p1.read_text(encoding="utf-8"))
        d2 = json.loads(p2.read_text(encoding="utf-8"))
        assert d1["integrity_sha256"] == d2["integrity_sha256"]

    @pytest.mark.asyncio
    async def test_md_report_with_failures(self, tmp_path):
        transport = DryRunTransport()
        transport.set_tx_fixtures({
            "TX_BAD": TxInfo(
                txid="TX_BAD",
                tx_type="Payment",
                result_code="tecUNFUNDED",
                validated=True,
            ),
        })
        report = await run_audit(transport, ["TX_BAD"])
        path = tmp_path / "report.md"
        write_audit_report_md(report, path)
        content = path.read_text(encoding="utf-8")
        assert "FAIL" in content
        assert "ENGINE_RESULT_MISMATCH" in content


# ── Audit-pack tamper detection (TESTS-A-003) ────────────────────────


class TestAuditPackTamperDetection:
    """``write_audit_pack`` embeds an ``integrity_sha256`` and documents a
    5-step verification procedure in its docstring (audit.py ~L377-382), but
    until now no test proved the procedure actually DETECTS tampering — unlike
    the proof pack / certificate, which have tamper tests (test_cli.py:
    ``test_proof_verify_tampered`` / ``test_cert_verify_tampered``).

    There is no ``verify_audit_pack`` function in source, so these tests
    replicate the DOCUMENTED procedure verbatim and prove BOTH halves:
      * a clean pack verifies (recomputed hash == stored hash), and
      * a pack with a mutated hashed field FAILS (recomputed != stored).

    The recompute mirrors the producer exactly (``json.dumps(pack,
    sort_keys=True, indent=2)`` over the pack with ``integrity_sha256``
    blanked, then sha256) so the test is a faithful external verifier, not
    a re-derivation of the producer's private logic.

    NOTE (out of this agent's scope — test-only): extracting a real
    ``verify_audit_pack()`` helper into ``audit.py`` so the documented
    procedure is tested CODE rather than prose-replicated-in-tests is a
    recommended FEATURE-pass follow-up. These tests pin the contract today.
    """

    @staticmethod
    def _recompute_from_documented_procedure(pack: dict) -> str:
        """Replicate the 5-step verification procedure from the
        ``write_audit_pack`` docstring and return the recomputed hash.

        Steps (verbatim from audit.py):
          1. (caller) read the file and parse JSON → ``pack``
          2. set ``pack["integrity_sha256"] = ""``
          3. serialize with ``json.dumps(pack, sort_keys=True, indent=2)``
          4. compute ``hashlib.sha256(serialization.encode()).hexdigest()``
          5. (caller) compare to the original ``integrity_sha256``
        """
        # Operate on a copy so step 2's blanking doesn't clobber the
        # caller's stored hash before they compare in step 5.
        recompute = dict(pack)
        recompute["integrity_sha256"] = ""
        canonical = json.dumps(recompute, sort_keys=True, indent=2)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @pytest.mark.asyncio
    async def test_audit_pack_verify_clean(self, tmp_path):
        """A pristine pack written by the real writer must verify: the
        recomputed hash (per the documented procedure) equals the stored
        ``integrity_sha256``."""
        transport = DryRunTransport()
        report = await run_audit(transport, ["TX1", "TX2"])
        path = tmp_path / "pack.json"
        write_audit_pack(report, path)

        pack = json.loads(path.read_text(encoding="utf-8"))
        stored = pack["integrity_sha256"]
        recomputed = self._recompute_from_documented_procedure(pack)

        assert recomputed == stored, (
            "clean audit pack failed self-verification — the documented "
            "5-step procedure does not reproduce the stored hash, so the "
            "integrity claim is unverifiable by an external auditor."
        )

    @pytest.mark.asyncio
    async def test_audit_pack_verify_tampered(self, tmp_path):
        """Mutating a hashed field after the pack is written must be
        DETECTED: the recomputed hash no longer matches the stored one.

        We mutate ``summary.passed`` (a hashed field — it sits inside the
        dict the producer hashes), simulating an attacker editing the
        verdict counts to claim more passes than actually occurred."""
        transport = DryRunTransport()
        report = await run_audit(transport, ["TX1", "TX2"])
        path = tmp_path / "pack.json"
        write_audit_pack(report, path)

        pack = json.loads(path.read_text(encoding="utf-8"))
        stored = pack["integrity_sha256"]

        # Tamper: inflate the passed count. This field is part of the
        # hashed payload, so any honest recompute must diverge.
        original_passed = pack["summary"]["passed"]
        pack["summary"]["passed"] = original_passed + 99

        recomputed = self._recompute_from_documented_procedure(pack)

        assert recomputed != stored, (
            "tampered audit pack passed verification — mutating "
            "summary.passed did NOT change the recomputed hash, so the "
            "integrity_sha256 provides no tamper protection."
        )


# ── CLI smoke test ───────────────────────────────────────────────────


class TestAuditCLI:
    def test_audit_command(self, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", tmp_path / "ws")
        from click.testing import CliRunner

        from xrpl_lab.cli import main

        # Write txids file
        txids_file = tmp_path / "txids.txt"
        txids_file.write_text("AAAA\nBBBB\n", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(main, [
            "audit", "--txids", str(txids_file), "--dry-run",
        ])
        assert result.exit_code == 0
        assert "Audit" in result.output
        assert "Checked" in result.output
        assert "Pass" in result.output

    def test_audit_with_expectations(self, tmp_path, monkeypatch):
        monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", tmp_path / "ws")
        from click.testing import CliRunner

        from xrpl_lab.cli import main

        txids_file = tmp_path / "txids.txt"
        txids_file.write_text("TX1\n", encoding="utf-8")

        expect_file = tmp_path / "expect.json"
        expect_file.write_text(json.dumps({
            "defaults": {"require_success": True, "memo_prefix": "XRPLLAB|"},
        }), encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(main, [
            "audit", "--txids", str(txids_file),
            "--expect", str(expect_file),
            "--dry-run",
        ])
        assert result.exit_code == 0

    def test_audit_empty_file(self, tmp_path):
        from click.testing import CliRunner

        from xrpl_lab.cli import main

        txids_file = tmp_path / "txids.txt"
        txids_file.write_text("# only comments\n", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(main, ["audit", "--txids", str(txids_file)])
        assert result.exit_code == 0
        assert "No txids" in result.output


# ── Default-path safety regression (F-TESTS-002) ─────────────────────


class TestDefaultPathSafety:
    """The CLI is the trust boundary for user-supplied paths (--md/--csv/--out
    accept whatever the user types). These tests lock in that the *default*
    audit-pack path stays inside the .xrpl-lab/ workspace sandbox so a future
    refactor cannot silently relocate secrets/proofs to an arbitrary location.

    Scope is intentionally tight (Mike: "if it expands beyond 2-3 assertions,
    push back"). We do NOT test path-traversal payloads — that's a CLI-trust
    surface concern out of scope for this regression.
    """

    @pytest.mark.asyncio
    async def test_default_audit_pack_path_is_inside_workspace(
        self, tmp_path
    ):
        """write_audit_pack with the CLI default path must resolve inside
        the .xrpl-lab/ workspace.

        Mirrors the path the CLI/handlers construct:
        ``.xrpl-lab/proofs/audit_pack_<ts>.json``.
        """
        import os
        from pathlib import Path

        # Run the CLI's pack-write inside tmp_path so we don't pollute the
        # real .xrpl-lab/ workspace.
        prev_cwd = Path.cwd()
        os.chdir(tmp_path)
        try:
            transport = DryRunTransport()
            report = await run_audit(transport, ["TX1"])
            default_path = Path(".xrpl-lab/proofs/audit_pack_TEST.json")
            written = write_audit_pack(report, default_path)

            workspace_root = (tmp_path / ".xrpl-lab").resolve()
            assert written.resolve().is_relative_to(workspace_root), (
                f"default audit-pack path escaped workspace: "
                f"{written.resolve()} not under {workspace_root}"
            )
        finally:
            os.chdir(prev_cwd)
