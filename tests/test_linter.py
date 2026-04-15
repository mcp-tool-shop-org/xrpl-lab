"""Tests for the module linter (Phase 2C)."""

from __future__ import annotations

from pathlib import Path

import pytest

from xrpl_lab.linter import LintResult, lint_module_file, lint_module_text

FIXTURES = Path(__file__).parent / "fixtures"


# ── Helper ───────────────────────────────────────────────────────────


def _lint_fixture(name: str) -> list:
    """Lint a fixture file and return the issues."""
    return lint_module_file(FIXTURES / name)


# ── Good modules should pass ────────────────────────────────────────


class TestLinterGood:
    def test_minimal_module_passes(self):
        issues = _lint_fixture("good_minimal.md")
        errors = [i for i in issues if i.level == "error"]
        assert not errors

    def test_real_module_passes(self):
        """At least one real bundled module should lint cleanly (no errors)."""
        modules_dir = Path(__file__).parent.parent / "modules"
        if not modules_dir.exists():
            pytest.skip("modules dir not found")
        first_md = next(modules_dir.glob("*.md"), None)
        if first_md is None:
            pytest.skip("no modules found")
        issues = lint_module_file(first_md)
        errors = [i for i in issues if i.level == "error"]
        assert not errors, f"Real module {first_md.name} has errors: {errors}"


# ── Frontmatter errors ──────────────────────────────────────────────


class TestLinterFrontmatter:
    def test_missing_id_is_error(self):
        issues = _lint_fixture("bad_missing_id.md")
        errors = [i for i in issues if i.level == "error"]
        assert len(errors) >= 1
        assert any("id" in i.message.lower() for i in errors)

    def test_no_frontmatter_is_error(self):
        issues = lint_module_text("# Just some markdown\n\nNo frontmatter here.", "no_fm.md")
        assert len(issues) >= 1
        assert issues[0].level == "error"
        assert "front-matter" in issues[0].message.lower() or "front" in issues[0].message.lower()


# ── Action validation ────────────────────────────────────────────────


class TestLinterActions:
    def test_unknown_action_is_error(self):
        issues = _lint_fixture("bad_unknown_action.md")
        errors = [i for i in issues if i.level == "error"]
        assert len(errors) >= 1
        assert any("totally_bogus_action" in i.message for i in errors)

    def test_bad_payload_is_error(self):
        issues = _lint_fixture("bad_payload.md")
        errors = [i for i in issues if i.level == "error"]
        assert len(errors) >= 1
        assert any("min_xrp_drops" in i.location for i in errors)


# ── dry_run_only labeling ────────────────────────────────────────────


class TestLinterDryRunLabel:
    def test_amm_without_dry_run_label_warns(self):
        issues = _lint_fixture("bad_amm_no_label.md")
        warnings = [i for i in issues if i.level == "warning"]
        assert any("dry_run_only" in i.message for i in warnings)

    def test_dry_run_without_amm_warns(self):
        issues = _lint_fixture("bad_dry_run_no_amm.md")
        warnings = [i for i in issues if i.level == "warning"]
        assert any("dry_run_only" in i.message or "AMM" in i.message for i in warnings)


# ── LintResult ────────────────────────────────────────────────────────


class TestLintResult:
    def test_empty_result_passes(self):
        r = LintResult()
        assert r.passed
        assert r.error_count == 0
        assert r.warning_count == 0

    def test_json_output_stable(self):
        import json

        r = LintResult()
        data = json.loads(r.to_json())
        assert data["passed"] is True
        assert data["errors"] == 0
        assert data["warnings"] == 0
        assert data["issues"] == []

    def test_result_with_errors_fails(self):
        from xrpl_lab.linter import LintIssue

        r = LintResult(issues=[
            LintIssue(level="error", module="m", location="l", message="bad"),
        ])
        assert not r.passed
        assert r.error_count == 1

    def test_result_with_only_warnings_passes(self):
        from xrpl_lab.linter import LintIssue

        r = LintResult(issues=[
            LintIssue(level="warning", module="m", location="l", message="meh"),
        ])
        assert r.passed
        assert r.warning_count == 1


# ── All real modules lint cleanly ─────────────────────────────────────


class TestLinterAllModules:
    def test_all_bundled_modules_pass(self):
        """Every bundled .md module should have zero lint errors."""
        modules_dir = Path(__file__).parent.parent / "modules"
        if not modules_dir.exists():
            pytest.skip("modules dir not found")
        md_files = sorted(modules_dir.glob("*.md"))
        if not md_files:
            pytest.skip("no modules found")

        all_errors = []
        for md in md_files:
            issues = lint_module_file(md)
            errors = [i for i in issues if i.level == "error"]
            if errors:
                all_errors.extend(errors)

        assert not all_errors, (
            f"{len(all_errors)} error(s) in bundled modules:\n"
            + "\n".join(str(e) for e in all_errors)
        )
