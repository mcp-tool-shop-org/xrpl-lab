"""Tests for module parsing and loading."""

import pytest

from xrpl_lab.modules import load_all_modules, parse_module

VALID_MODULE = """\
---
id: test_module
title: Test Module
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
