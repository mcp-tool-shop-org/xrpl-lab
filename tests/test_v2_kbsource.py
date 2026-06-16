"""Tests for the kb_source capability binding (FT-ARCH-02).

THE GAP this closes: the "module → which XRPL capability it teaches" join used
to live ONLY in the KB's external ``ingest_proofs.py`` MODULE_CAPABILITY dict,
which drifted the moment a new KB-sourced module shipped. Moving the binding
INTO the curriculum (``kb_source`` frontmatter → ModuleDef → proof pack) lets a
learner's real testnet receipt carry its capability identity end-to-end, so the
KB can ingest ANY future module's proofs with zero script edits.

Coverage:
  (a) the 4 shipped KB-sourced modules parse with their expected kb_source;
  (b) a proof pack for a completed KB-sourced module carries kb_source in its
      completed-module entry;
  (c) the pack's SHA-256 still verifies with the new field present (round-trip);
  (d) NO secret leaks into the pack (sentinel-seed scan, mirrors
      test_reporting.py::TestProofPack::test_no_secrets);
  (e) the linter WARNS (never errors) on a KB-track module missing kb_source,
      and does NOT warn when present.
"""

from __future__ import annotations

import json

import pytest

from xrpl_lab.linter import (
    lint_module_text,
    load_kb_capability_slugs,
)
from xrpl_lab.modules import load_all_modules
from xrpl_lab.reporting import generate_proof_pack, verify_proof_pack
from xrpl_lab.state import LabState

# The canonical capability slug each shipped KB-sourced module proves. These
# MUST match the KB's ingest_proofs.py MODULE_CAPABILITY dict exactly — that is
# the whole point of moving the binding into the curriculum (read 2026-06-16
# from E:/AI/readouts/xrpl-knowledge/scripts/ingest_proofs.py).
EXPECTED_KB_SOURCES = {
    "nft_minting_101": "nftokenmint",
    "mpt_issuance_101": "mpt-issuance-create-config",
    "escrow_101": "escrow-xrp",
    "did_101": "did-transactions",
}

# Same value-channel pin as test_reporting.py — assert this exact VALUE never
# lands in a shareable artifact (a key-name-only check is vacuous).
SENTINEL_SEED = "sEdSENTINELSEEDxxxxxxxxxxxxxx"

# A KB-derived track to exercise the linter's kb_source warning on a synthetic
# module (no AMM actions, so the only warning we expect is the kb_source one).
_KB_TRACK_MODULE_TEMPLATE = """\
---
id: synthetic_kb_module
title: Synthetic KB Module
track: {track}
summary: A synthetic module on a KB-derived track for linter tests.
time: 5 min
level: beginner
{kb_source_line}requires: []
produces:
  - txid
checks:
  - "Something happened"
---

Intro text.

## Step 1: Ensure wallet

<!-- action: ensure_wallet -->

## Checkpoint: Done

You did it.
"""


def _kb_track_module(track: str = "nfts", kb_source: str | None = None) -> str:
    line = f"kb_source: {kb_source}\n" if kb_source is not None else ""
    return _KB_TRACK_MODULE_TEMPLATE.format(track=track, kb_source_line=line)


# ── (a) The 4 shipped KB-sourced modules parse with expected kb_source ──


class TestKbSourceParsing:
    def test_shipped_modules_carry_expected_kb_source(self):
        """Each shipped KB-sourced module's frontmatter kb_source matches the
        KB's canonical capability slug. This is the binding that, once it
        rides on the receipt, lets the KB ingest the proof without editing
        its MODULE_CAPABILITY map."""
        mods = load_all_modules()
        for module_id, expected_slug in EXPECTED_KB_SOURCES.items():
            assert module_id in mods, f"missing shipped module {module_id}"
            assert mods[module_id].kb_source == expected_slug, (
                f"{module_id}: kb_source is {mods[module_id].kb_source!r}, "
                f"expected {expected_slug!r}"
            )

    def test_kb_source_defaults_empty_when_absent(self):
        """Backward-compatible: a module without kb_source defaults to ""."""
        from xrpl_lab.modules import parse_module

        text = _kb_track_module(track="foundations", kb_source=None)
        mod = parse_module(text)
        assert mod.kb_source == ""


# ── (b) Proof pack carries kb_source in completed-module entries ─────────


class TestProofPackKbSource:
    def test_completed_kb_module_entry_includes_kb_source(self):
        """A completed KB-sourced module's pack entry carries the resolved
        capability slug — the receipt now self-describes its capability."""
        state = LabState(network="testnet", wallet_address="rTESTKB")
        state.complete_module("nft_minting_101", txids=["TXNFT1"])
        state.record_tx("TXNFT1", "nft_minting_101", "testnet", True)

        pack = generate_proof_pack(state)
        entry = next(
            m for m in pack["completed_modules"]
            if m["module_id"] == "nft_minting_101"
        )
        assert entry["kb_source"] == "nftokenmint"

    def test_non_kb_module_entry_has_empty_kb_source(self):
        """A completed module with no kb_source (or absent from the
        curriculum) yields "" — never a crash, never a fabricated slug."""
        state = LabState(network="testnet", wallet_address="rTESTKB")
        state.complete_module("not_a_real_module_xyz", txids=["TXX"])
        state.record_tx("TXX", "not_a_real_module_xyz", "testnet", True)

        pack = generate_proof_pack(state)
        entry = next(
            m for m in pack["completed_modules"]
            if m["module_id"] == "not_a_real_module_xyz"
        )
        assert entry["kb_source"] == ""


# ── (c) SHA-256 round-trip still verifies with the new field present ─────


class TestProofPackIntegrity:
    def test_integrity_verifies_with_kb_source_present(self):
        """The new kb_source field is inside the hashed content — recomputing
        the SHA-256 over the pack (minus the hash field) must still match."""
        state = LabState(network="testnet", wallet_address="rTESTKB")
        state.complete_module("escrow_101", txids=["TXESC1"])
        state.record_tx("TXESC1", "escrow_101", "testnet", True)

        pack = generate_proof_pack(state)
        # The field is present...
        entry = pack["completed_modules"][0]
        assert entry["kb_source"] == "escrow-xrp"
        # ...and the embedded hash still verifies (round-trip).
        valid, msg = verify_proof_pack(pack)
        assert valid, f"integrity check failed: {msg}"

    def test_tampering_with_kb_source_breaks_hash(self):
        """Defensive: the kb_source field is part of the sealed content, so
        editing it after generation must invalidate the hash."""
        state = LabState(network="testnet", wallet_address="rTESTKB")
        state.complete_module("did_101", txids=["TXDID1"])
        state.record_tx("TXDID1", "did_101", "testnet", True)

        pack = generate_proof_pack(state)
        assert verify_proof_pack(pack)[0] is True
        pack["completed_modules"][0]["kb_source"] = "forged-capability"
        valid, _ = verify_proof_pack(pack)
        assert valid is False, "tampered kb_source should break integrity"


# ── (d) No secret leaks into the pack (sentinel-seed scan) ───────────────


class TestProofPackNoSecrets:
    def test_no_secrets_with_kb_source(self, tmp_path, monkeypatch):
        """Mirror test_reporting.py::TestProofPack::test_no_secrets — pin a
        known SENTINEL seed into the monkeypatched workspace's wallet.json and
        assert that VALUE never appears in the serialized pack, now that the
        pack also resolves modules (load_all_modules) at pack time."""
        ws = tmp_path / ".xrpl-lab"
        ws.mkdir()
        (ws / "wallet.json").write_text(
            json.dumps({"seed": SENTINEL_SEED}), encoding="utf-8",
        )
        monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws)

        state = LabState(network="testnet", wallet_address="rTESTKB")
        state.complete_module("mpt_issuance_101", txids=["TXMPT1"])
        state.record_tx("TXMPT1", "mpt_issuance_101", "testnet", True)

        pack = generate_proof_pack(state)
        text = json.dumps(pack)
        # The capability slug rides along...
        assert pack["completed_modules"][0]["kb_source"] == (
            "mpt-issuance-create-config"
        )
        # ...but the seed value never does.
        assert SENTINEL_SEED not in text, (
            "proof pack leaked the sentinel wallet seed value"
        )
        assert "seed" not in text.lower()
        assert "secret" not in text.lower()


# ── (e) Linter warns (not errors) on missing kb_source for KB tracks ─────


class TestLinterKbSource:
    def test_kb_track_missing_kb_source_warns_not_errors(self):
        """A module on a KB-derived track with no kb_source gets a WARNING,
        never an error — new modules lint green before backfill."""
        text = _kb_track_module(track="nfts", kb_source=None)
        issues = lint_module_text(text, "synthetic_kb_module.md")
        errors = [i for i in issues if i.level == "error"]
        warnings = [i for i in issues if i.level == "warning"]
        assert not errors, f"missing kb_source must not error: {errors}"
        assert any("kb_source" in w.message for w in warnings), (
            "expected a kb_source warning for a KB-track module without it"
        )

    def test_kb_track_with_kb_source_does_not_warn(self):
        """A KB-track module that carries a kb_source emits no kb_source
        warning."""
        text = _kb_track_module(track="nfts", kb_source="nftokenmint")
        issues = lint_module_text(text, "synthetic_kb_module.md")
        assert not [i for i in issues if i.level == "error"]
        assert not any("kb_source" in i.message for i in issues), (
            "a module WITH kb_source should not get the kb_source warning"
        )

    def test_non_kb_track_missing_kb_source_does_not_warn(self):
        """A module on a NON-KB track without kb_source is fine — the warning
        is scoped to KB-derived tracks only."""
        text = _kb_track_module(track="foundations", kb_source=None)
        issues = lint_module_text(text, "synthetic_module.md")
        assert not [i for i in issues if i.level == "error"]
        assert not any("kb_source" in i.message for i in issues)

    @pytest.mark.parametrize(
        "track", ["nfts", "tokens", "payments", "identity"],
    )
    def test_all_kb_derived_tracks_warn(self, track):
        """Every KB-derived track triggers the warning when kb_source is
        absent."""
        text = _kb_track_module(track=track, kb_source=None)
        issues = lint_module_text(text, "synthetic_kb_module.md")
        assert any("kb_source" in i.message for i in issues), (
            f"track {track!r} should warn on missing kb_source"
        )
        assert not [i for i in issues if i.level == "error"]


# ── (f) kb_source VALIDITY cross-check against the KB capabilities table ──
#
# THE GAP this closes: the presence check (§e above) only verifies a slug is
# THERE, not that it's REAL. Three modules shipped with hand-invented slugs
# (clawback-issuer-recall, nft-offer-trade-royalty, nft-modify-mutable-uri)
# that passed lint but do NOT exist in the KB capabilities table — they would
# have been silently dropped by ingest_proofs.py's record() gate
# (SELECT 1 FROM capabilities WHERE slug=?). The cross-check ERRORs on a
# present-but-nonexistent slug, by analogy to the "Unknown action" error, and
# degrades silently (skips) when the KB db is absent (as in CI).

# A synthetic slug set standing in for the KB capabilities table. Deterministic
# — these tests must NOT depend on the real KB being present on the host.
_FAKE_KB_SLUGS = frozenset({"nftokenmint", "escrow-xrp", "mpt-issuance-create-config"})


class TestLinterKbSourceValidity:
    def test_invalid_kb_source_errors_when_kb_present(self):
        """A kb_source absent from the KB capabilities table is an ERROR when
        the slug set is supplied — this is the bug that shipped."""
        text = _kb_track_module(track="nfts", kb_source="totally-invented-slug")
        issues = lint_module_text(
            text, "synthetic_kb_module.md", kb_slugs=_FAKE_KB_SLUGS,
        )
        errors = [i for i in issues if i.level == "error"]
        assert any(
            "totally-invented-slug" in e.message and "kb_source" in e.message
            for e in errors
        ), f"expected an Unknown kb_source error, got: {errors}"

    def test_valid_kb_source_no_error_when_kb_present(self):
        """A kb_source that IS in the slug set produces no error and no
        kb_source warning."""
        text = _kb_track_module(track="nfts", kb_source="nftokenmint")
        issues = lint_module_text(
            text, "synthetic_kb_module.md", kb_slugs=_FAKE_KB_SLUGS,
        )
        assert not [i for i in issues if i.level == "error"]
        assert not any("kb_source" in i.message for i in issues)

    def test_invalid_kb_source_skipped_when_kb_absent(self):
        """CORE graceful-degradation guarantee: with no slug set (the default,
        as when the KB db is absent in CI), an invalid slug is NOT flagged —
        the cross-check is skipped entirely, never failing a release gate."""
        text = _kb_track_module(track="nfts", kb_source="totally-invented-slug")
        issues = lint_module_text(text, "synthetic_kb_module.md")  # kb_slugs=None
        assert not [i for i in issues if i.level == "error"], (
            "kb_source validity must be skipped when the KB is absent"
        )

    def test_missing_kb_source_is_warning_not_validity_error(self):
        """A MISSING slug on a KB track stays a warning (deferred backfill),
        even with the slug set present — only a WRONG slug errors."""
        text = _kb_track_module(track="nfts", kb_source=None)
        issues = lint_module_text(
            text, "synthetic_kb_module.md", kb_slugs=_FAKE_KB_SLUGS,
        )
        assert not [i for i in issues if i.level == "error"]
        assert any(
            i.level == "warning" and "kb_source" in i.message for i in issues
        )

    def test_invalid_kb_source_errors_even_on_non_kb_track(self):
        """The validity check applies to ANY declared kb_source, not just
        KB-derived tracks: if a module provides a slug at all, it must be
        real (an invalid one would still be dropped at ingest)."""
        text = _kb_track_module(track="foundations", kb_source="not-a-real-slug")
        issues = lint_module_text(
            text, "synthetic_module.md", kb_slugs=_FAKE_KB_SLUGS,
        )
        assert any(
            i.level == "error" and "not-a-real-slug" in i.message for i in issues
        )


class TestKbSlugLoader:
    def test_loader_returns_none_when_db_absent(self, tmp_path):
        """An absent db path yields None (skip), never raises."""
        assert load_kb_capability_slugs(tmp_path / "does-not-exist.db") is None

    def test_loader_reads_slugs_from_temp_db(self, tmp_path):
        """A db with a capabilities table returns its slugs as a frozenset."""
        import sqlite3

        db = tmp_path / "xrpl.db"
        con = sqlite3.connect(db)
        con.execute(
            "CREATE TABLE capabilities (id INTEGER PRIMARY KEY, "
            "slug TEXT UNIQUE NOT NULL)"
        )
        con.executemany(
            "INSERT INTO capabilities(slug) VALUES (?)",
            [("nftokenmint",), ("escrow-xrp",)],
        )
        con.commit()
        con.close()

        slugs = load_kb_capability_slugs(db)
        assert slugs == frozenset({"nftokenmint", "escrow-xrp"})

    def test_loader_returns_none_on_wrong_schema(self, tmp_path):
        """A db that exists but lacks a capabilities table degrades to None
        (graceful), not an unhandled sqlite error."""
        import sqlite3

        db = tmp_path / "wrong.db"
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE unrelated (x INTEGER)")
        con.commit()
        con.close()

        assert load_kb_capability_slugs(db) is None

    def test_loader_honors_env_override(self, tmp_path, monkeypatch):
        """XRPL_LAB_KB_DB overrides the default path."""
        import sqlite3

        db = tmp_path / "override.db"
        con = sqlite3.connect(db)
        con.execute(
            "CREATE TABLE capabilities (id INTEGER PRIMARY KEY, "
            "slug TEXT UNIQUE NOT NULL)"
        )
        con.execute("INSERT INTO capabilities(slug) VALUES ('did-transactions')")
        con.commit()
        con.close()

        monkeypatch.setenv("XRPL_LAB_KB_DB", str(db))
        assert load_kb_capability_slugs() == frozenset({"did-transactions"})


# ── (g) Regression guard: real bundled modules vs the real KB (when present) ─
#
# This is the test that would have caught the shipped bug. It only runs on a
# host that has the xrpl-knowledge KB checked out (skipped in CI), and asserts
# that EVERY bundled module's kb_source is a real KB capability slug.
_REAL_KB_SLUGS = load_kb_capability_slugs()


@pytest.mark.skipif(
    _REAL_KB_SLUGS is None,
    reason="xrpl-knowledge KB db not present (external optional dependency)",
)
class TestBundledModulesAgainstRealKb:
    def test_every_bundled_kb_source_exists_in_kb(self):
        mods = load_all_modules()
        bad = {
            mid: m.kb_source
            for mid, m in mods.items()
            if m.kb_source and m.kb_source not in _REAL_KB_SLUGS
        }
        assert not bad, (
            "bundled modules carry kb_source slugs absent from the "
            f"xrpl-knowledge KB capabilities table: {bad}"
        )

    def test_shipped_expected_sources_are_real_kb_slugs(self):
        """The 4 originally-shipped KB-sourced modules' expected slugs are all
        real KB capabilities (sanity-checks EXPECTED_KB_SOURCES itself)."""
        missing = sorted(s for s in EXPECTED_KB_SOURCES.values() if s not in _REAL_KB_SLUGS)
        assert not missing, f"EXPECTED_KB_SOURCES has non-KB slugs: {missing}"
