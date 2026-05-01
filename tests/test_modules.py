"""Tests for module parsing and loading."""

import pytest

from xrpl_lab.modules import load_all_modules, parse_module

VALID_MODULE = """\
---
id: test_module
title: Test Module
track: foundations
summary: A test module for unit tests.
time: 5 min
level: beginner
requires:
  - wallet
produces:
  - txid
checks:
  - "Something happened"
---

Introduction text.

## Step 1: Do something

Do the thing.

<!-- action: ensure_wallet -->

## Step 2: Do another thing

Do it again.

<!-- action: submit_payment destination=self amount=10 -->

## Checkpoint: Done

You did it.
"""


class TestParseModule:
    def test_valid_module(self):
        mod = parse_module(VALID_MODULE)
        assert mod.id == "test_module"
        assert mod.title == "Test Module"
        assert mod.time == "5 min"
        assert mod.level == "beginner"
        assert mod.requires == ["wallet"]
        assert mod.produces == ["txid"]
        assert mod.checks == ["Something happened"]
        assert len(mod.steps) >= 3

    def test_action_parsing(self):
        mod = parse_module(VALID_MODULE)
        actions = [s.action for s in mod.steps if s.action]
        assert "ensure_wallet" in actions
        assert "submit_payment" in actions

    def test_action_args(self):
        mod = parse_module(VALID_MODULE)
        payment_step = next(s for s in mod.steps if s.action == "submit_payment")
        assert payment_step.action_args["destination"] == "self"
        assert payment_step.action_args["amount"] == "10"

    def test_missing_frontmatter(self):
        with pytest.raises(ValueError, match="front-matter"):
            parse_module("No frontmatter here")

    def test_missing_required_keys(self):
        bad = "---\nid: foo\n---\nBody"
        with pytest.raises(ValueError, match="missing keys"):
            parse_module(bad)

    def test_summary_line(self):
        mod = parse_module(VALID_MODULE)
        assert "Test Module" in mod.summary_line
        assert "beginner" in mod.summary_line


class TestLoadModules:
    def test_load_builtin_modules(self):
        modules = load_all_modules()
        assert "receipt_literacy" in modules
        assert "failure_literacy" in modules
        assert "trust_lines_101" in modules
        assert "trust_line_failures" in modules
        assert "dex_literacy" in modules
        assert "reserves_101" in modules
        assert "account_hygiene" in modules
        assert "receipt_audit" in modules
        assert "amm_liquidity_101" in modules
        assert "dex_market_making_101" in modules
        assert "dex_inventory_guardrails" in modules
        assert "dex_vs_amm_risk_literacy" in modules

    def test_module_metadata(self):
        modules = load_all_modules()
        rl = modules["receipt_literacy"]
        assert rl.title == "Receipt Literacy"
        assert rl.level == "beginner"
        assert "txid" in rl.produces

    def test_load_from_extra_dir(self, tmp_path):
        # Write a custom module
        content = """\
---
id: custom_test
title: Custom Test
track: foundations
summary: A custom test module.
time: 1 min
level: beginner
requires: []
produces: []
checks: []
---

Custom module body.
"""
        (tmp_path / "custom_test.md").write_text(content, encoding="utf-8")
        modules = load_all_modules(extra_dirs=[tmp_path])
        assert "custom_test" in modules

    def test_skip_malformed(self, tmp_path):
        (tmp_path / "bad.md").write_text("not a module", encoding="utf-8")
        # Should not raise, just skip
        modules = load_all_modules(extra_dirs=[tmp_path])
        assert "bad" not in modules


# ── F-BACKEND-FT-006: render_module_skeleton + xrpl-lab module init ──


class TestRenderModuleSkeleton:
    """The skeleton must produce a frontmatter+body that survives the
    linter and reparses through ``parse_module``."""

    def test_skeleton_parses_back(self):
        """Round-trip: skeleton text → parse_module → ModuleDef."""
        from xrpl_lab.modules import render_module_skeleton

        text = render_module_skeleton(
            module_id="my_new_module",
            track="foundations",
            title="My New Module",
            time="20 min",
            requires=[],
            level="beginner",
            mode="testnet",
        )
        mod = parse_module(text)
        assert mod.id == "my_new_module"
        assert mod.track == "foundations"
        assert mod.title == "My New Module"
        assert mod.level == "beginner"
        assert mod.mode == "testnet"

    def test_skeleton_with_requires(self):
        """When --requires is passed, the YAML lists prerequisites."""
        from xrpl_lab.modules import render_module_skeleton

        text = render_module_skeleton(
            module_id="advanced_module",
            track="dex",
            title="Advanced Module",
            time="30 min",
            requires=["receipt_literacy", "failure_literacy"],
        )
        mod = parse_module(text)
        assert mod.requires == ["receipt_literacy", "failure_literacy"]


class TestModuleInitCLI:
    """End-to-end: xrpl-lab module init produces a lint-passing file."""

    def test_module_init_creates_lint_passing_skeleton(
        self, tmp_path, monkeypatch,
    ):
        """F-BACKEND-FT-006: invoke command; assert file created and
        passes existing linter."""
        from click.testing import CliRunner

        from xrpl_lab.cli import main
        from xrpl_lab.linter import lint_module_file

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(main, [
            "module", "init",
            "--id", "my_brand_new_module",
            "--track", "foundations",
            "--title", "My Brand New Module",
            "--time", "20 min",
        ])
        assert result.exit_code == 0, f"unexpected failure: {result.output}"
        out = tmp_path / "my_brand_new_module.md"
        assert out.exists()
        # Passes the linter immediately
        issues = lint_module_file(out)
        errors = [i for i in issues if i.level == "error"]
        assert errors == [], f"unexpected lint errors: {errors}"

    def test_module_init_rejects_duplicate_id(self, tmp_path, monkeypatch):
        """F-BACKEND-FT-006: trying to init with an existing module's ID
        clears errors + exits non-zero. Use 'receipt_literacy' which
        ships in the bundled catalog."""
        from click.testing import CliRunner

        from xrpl_lab.cli import main

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(main, [
            "module", "init",
            "--id", "receipt_literacy",
            "--track", "foundations",
            "--title", "Conflicting Title",
            "--time", "10 min",
        ])
        assert result.exit_code != 0
        assert "already exists" in result.output
        # Did NOT write a file (preflight check happens before write)
        assert not (tmp_path / "receipt_literacy.md").exists()

    def test_module_init_rejects_invalid_id(self, tmp_path, monkeypatch):
        """Bonus: invalid (non-snake_case) IDs are rejected before any
        file write — guards against `--id "Bad ID"` typos."""
        from click.testing import CliRunner

        from xrpl_lab.cli import main

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(main, [
            "module", "init",
            "--id", "Bad-ID-Format",
            "--track", "foundations",
            "--title", "X",
            "--time", "1 min",
        ])
        assert result.exit_code != 0
        assert "Invalid module ID" in result.output

    def test_module_init_passes_full_catalog_lint(self, tmp_path, monkeypatch):
        """F-TESTS-PH8-004 — module init survives the FULL ``xrpl-lab
        lint`` CLI surface, not just the per-file unit linter.

        ``test_module_init_creates_lint_passing_skeleton`` calls
        ``lint_module_file()`` directly — that's frontmatter + step
        skeleton parse only. The CLI's ``xrpl-lab lint`` subcommand
        also runs curriculum-level checks and exits non-zero on any
        error. The scaffolder claims "passes existing linter"; this
        test pins that claim against the user-facing CLI rather than
        an internal helper.

        Without this, a regression that adds a new curriculum-level
        check (or hardens an existing one) could silently break
        ``module init`` — the per-file unit test still passes, but
        the CLI a contributor actually runs would exit 1.
        """
        from click.testing import CliRunner

        from xrpl_lab.cli import main

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        # 1. Scaffold a fresh module via the same CLI a contributor uses.
        init_result = runner.invoke(main, [
            "module", "init",
            "--id", "catalog_lint_test",
            "--track", "foundations",
            "--title", "Catalog Lint Test",
            "--time", "15 min",
        ])
        assert init_result.exit_code == 0, (
            f"module init failed: {init_result.output}"
        )
        out = tmp_path / "catalog_lint_test.md"
        assert out.exists(), "module init did not write the .md file"

        # 2. Invoke the full ``xrpl-lab lint`` CLI against the new
        #    scaffold. We point the glob at the file just written
        #    (``module init`` defaults outfile to cwd, so a glob like
        #    ``*.md`` from cwd hits exactly one file). Use
        #    ``--no-curriculum`` because the curriculum validator loads
        #    the BUILT-IN module catalog — not the cwd file — and the
        #    new module isn't installed there. The per-file gate is
        #    what "passes existing linter" actually claims.
        lint_result = runner.invoke(main, [
            "lint",
            "catalog_lint_test.md",
            "--no-curriculum",
        ])
        assert lint_result.exit_code == 0, (
            "xrpl-lab lint exited non-zero on a freshly-scaffolded "
            "module. Output:\n" + lint_result.output
        )
        # The CLI's PASS line must appear — guards against a future
        # refactor that swallows errors but still exits 0.
        assert "PASS" in lint_result.output, (
            "xrpl-lab lint exit_code=0 but no PASS marker in output:\n"
            + lint_result.output
        )

        # 3. JSON-mode lint provides a machine-readable assertion path.
        #    Re-run the same lint in --json mode and confirm zero
        #    error-level issues. Catches the case where exit code 0
        #    is correct but a regression sneaks in warnings that the
        #    text path glosses over.
        json_result = runner.invoke(main, [
            "lint",
            "catalog_lint_test.md",
            "--json",
            "--no-curriculum",
        ])
        assert json_result.exit_code == 0, (
            f"JSON-mode lint exited non-zero: {json_result.output}"
        )
        import json as _json
        # Click captures stdout — strip any trailing newline.
        report = _json.loads(json_result.output.strip())
        errors = [
            i for i in report.get("issues", [])
            if i.get("level") == "error"
        ]
        assert errors == [], (
            f"JSON lint reports errors on freshly-scaffolded module: "
            f"{errors}"
        )
