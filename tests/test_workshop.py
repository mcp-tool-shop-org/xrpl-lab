"""Tests for workshop module — facilitator status, support bundles, track summaries."""

from __future__ import annotations

import json
import time

import pytest

from xrpl_lab.state import CompletedModule, LabState, TxRecord
from xrpl_lab.workshop import (
    diagnose_recovery,
    get_learner_status,
    get_track_summaries,
    verify_support_bundle,
)


def _make_state(
    completed: list[str] | None = None,
    wallet: str | None = "rTestAddr123",
    txs: list[TxRecord] | None = None,
) -> LabState:
    """Build a LabState for testing without touching disk."""
    mods = [
        CompletedModule(module_id=mid, completed_at=time.time())
        for mid in (completed or [])
    ]
    return LabState(
        wallet_address=wallet,
        completed_modules=mods,
        tx_index=txs or [],
    )


# ── 4A: Learner Status ──────────────────────────────────────────────


class TestLearnerStatus:
    """get_learner_status returns deterministic, curriculum-aware truth."""

    def test_fresh_state_has_next_module(self) -> None:
        ls = get_learner_status(_make_state())
        assert ls.current_module is not None
        assert ls.completed_count == 0
        assert ls.total_modules > 0

    def test_no_wallet_is_blocker(self) -> None:
        ls = get_learner_status(_make_state(wallet=None))
        assert any("wallet" in b.lower() for b in ls.blockers)
        assert ls.is_blocked

    def test_completed_module_not_next(self) -> None:
        ls = get_learner_status(_make_state(completed=["receipt_literacy"]))
        assert ls.current_module != "receipt_literacy"
        assert "receipt_literacy" in ls.completed_modules

    def test_track_progress_covers_all_tracks(self) -> None:
        ls = get_learner_status(_make_state())
        track_names = {tp.track for tp in ls.track_progress}
        assert "foundations" in track_names
        assert "dex" in track_names

    def test_track_progress_reflects_completion(self) -> None:
        ls = get_learner_status(_make_state(completed=["receipt_literacy"]))
        foundations = next(tp for tp in ls.track_progress if tp.track == "foundations")
        assert "receipt_literacy" in foundations.completed
        assert foundations.done >= 1

    def test_all_complete_no_next(self) -> None:
        from xrpl_lab.modules import load_all_modules
        all_ids = list(load_all_modules().keys())
        ls = get_learner_status(_make_state(completed=all_ids))
        assert ls.current_module is None
        assert ls.completed_count == ls.total_modules

    def test_transactions_counted(self) -> None:
        txs = [
            TxRecord(txid="tx1", module_id="receipt_literacy", timestamp=time.time(),
                     network="testnet", success=True),
            TxRecord(txid="tx2", module_id="receipt_literacy", timestamp=time.time(),
                     network="testnet", success=False),
        ]
        ls = get_learner_status(_make_state(txs=txs))
        assert ls.total_transactions == 2
        assert ls.failed_transactions == 1

    def test_to_dict_roundtrips(self) -> None:
        ls = get_learner_status(_make_state())
        d = ls.to_dict()
        assert isinstance(d, dict)
        assert d["version"] == ls.version
        assert isinstance(d["track_progress"], list)
        # JSON-serializable
        json.dumps(d)

    def test_dry_run_module_shows_mode_hint(self) -> None:
        """If next module is dry-run, blocker list includes a mode hint."""
        from xrpl_lab.modules import load_all_modules
        modules = load_all_modules()
        dry_run_ids = [m.id for m in modules.values() if m.mode == "dry-run"]
        if not dry_run_ids:
            pytest.skip("No dry-run modules in curriculum")

        # Complete all prerequisites for a dry-run module
        from xrpl_lab.curriculum import build_graph
        graph = build_graph(modules)
        target = dry_run_ids[0]
        prereqs = graph.all_prerequisites(target)
        ls = get_learner_status(_make_state(completed=list(prereqs)))
        # next module might or might not be the dry-run one (depends on order)
        # but if it IS the dry-run one, mode hint should be present
        if ls.current_module == target:
            assert any("dry-run" in b for b in ls.blockers)

    def test_blocked_only_for_hard_blockers(self) -> None:
        """Mode hints don't set is_blocked=True — only wallet/prereqs do."""
        ls = get_learner_status(_make_state())
        # With a wallet and first module having no prereqs, should not be blocked
        assert not ls.is_blocked


# ── 4B: Support Bundles ──────────────────────────────────────────────


class TestSupportBundle:
    """Support bundle generation and verification."""

    def test_verify_valid_bundle(self) -> None:
        bundle_json = json.dumps({
            "schema": "xrpl-lab-support-bundle-v1",
            "version": "1.3.0",
            "generated": "2026-01-01T00:00:00Z",
            "learner": {
                "version": "1.3.0",
                "completed_count": 3,
                "total_modules": 12,
            },
            "network": "testnet",
        })
        valid, msg = verify_support_bundle(bundle_json)
        assert valid
        assert "well-formed" in msg.lower()

    def test_verify_rejects_bad_json(self) -> None:
        valid, msg = verify_support_bundle("not json {")
        assert not valid
        assert "JSON" in msg

    def test_verify_rejects_missing_fields(self) -> None:
        valid, msg = verify_support_bundle(json.dumps({"schema": "xrpl-lab-support-bundle-v1"}))
        assert not valid
        assert "Missing" in msg

    def test_verify_rejects_wrong_schema(self) -> None:
        bundle = {
            "schema": "unknown-v99",
            "version": "1.0",
            "generated": "now",
            "learner": {"version": "1.0", "completed_count": 0, "total_modules": 0},
            "network": "testnet",
        }
        valid, msg = verify_support_bundle(json.dumps(bundle))
        assert not valid
        assert "schema" in msg.lower()

    def test_verify_rejects_bad_learner(self) -> None:
        bundle = {
            "schema": "xrpl-lab-support-bundle-v1",
            "version": "1.0",
            "generated": "now",
            "learner": "not-an-object",
            "network": "testnet",
        }
        valid, msg = verify_support_bundle(json.dumps(bundle))
        assert not valid
        assert "object" in msg.lower()

    def test_verify_rejects_incomplete_learner(self) -> None:
        bundle = {
            "schema": "xrpl-lab-support-bundle-v1",
            "version": "1.0",
            "generated": "now",
            "learner": {},
            "network": "testnet",
        }
        valid, msg = verify_support_bundle(json.dumps(bundle))
        assert not valid
        assert "Learner" in msg

    def test_no_secrets_in_bundle_dict(self) -> None:
        """Support bundles must never contain seeds or private keys."""
        ls = get_learner_status(_make_state())
        d = ls.to_dict()
        text = json.dumps(d).lower()
        assert "seed" not in text
        assert "secret" not in text
        assert "private" not in text


# ── 4C: Track Summaries ─────────────────────────────────────────────


class TestTrackSummaries:
    """get_track_summaries returns accurate per-track completion info."""

    def test_empty_state_all_remaining(self) -> None:
        summaries = get_track_summaries(_make_state(completed=[]))
        for ts in summaries:
            assert ts.completed_modules == []
            assert not ts.is_complete
            assert ts.mode_breakdown == "none"

    def test_partial_completion(self) -> None:
        summaries = get_track_summaries(_make_state(completed=["receipt_literacy"]))
        foundations = next(ts for ts in summaries if ts.track == "foundations")
        assert "receipt_literacy" in foundations.completed_modules
        assert not foundations.is_complete
        assert len(foundations.remaining_modules) > 0

    def test_full_track_completion(self) -> None:
        from xrpl_lab.modules import load_all_modules
        modules = load_all_modules()
        foundations_ids = [m.id for m in modules.values() if m.track == "foundations"]
        summaries = get_track_summaries(_make_state(completed=foundations_ids))
        foundations = next(ts for ts in summaries if ts.track == "foundations")
        assert foundations.is_complete
        assert foundations.remaining_modules == []

    def test_mode_breakdown_testnet(self) -> None:
        summaries = get_track_summaries(_make_state(completed=["receipt_literacy"]))
        foundations = next(ts for ts in summaries if ts.track == "foundations")
        # receipt_literacy is testnet mode
        assert foundations.mode_breakdown == "testnet"

    def test_transaction_count_per_track(self) -> None:
        txs = [
            TxRecord(txid="tx1", module_id="receipt_literacy", timestamp=time.time(),
                     network="testnet", success=True),
            TxRecord(txid="tx2", module_id="dex_literacy", timestamp=time.time(),
                     network="testnet", success=True),
        ]
        summaries = get_track_summaries(_make_state(txs=txs))
        foundations = next(ts for ts in summaries if ts.track == "foundations")
        dex = next(ts for ts in summaries if ts.track == "dex")
        assert foundations.transaction_count == 1
        assert dex.transaction_count == 1

    def test_skills_from_checks(self) -> None:
        from xrpl_lab.modules import load_all_modules
        modules = load_all_modules()
        # Find a module with checks
        mod_with_checks = next(
            (m for m in modules.values() if m.checks), None
        )
        if mod_with_checks is None:
            pytest.skip("No modules with checks")
        summaries = get_track_summaries(
            _make_state(completed=[mod_with_checks.id])
        )
        track = next(ts for ts in summaries if ts.track == mod_with_checks.track)
        assert track.skills_practiced  # should have at least one skill


# ── CLI + API parity ─────────────────────────────────────────────────


class TestStatusParity:
    """CLI and API derive from the same workshop truth."""

    def test_learner_status_deterministic(self) -> None:
        """Same state → same status, always."""
        state = _make_state(completed=["receipt_literacy"])
        ls1 = get_learner_status(state)
        ls2 = get_learner_status(state)
        assert ls1.current_module == ls2.current_module
        assert ls1.blockers == ls2.blockers
        assert ls1.completed_count == ls2.completed_count

    def test_blocked_prerequisites(self) -> None:
        """A module with unmet prereqs must show a blocker."""
        from xrpl_lab.curriculum import build_graph
        from xrpl_lab.modules import load_all_modules

        modules = load_all_modules()
        graph = build_graph(modules)

        # Find a module with prerequisites
        mod_with_reqs = next(
            (m for m in modules.values() if m.requires), None
        )
        if mod_with_reqs is None:
            pytest.skip("No modules with prerequisites")

        # Don't complete any prereqs — skip to where this module would be next
        # The graph should never suggest this module until prereqs are met
        ordered = graph.canonical_order()
        completed = set()
        for mid in ordered:
            if mid == mod_with_reqs.id:
                break
            completed.add(mid)

        # Remove one prereq from completed
        if mod_with_reqs.requires:
            completed.discard(mod_with_reqs.requires[0])

        ls = get_learner_status(_make_state(completed=list(completed)))
        # If this module is now the next one, it should have a prerequisites blocker
        if ls.current_module == mod_with_reqs.id:
            assert any("prerequisite" in b.lower() for b in ls.blockers)


# ── 4D: Recovery Guidance ────────────────────────────────────────────


class TestRecoveryGuidance:
    """diagnose_recovery returns actionable hints for known stuck states."""

    def test_no_wallet_recovery(self) -> None:
        hints = diagnose_recovery(_make_state(wallet=None))
        situations = [h.situation for h in hints]
        assert any("wallet" in s.lower() for s in situations)
        commands = [h.command for h in hints]
        assert any("wallet create" in c for c in commands)

    def test_healthy_state_no_hints(self) -> None:
        hints = diagnose_recovery(_make_state())
        # Fresh state with wallet: no hard blockers (may have mode hints)
        hard_blockers = [
            h for h in hints
            if "wallet" in h.situation.lower() or "prerequisite" in h.situation.lower()
        ]
        assert hard_blockers == []

    def test_failed_tx_recovery(self) -> None:
        txs = [
            TxRecord(txid=f"fail{i}", module_id="receipt_literacy", timestamp=time.time(),
                     network="testnet", success=False)
            for i in range(4)
        ]
        hints = diagnose_recovery(_make_state(txs=txs))
        situations = [h.situation for h in hints]
        assert any("transaction failure" in s.lower() for s in situations)

    def test_all_complete_no_proof_pack(self) -> None:
        from xrpl_lab.modules import load_all_modules
        all_ids = list(load_all_modules().keys())
        hints = diagnose_recovery(_make_state(completed=all_ids))
        situations = [h.situation for h in hints]
        assert any("proof pack" in s.lower() for s in situations)

    def test_dry_run_module_hint(self) -> None:
        from xrpl_lab.curriculum import build_graph
        from xrpl_lab.modules import load_all_modules
        modules = load_all_modules()
        dry_run_ids = [m.id for m in modules.values() if m.mode == "dry-run"]
        if not dry_run_ids:
            pytest.skip("No dry-run modules")

        graph = build_graph(modules)
        target = dry_run_ids[0]
        prereqs = graph.all_prerequisites(target)
        hints = diagnose_recovery(_make_state(completed=list(prereqs)))

        ls = get_learner_status(_make_state(completed=list(prereqs)))
        if ls.current_module == target:
            commands = [h.command for h in hints]
            assert any("--dry-run" in c for c in commands)
