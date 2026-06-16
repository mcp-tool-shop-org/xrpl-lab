"""v2.0.0 capstone tests (f3-capstone domain).

The capstone (``game_economy_capstone``, track 'capstone') is the culminating
module: it COMPOSES already-registered actions across tracks into one coherent
build — issue a game currency (MPT) → mint a tradeable game asset (NFT with a
royalty) → trade it to a second player → lock and release a reward in escrow →
audit the whole trail into a sealed proof. There is no new transport / handler /
action code; the capstone is a MODULE, and these tests pin that contract:

  (a) it lints + parses cleanly with track 'capstone' and its cross-track
      ``requires``;
  (b) the curriculum gates it — ``next_module`` does NOT offer it until its
      prerequisites are complete, and DOES once they are, with no new
      sequencing code;
  (c) every action it composes resolves in the action registry (it invents no
      new primitive);
  (d) completing it surfaces a ``capstone: true`` flag in the proof pack, and
      the pack's SHA-256 integrity still verifies.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from xrpl_lab.curriculum import TRACKS, build_graph
from xrpl_lab.linter import lint_module_file
from xrpl_lab.modules import load_all_modules, parse_module
from xrpl_lab.registry import is_registered
from xrpl_lab.reporting import (
    CAPSTONE_MODULE_ID,
    generate_proof_pack,
    verify_proof_pack,
)
from xrpl_lab.state import LabState

CAPSTONE_ID = "game_economy_capstone"
CAPSTONE_PREREQS = {
    "mpt_issuance_101",
    "nft_minting_101",
    "escrow_101",
    "receipt_audit",
}


def _capstone_path() -> Path:
    return Path(__file__).resolve().parent.parent / "modules" / f"{CAPSTONE_ID}.md"


@pytest.fixture
def modules() -> dict:
    return load_all_modules()


@pytest.fixture
def capstone(modules):
    mod = modules.get(CAPSTONE_ID)
    assert mod is not None, "capstone module did not load"
    return mod


# ════════════════════════════════════════════════════════════════════════
# (a) The capstone module lints + parses with track 'capstone' + its requires
# ════════════════════════════════════════════════════════════════════════


class TestCapstoneModuleParses:
    def test_capstone_id_matches_reporting_constant(self):
        # The proof-pack flag is derived from this exact id — keep them in sync.
        assert CAPSTONE_MODULE_ID == CAPSTONE_ID

    def test_module_file_exists(self):
        assert _capstone_path().is_file()

    def test_parses_with_capstone_track(self):
        mod = parse_module(_capstone_path().read_text(encoding="utf-8"))
        assert mod.id == CAPSTONE_ID
        assert mod.track == "capstone"
        assert mod.summary.strip()

    def test_capstone_track_registered_last(self):
        # Track must be known to the curriculum AND sort after every other
        # track (highest rank) so canonical_order places it at the end.
        assert "capstone" in TRACKS
        assert TRACKS[-1] == "capstone"

    def test_requires_the_economy_prereq_set(self, capstone):
        assert set(capstone.requires) == CAPSTONE_PREREQS

    def test_mode_is_honest(self, capstone):
        # The composed actions are testnet actions — the mode must say so.
        assert capstone.mode == "testnet"

    def test_lints_clean(self):
        issues = lint_module_file(_capstone_path())
        errors = [i for i in issues if i.level == "error"]
        assert not errors, f"capstone lint errors: {errors}"


# ════════════════════════════════════════════════════════════════════════
# (b) Curriculum gates the capstone on its prereqs — NO new sequencing code
# ════════════════════════════════════════════════════════════════════════


class TestCapstoneGating:
    def test_prereqs_all_exist(self, modules):
        for req in CAPSTONE_PREREQS:
            assert req in modules, f"capstone prereq {req!r} not in curriculum"

    def test_not_offered_before_prereqs_done(self, modules):
        """With nothing completed, the curriculum must never jump to the
        capstone — its prerequisite gate (the existing graph, no new code)
        keeps it out of reach."""
        g = build_graph(modules)
        assert g.next_module(set()) != CAPSTONE_ID

    def test_not_offered_with_only_some_prereqs(self, modules):
        """Partial prerequisites are not enough — the gate needs ALL of them."""
        g = build_graph(modules)
        # Complete everything EXCEPT one prereq (escrow_101).
        completed = set(modules.keys()) - {CAPSTONE_ID, "escrow_101"}
        nxt = g.next_module(completed)
        assert nxt != CAPSTONE_ID
        # The thing it offers instead is the missing prereq (or its chain).
        assert nxt is not None

    def test_offered_once_prereqs_complete(self, modules):
        """Complete every module except the capstone — the only thing left to
        offer is the capstone, and its prereqs are all satisfied."""
        g = build_graph(modules)
        completed = set(modules.keys()) - {CAPSTONE_ID}
        assert g.next_module(completed) == CAPSTONE_ID

    def test_capstone_is_last_in_canonical_order(self, modules):
        g = build_graph(modules)
        order = g.canonical_order()
        assert order[-1] == CAPSTONE_ID, (
            "capstone must sort last (highest track rank + high order)"
        )

    def test_real_curriculum_has_no_errors_with_capstone(self, modules):
        """Adding the capstone track + module must not introduce curriculum
        errors (unknown track, bad prereq, cycle, bad mode)."""
        g = build_graph(modules)
        errors = [i for i in g.validate() if i.level == "error"]
        assert not errors, f"curriculum errors: {errors}"


# ════════════════════════════════════════════════════════════════════════
# (c) The capstone composes ONLY registered actions (invents no primitive)
# ════════════════════════════════════════════════════════════════════════


class TestCapstoneComposesRegisteredActions:
    def test_every_action_marker_resolves(self, capstone):
        # Importing the linter/handlers populates the registry (lint_module_file
        # already triggered it, but assert independently here).
        import xrpl_lab.handlers  # noqa: F401

        actions = [s.action for s in capstone.steps if s.action]
        assert actions, "capstone has no action markers"
        for action in actions:
            assert is_registered(action), (
                f"capstone composes unregistered action {action!r} — the "
                "capstone must sequence EXISTING actions, not invent new ones"
            )

    def test_composes_the_economy_spine(self, capstone):
        """The capstone must actually span the economy: a currency, an asset,
        a trade, an escrow lifecycle, and an audit."""
        actions = {s.action for s in capstone.steps if s.action}
        spine = {
            "create_mpt_issuance",   # game currency
            "mint_nft",              # game asset
            "list_nft_sell_offer",   # marketplace listing
            "accept_nft_offer",      # atomic trade
            "create_escrow",         # reward lock
            "finish_escrow",         # reward release
            "run_audit",             # seal the proof
        }
        missing = spine - actions
        assert not missing, f"capstone is missing economy steps: {missing}"


# ════════════════════════════════════════════════════════════════════════
# (d) Completing the capstone surfaces the flag AND the pack still verifies
# ════════════════════════════════════════════════════════════════════════


def _state_without_capstone() -> LabState:
    state = LabState(network="testnet", wallet_address="rTEST123456789")
    state.complete_module("receipt_literacy", txids=["TX001"])
    state.record_tx("TX001", "receipt_literacy", "testnet", True)
    return state


def _state_with_capstone() -> LabState:
    state = _state_without_capstone()
    state.complete_module(CAPSTONE_ID, txids=["TXCAP"])
    state.record_tx("TXCAP", CAPSTONE_ID, "testnet", True)
    return state


class TestCapstoneProofFlag:
    def test_flag_absent_when_capstone_not_done(self):
        pack = generate_proof_pack(_state_without_capstone())
        assert pack["capstone"] is False

    def test_flag_present_when_capstone_done(self):
        pack = generate_proof_pack(_state_with_capstone())
        assert pack["capstone"] is True

    def test_pack_integrity_verifies_with_flag(self):
        """The flag is folded in BEFORE the SHA-256 — the pack still verifies."""
        pack = generate_proof_pack(_state_with_capstone())
        ok, msg = verify_proof_pack(pack)
        assert ok, f"capstone proof pack failed integrity check: {msg}"

    def test_tampering_with_flag_breaks_integrity(self):
        """Flipping the flag after sealing must break the hash — proving the
        flag is genuinely covered by the integrity check, not cosmetic."""
        pack = generate_proof_pack(_state_with_capstone())
        pack["capstone"] = False  # tamper
        ok, _ = verify_proof_pack(pack)
        assert not ok

    def test_flag_leaks_no_secret(self):
        # The flag is a derived boolean — the serialized pack carries no seed.
        import json

        pack = generate_proof_pack(_state_with_capstone())
        text = json.dumps(pack).lower()
        assert "seed" not in text
        assert "secret" not in text
