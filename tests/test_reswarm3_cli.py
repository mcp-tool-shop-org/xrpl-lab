"""Re-swarm Stage A regression tests (CL-001 .. CL-006).

Each test pins a specific finding fixed in this wave. Run in isolation:
    python -m pytest tests/test_reswarm3_cli.py -q
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from xrpl_lab.cli import main

# ── Shared helpers ───────────────────────────────────────────────────


def _recompute_pack_hash(data: dict) -> str:
    """Reproduce the documented integrity procedure."""
    d = dict(data)
    d["integrity_sha256"] = ""
    canonical = json.dumps(d, indent=2, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


# ── CL-001: dry-run provenance sealed into the audit pack + MD banner ─


class TestCL001DryRunProvenance:
    def test_dry_run_pack_carries_provenance_inside_hash(self, tmp_path):
        """A dry-run audit pack must carry dry_run provenance AND that
        provenance must be inside the hashed content (non-vacuous seal)."""
        import asyncio

        from xrpl_lab.audit import run_audit, write_audit_pack
        from xrpl_lab.transport.dry_run import DryRunTransport

        report = asyncio.run(run_audit(DryRunTransport(), ["TX1"], dry_run=True))
        pack_path = tmp_path / "pack.json"
        write_audit_pack(report, pack_path)
        data = json.loads(pack_path.read_text(encoding="utf-8"))

        # provenance present and truthful
        assert data.get("dry_run") is True
        assert data.get("network") == "dry-run"

        # the seal is non-vacuous: recomputing the hash over the stored
        # content reproduces the stored hash (provenance is part of it)
        assert data["integrity_sha256"] == _recompute_pack_hash(data)

        # and if we flip provenance the hash no longer matches — proves the
        # field is genuinely folded into the hash, not cosmetic
        tampered = dict(data)
        tampered["dry_run"] = False
        tampered["network"] = "testnet"
        assert data["integrity_sha256"] != _recompute_pack_hash(tampered)

    def test_testnet_pack_backward_compatible(self, tmp_path):
        """A non-dry-run pack keeps dry_run=false and a stable hash shape.

        RA-001 (F-a8db1a2d) update: the pack's ``network`` is no longer a
        hardcoded 'testnet' literal — it now seals the network the TRANSPORT
        actually classified (run_audit reads net_info.network). This test's
        stand-in transport IS the DryRunTransport, so the honest label here
        is 'dry-run' even though the dry_run flag defaults False; a real
        testnet run (XRPLTestnetTransport at the default RPC) still seals
        'testnet'. The devnet/testnet truthfulness cases are pinned in
        tests/test_reswarm4_reporting_audit.py.
        """
        import asyncio

        from xrpl_lab.audit import run_audit, write_audit_pack
        from xrpl_lab.transport.dry_run import DryRunTransport

        # dry_run defaults False -> the "real" pack shape
        report = asyncio.run(run_audit(DryRunTransport(), ["TX1"]))
        pack_path = tmp_path / "pack.json"
        write_audit_pack(report, pack_path)
        data = json.loads(pack_path.read_text(encoding="utf-8"))

        assert data.get("dry_run") is False
        # Honest network label: what the transport reports, not a literal.
        assert data.get("network") == "dry-run"
        assert data["integrity_sha256"] == _recompute_pack_hash(data)

    def test_dry_run_md_shows_simulated_banner(self, tmp_path):
        import asyncio

        from xrpl_lab.audit import run_audit, write_audit_report_md
        from xrpl_lab.transport.dry_run import DryRunTransport

        report = asyncio.run(run_audit(DryRunTransport(), ["TX1"], dry_run=True))
        md_path = tmp_path / "report.md"
        write_audit_report_md(report, md_path)
        text = md_path.read_text(encoding="utf-8")
        assert "SIMULATED" in text

    def test_testnet_md_has_no_simulated_banner(self, tmp_path):
        import asyncio

        from xrpl_lab.audit import run_audit, write_audit_report_md
        from xrpl_lab.transport.dry_run import DryRunTransport

        report = asyncio.run(run_audit(DryRunTransport(), ["TX1"]))
        md_path = tmp_path / "report.md"
        write_audit_report_md(report, md_path)
        text = md_path.read_text(encoding="utf-8")
        assert "SIMULATED" not in text


# ── CL-002: audit command exit code gating ───────────────────────────


def _write_txids(dir_: Path, txids: list[str]) -> Path:
    p = dir_ / "txids.txt"
    p.write_text("\n".join(txids) + "\n", encoding="utf-8")
    return p


class TestCL002AuditExitCode:
    def test_all_pass_exits_zero(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            txp = _write_txids(Path("."), ["ABCDEF0123456789"])
            result = runner.invoke(
                main, ["audit", "--txids", str(txp), "--dry-run", "--no-pack"]
            )
            assert result.exit_code == 0, result.output

    def test_failing_verdict_exits_nonzero(self, tmp_path):
        """A verdict that fails an expectation must gate the exit non-zero.

        The dry-run tx is always a Payment; an expectations file that only
        allows Escrow forces a ``fail`` verdict, exercising the gate without
        depending on transport internals.
        """
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            txp = _write_txids(Path("."), ["ABCDEF0123456789"])
            expect = Path("expect.json")
            expect.write_text(
                json.dumps({"defaults": {"types_allowed": ["Escrow"]}}),
                encoding="utf-8",
            )
            result = runner.invoke(
                main,
                ["audit", "--txids", str(txp), "--expect", str(expect),
                 "--dry-run", "--no-pack"],
            )
            assert result.exit_code != 0, result.output


# ── CL-003: fund / send exit 1 on no-wallet ──────────────────────────


class TestCL003NoWalletExit:
    def test_fund_no_wallet_exits_1(self, tmp_path, monkeypatch):
        # Point XRPL_LAB_HOME at an empty dir so there is genuinely no wallet
        # (the real ~/.xrpl-lab is otherwise consulted regardless of cwd).
        empty_home = tmp_path / "home_fund"
        empty_home.mkdir()
        monkeypatch.setenv("XRPL_LAB_HOME", str(empty_home))
        runner = CliRunner()
        result = runner.invoke(main, ["fund", "--dry-run"])
        assert result.exit_code == 1, result.output

    def test_send_no_wallet_exits_1(self, tmp_path, monkeypatch):
        empty_home = tmp_path / "home_send"
        empty_home.mkdir()
        monkeypatch.setenv("XRPL_LAB_HOME", str(empty_home))
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["send", "--to", "rDEST00000000000000000000000000000",
             "--amount", "1", "--dry-run"],
        )
        assert result.exit_code == 1, result.output


# ── CL-004: send rejects non-finite amounts before transport ─────────


class TestCL004NonFiniteAmount:
    @pytest.mark.parametrize("amount", ["Infinity", "1e500", "-Infinity", "NaN"])
    def test_bad_amount_exits_2(self, tmp_path, amount):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                main,
                ["send", "--to", "rDEST00000000000000000000000000000",
                 "--amount", amount, "--dry-run"],
            )
            assert result.exit_code == 2, f"{amount!r}: {result.output}"


# ── CL-005: cohort-status --format json emits no absolute path ───────


class TestCL005CohortDirBasename:
    def test_cohort_dir_is_basename(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cohort = Path("mycohort")
            cohort.mkdir()
            result = runner.invoke(
                main, ["cohort-status", "--dir", str(cohort), "--format", "json"]
            )
            assert result.exit_code == 0, result.output
            data = json.loads(result.output)
            cohort_dir = data["cohort_dir"]
            # basename only — no path separators, no drive/username leak
            assert cohort_dir == "mycohort"
            assert "/" not in cohort_dir
            assert "\\" not in cohort_dir
            assert ":" not in cohort_dir


# ── CL-006: lint of a single-module subset glob does not fail on an ──
#            unrelated module's curriculum error ─────────────────────


class TestCL006LintSubset:
    def test_single_module_glob_not_failed_by_unrelated_curriculum(self, tmp_path):
        """Linting one clean module via a subset glob must not exit non-zero
        because of curriculum errors that span other modules."""
        runner = CliRunner()
        # Point at a real repo module so the file itself lints clean.
        repo_root = Path(__file__).resolve().parent.parent
        modules_dir = repo_root / "modules"
        md_files = sorted(modules_dir.glob("*.md"))
        assert md_files, "no modules found to lint"
        one = md_files[0]
        rel = one.relative_to(repo_root).as_posix()

        result = runner.invoke(main, ["lint", rel], catch_exceptions=False)
        # subset glob: a clean single module must not be failed by
        # curriculum errors that belong to unrelated modules
        assert result.exit_code == 0, result.output
