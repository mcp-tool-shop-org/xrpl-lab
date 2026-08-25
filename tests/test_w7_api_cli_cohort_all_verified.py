"""Wave-7/8 api-cli — F-edd0c1d8 / F-a8c31e02.

``cohort-status`` already calls ``get_learner_status(state)`` but only exports
completed_count / total_modules / current_module / blockers / last_activity.
It drops ``all_verified`` (and related honesty fields), so a facilitator
grading from the cohort roster sees silent-green while learners have
completed-but-UNVERIFIED modules.

Fix under test: surface ``all_verified`` (plus unverified list/count and
artifact flags already on LearnerStatus) in JSON, CSV, and table.

Run in isolation:
    python -m pytest tests/test_w7_api_cli_cohort_all_verified.py -q
"""

from __future__ import annotations

import csv
import io
import json

from click.testing import CliRunner

from xrpl_lab.cli import main
from xrpl_lab.state import LabState


def _write_learner(cohort_dir, learner_id: str, *, verified: bool) -> None:
    learner_dir = cohort_dir / learner_id
    workspace = learner_dir / ".xrpl-lab"
    workspace.mkdir(parents=True)
    state = LabState(wallet_address="rFAKE")
    state.complete_module("receipt_literacy", txids=["TX1"], verified=verified)
    (workspace / "state.json").write_text(
        state.model_dump_json(indent=2), encoding="utf-8",
    )


def test_cohort_status_json_exposes_all_verified(tmp_path):
    """JSON roster must carry all_verified so silent-green is impossible."""
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    _write_learner(cohort, "alice", verified=True)
    _write_learner(cohort, "bob", verified=False)

    runner = CliRunner()
    result = runner.invoke(main, [
        "cohort-status", "--dir", str(cohort), "--format", "json",
    ])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    by_id = {r["learner_id"]: r for r in data["learners"]}
    assert by_id["alice"]["all_verified"] is True
    assert by_id["bob"]["all_verified"] is False
    assert "receipt_literacy" in by_id["bob"].get("unverified_modules", [])


def test_cohort_status_csv_exposes_all_verified(tmp_path):
    """CSV gradebook column must include all_verified."""
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    _write_learner(cohort, "alice", verified=True)
    _write_learner(cohort, "bob", verified=False)

    runner = CliRunner()
    result = runner.invoke(main, [
        "cohort-status", "--dir", str(cohort), "--format", "csv",
    ])
    assert result.exit_code == 0, result.output
    reader = csv.DictReader(io.StringIO(result.output))
    assert reader.fieldnames is not None
    assert "all_verified" in reader.fieldnames
    rows = {r["learner_id"]: r for r in reader}
    assert rows["alice"]["all_verified"].lower() in {"true", "1", "yes"}
    assert rows["bob"]["all_verified"].lower() in {"false", "0", "no"}


def test_cohort_status_table_surfaces_unverified(tmp_path):
    """Table output must not be silent-green when a learner is unverified."""
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    _write_learner(cohort, "bob", verified=False)

    runner = CliRunner()
    result = runner.invoke(main, ["cohort-status", "--dir", str(cohort)])
    assert result.exit_code == 0, result.output
    out = result.output.lower()
    assert "bob" in out
    # Facilitator-readable honesty signal (column header or cell text).
    assert "unverified" in out or "all_verified" in out or "verified" in out
