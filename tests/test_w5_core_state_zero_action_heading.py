"""Wave 5 Stage B — lint must reject zero-action Step headings (F-0c61a5e7)."""

from __future__ import annotations

from xrpl_lab.linter import lint_module_text

_FM = (
    "---\n"
    "id: zero_action_fixture\n"
    "title: Zero Action Fixture\n"
    "time: 1 min\n"
    "level: beginner\n"
    "track: foundations\n"
    "summary: fixture for zero-action lint\n"
    "---\n\n"
)


def _errors(text: str) -> list:
    return [i for i in lint_module_text(text, filename="zero_action_fixture.md")
            if i.level == "error"]


class TestZeroActionStepHeading:
    def test_step_with_zero_actions_is_error(self):
        """A ## Step heading with no action comment must fail lint.

        Before the fix, only ``len(found) > 1`` was checked — zero matches
        were silent, so a typo'd ``<!-- action: set-trust-line -->`` (hyphen
        breaks ``_ACTION_RE``) or a forgotten action shipped clean.
        """
        text = (
            _FM
            + "## Step 1: Do the thing\n\n"
            + "Prose that claims an action will run, but none is declared.\n"
        )
        errors = _errors(text)
        assert errors, "expected zero-action Step heading to produce a lint error"
        assert any(
            "action" in e.message.lower() and (
                "zero" in e.message.lower()
                or "no action" in e.message.lower()
                or "0 action" in e.message.lower()
                or "none" in e.message.lower()
            )
            for e in errors
        ), f"expected a zero-action message, got {[e.message for e in errors]}"

    def test_hyphenated_action_typo_is_error(self):
        """Malformed action comments that fail ``_ACTION_RE`` are len(found)==0."""
        text = (
            _FM
            + "## Step 1: Set a trust line\n\n"
            + "<!-- action: set-trust-line currency=LAB limit=1000 -->\n"
        )
        errors = _errors(text)
        assert errors, "hyphenated action typo must not lint clean"
        assert any("action" in e.message.lower() for e in errors)

    def test_checkpoint_without_action_is_allowed(self):
        """``## Checkpoint:`` headings are narrative wrap-ups, not action headings."""
        text = (
            _FM
            + "## Step 1: Ready\n\n"
            + "<!-- action: ensure_wallet -->\n\n"
            + "## Checkpoint: What you proved\n\n"
            + "You proved the wallet exists.\n"
        )
        errors = _errors(text)
        assert not errors, f"Checkpoint without action should be clean: {errors}"

    def test_narrative_only_opt_out_is_allowed(self):
        """Explicit ``<!-- narrative-only -->`` marks a Step as intentionally actionless."""
        text = (
            _FM
            + "## Step 1: Read the table\n\n"
            + "<!-- narrative-only -->\n\n"
            + "Here is a result-code table with no ledger call.\n"
        )
        errors = _errors(text)
        assert not errors, f"narrative-only Step should be clean: {errors}"

    def test_one_action_step_still_passes(self):
        text = (
            _FM
            + "## Step 1: Ready\n\n"
            + "<!-- action: ensure_wallet -->\n"
        )
        assert not _errors(text)

    def test_two_action_step_still_errors(self):
        text = (
            _FM
            + "## Step 1: Two things\n\n"
            + "<!-- action: ensure_wallet -->\n\n"
            + "<!-- action: ensure_funded -->\n"
        )
        errors = _errors(text)
        assert len(errors) >= 1
        assert any("only the first" in e.message for e in errors)
