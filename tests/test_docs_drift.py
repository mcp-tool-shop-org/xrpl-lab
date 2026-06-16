"""Curriculum drift gate — the authored surfaces MUST match the manifest.

The curriculum's *shape* (module list, ordering/numbering, tracks, counts) is
single-sourced in :func:`xrpl_lab.curriculum_manifest.build_manifest`, and
``scripts/gen_docs.py`` renders it into the README, the Starlight handbook, and
the marketing ``site/src/data/curriculum.json``. These tests fail CI if any of
those surfaces drifts from the manifest — so adding a module/track and
forgetting to regenerate is caught, not shipped.

Scope discipline (deliberate): the assertions compare ONLY the *generated*
blocks fenced by ``BEGIN/END curriculum:auto`` markers — the structured data
(id/title/track/mode/index ordering/prerequisites/produces/counts). Editorial
prose OUTSIDE the fences (the README badges/translation nav, the site taglines,
the handbook narrative, any human-authored "what you learn / what you prove"
columns) is never read here and remains human-owned.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from xrpl_lab.curriculum_manifest import build_manifest

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_gen_docs():
    """Import scripts/gen_docs.py as a module (it lives outside the package)."""
    path = _REPO_ROOT / "scripts" / "gen_docs.py"
    spec = importlib.util.spec_from_file_location("gen_docs", path)
    assert spec and spec.loader, "could not load scripts/gen_docs.py"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gen_docs = _load_gen_docs()


def _extract_block(text: str, region: str) -> str:
    """Return the on-disk content between a region's BEGIN/END markers.

    The note line and surrounding blank lines are stripped so the comparison is
    against the structured body only — matching what the renderers produce.
    """
    begin = re.escape(gen_docs._md_begin(region))
    end = re.escape(gen_docs._md_end(region))
    m = re.search(begin + r"\n(.*?)\n" + end, text, re.DOTALL)
    assert m, f"region {region!r} markers not found on disk"
    body = m.group(1)
    # Drop the generated-by note line (it is constant boilerplate).
    lines = [ln for ln in body.splitlines() if gen_docs._NOTE not in ln]
    return "\n".join(lines).strip()


def _expected(render_fn) -> str:
    """Render a block from the live manifest and normalize like _extract_block."""
    manifest = build_manifest()
    return render_fn(manifest).strip()


# ── README ───────────────────────────────────────────────────────────


def test_readme_intro_matches_manifest():
    text = gen_docs.README.read_text(encoding="utf-8")
    assert _extract_block(text, "readme-intro") == _expected(gen_docs.render_readme_intro)


def test_readme_table_matches_manifest():
    text = gen_docs.README.read_text(encoding="utf-8")
    assert _extract_block(text, "readme-table") == _expected(gen_docs.render_readme_table)


def test_readme_tracks_matches_manifest():
    text = gen_docs.README.read_text(encoding="utf-8")
    assert _extract_block(text, "readme-tracks") == _expected(gen_docs.render_readme_tracks)


# ── Handbook: modules.md ──────────────────────────────────────────────


def test_handbook_intro_matches_manifest():
    text = gen_docs.HANDBOOK_MODULES.read_text(encoding="utf-8")
    assert _extract_block(text, "handbook-intro") == _expected(gen_docs.render_handbook_intro)


def test_handbook_tracks_table_matches_manifest():
    text = gen_docs.HANDBOOK_MODULES.read_text(encoding="utf-8")
    assert _extract_block(text, "handbook-tracks-table") == _expected(
        gen_docs.render_handbook_tracks_table
    )


def test_handbook_per_track_matches_manifest():
    text = gen_docs.HANDBOOK_MODULES.read_text(encoding="utf-8")
    assert _extract_block(text, "handbook-per-track") == _expected(
        gen_docs.render_handbook_per_track
    )


# ── Handbook: index.md + getting-started.md ───────────────────────────


def test_handbook_index_count_matches_manifest():
    text = gen_docs.HANDBOOK_INDEX.read_text(encoding="utf-8")
    assert _extract_block(text, "index-count") == _expected(gen_docs.render_index_count)


def test_getting_started_tracks_matches_manifest():
    text = gen_docs.HANDBOOK_GETTING_STARTED.read_text(encoding="utf-8")
    assert _extract_block(text, "getting-started-tracks") == _expected(
        gen_docs.render_getting_started_tracks
    )


# ── Site: curriculum.json ─────────────────────────────────────────────


def test_curriculum_json_matches_manifest():
    on_disk = gen_docs.CURRICULUM_JSON.read_text(encoding="utf-8")
    expected = gen_docs.render_curriculum_json(build_manifest())
    assert on_disk == expected


def test_curriculum_json_rows_are_string_lists():
    """SiteConfig DataTableSectionDef.rows is string[][] — keep the type valid."""
    data = json.loads(gen_docs.CURRICULUM_JSON.read_text(encoding="utf-8"))
    assert isinstance(data["rows"], list)
    for row in data["rows"]:
        assert isinstance(row, list)
        assert all(isinstance(cell, str) for cell in row)
        assert len(row) == len(data["columns"])


# ── Structured invariants (defense-in-depth) ──────────────────────────


def test_counts_consistent_across_surfaces():
    """The module/track counts the manifest reports must literally appear in
    every surface's generated block — no hand-typed number can drift."""
    manifest = build_manifest()
    n_modules = manifest.totals["modules"]
    counts_sentence = gen_docs.counts_sentence(manifest)

    # The canonical counts sentence appears in README intro + handbook intro.
    readme = _extract_block(
        gen_docs.README.read_text(encoding="utf-8"), "readme-intro"
    )
    handbook = _extract_block(
        gen_docs.HANDBOOK_MODULES.read_text(encoding="utf-8"), "handbook-intro"
    )
    assert counts_sentence.lower() in handbook.lower()
    assert str(n_modules) in readme

    # curriculum.json carries the machine-readable counts the site consumes.
    data = json.loads(gen_docs.CURRICULUM_JSON.read_text(encoding="utf-8"))
    assert data["moduleCount"] == n_modules
    assert data["trackCount"] == manifest.totals["tracks"]
    assert data["countsSentence"] == counts_sentence


def test_manifest_module_count_matches_module_files():
    """The manifest must cover every module file on disk (no silent drop)."""
    module_files = sorted((_REPO_ROOT / "modules").glob("*.md"))
    manifest = build_manifest()
    assert len(manifest.modules) == len(module_files)
    file_ids = {p.stem for p in module_files}
    manifest_ids = {m.id for m in manifest.modules}
    assert manifest_ids == file_ids


def test_readme_table_row_ordering_matches_canonical_order():
    """Row order in the README table is the canonical_order() numbering 1..N."""
    manifest = build_manifest()
    table = _extract_block(
        gen_docs.README.read_text(encoding="utf-8"), "readme-table"
    )
    data_rows = [
        ln for ln in table.splitlines()
        if ln.startswith("|") and not ln.startswith("| #") and "---" not in ln
    ]
    assert len(data_rows) == len(manifest.modules)
    for expected_index, (row, mod) in enumerate(
        zip(data_rows, manifest.modules, strict=True), start=1
    ):
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert cells[0] == str(expected_index)  # # column
        assert cells[0] == str(mod.index)
        assert cells[1] == mod.title  # Module column
        assert cells[2] == mod.track  # Track column
        assert cells[3] == mod.mode  # Mode column


def test_surfaces_are_idempotent():
    """Re-rendering every surface yields exactly what is on disk (no diff).

    This is the strongest single check — it proves `python scripts/gen_docs.py`
    was run after the last curriculum change and that running it again is a
    no-op. Equivalent to `gen_docs.py --check` passing.
    """
    manifest = build_manifest()
    rendered = gen_docs.render_all(manifest)
    stale = [
        path.relative_to(_REPO_ROOT)
        for path, new_text in rendered.items()
        if not path.exists() or path.read_text(encoding="utf-8") != new_text
    ]
    assert not stale, (
        "Surfaces drifted from the manifest — run `python scripts/gen_docs.py`: "
        + ", ".join(str(p) for p in stale)
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
