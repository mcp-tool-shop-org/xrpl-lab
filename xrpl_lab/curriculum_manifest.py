"""Single-source curriculum manifest — the ONE shape the docs derive from.

The product side (CLI ``list`` / ``status`` / dashboard / API) already derives
its view of the curriculum from :func:`load_all_modules` plus the
:mod:`curriculum` graph. The AUTHORED surfaces (README module table + counts,
the Starlight handbook tables/numbering, the marketing site-config rows + counts)
historically hand-encoded the same shape — and drifted every time a module or
track was added.

This module collapses that to a single function, :func:`build_manifest`, which
returns the canonical curriculum derived from the SAME product-side primitives:

* :func:`xrpl_lab.modules.load_all_modules` — the module set,
* :data:`xrpl_lab.curriculum.TRACKS` — the canonical track order,
* :meth:`xrpl_lab.curriculum.CurriculumGraph.canonical_order` — the canonical
  numbering (1..N) the CLI ``list`` command shows.

``scripts/gen_docs.py`` renders every authored surface from this manifest, and
``tests/test_docs_drift.py`` fails CI if any surface drifts from it. There is no
second place to update the curriculum's *shape* — only module front-matter and
:data:`curriculum.TRACKS`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from .curriculum import TRACKS, build_graph
from .modules import ModuleDef, load_all_modules

# Human-readable display labels for tracks (Title Case, with XLS spec hints
# where they sharpen the meaning). Used by the docs renderer for headings and
# the track legend. The KEYS must stay a superset of curriculum.TRACKS; a
# missing key falls back to ``track.title()`` so a brand-new track still
# renders rather than crashing the generator.
TRACK_LABELS: dict[str, str] = {
    "foundations": "Foundations",
    "nfts": "NFTs",
    "tokens": "Tokens",
    "payments": "Payments",
    "identity": "Identity",
    "dex": "DEX",
    "reserves": "Reserves",
    "audit": "Audit",
    "amm": "AMM",
    "capstone": "Capstone",
}

# One-line focus blurb per track (the legend humans read). Editorial, but it is
# keyed off the canonical track id, so it can never list a track that does not
# exist — the generator iterates TRACKS and looks each one up here.
TRACK_FOCUS: dict[str, str] = {
    "foundations": "wallet, payments, trust lines, error handling",
    "nfts": "NFT game assets: minting, marketplace settlement, dynamic NFTs (XLS-20)",
    "tokens": "Multi-Purpose Token (MPT) game-currency issuance & clawback (XLS-33)",
    "payments": "escrow & time-locked value",
    "identity": "Decentralized Identifiers (DID, XLS-40)",
    "dex": "offers, order books, market making, inventory management",
    "reserves": "account reserves, owner count, cleanup",
    "audit": "batch verification, audit reports",
    "amm": "automated market maker liquidity, DEX vs AMM comparison",
    "capstone": "compose skills across tracks into one game-economy build",
}


def track_label(track: str) -> str:
    """Display label for a track id (Title Case fallback for unknown tracks)."""
    return TRACK_LABELS.get(track, track.title())


@dataclass(frozen=True)
class ManifestModule:
    """One module in canonical order — the structured shape docs render from."""

    index: int  # 1..N position in canonical_order()
    id: str
    title: str
    track: str
    mode: str
    summary: str
    produces: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    kb_source: str = ""


@dataclass(frozen=True)
class TrackCount:
    """Per-track module tally, in canonical track order."""

    track: str
    label: str
    count: int


@dataclass(frozen=True)
class CurriculumManifest:
    """The canonical curriculum — single source for all authored surfaces."""

    modules: list[ManifestModule]
    track_counts: list[TrackCount]
    totals: dict[str, int]  # {"modules": N, "tracks": M}

    def to_dict(self) -> dict:
        """JSON-serializable view (for ``--json`` and curriculum.json)."""
        return {
            "modules": [asdict(m) for m in self.modules],
            "track_counts": [asdict(t) for t in self.track_counts],
            "totals": dict(self.totals),
        }

    def module_by_id(self, module_id: str) -> ManifestModule | None:
        for m in self.modules:
            if m.id == module_id:
                return m
        return None


def build_manifest(extra_dirs: list[Path] | None = None) -> CurriculumManifest:
    """Build the canonical curriculum manifest.

    Derived entirely from the product-side primitives — it reuses the
    curriculum graph's :meth:`canonical_order` for numbering rather than
    reimplementing any ordering, so the docs and the CLI ``list`` command are
    guaranteed to agree.
    """
    modules: dict[str, ModuleDef] = load_all_modules(extra_dirs=extra_dirs)
    graph = build_graph(modules)
    order = graph.canonical_order()

    manifest_modules: list[ManifestModule] = []
    for i, mid in enumerate(order, start=1):
        mod = modules[mid]
        manifest_modules.append(
            ManifestModule(
                index=i,
                id=mod.id,
                title=mod.title,
                track=mod.track,
                mode=mod.mode,
                summary=mod.summary,
                produces=list(mod.produces),
                requires=list(mod.requires),
                kb_source=mod.kb_source,
            )
        )

    # Per-track counts in canonical TRACKS order. A track with zero modules is
    # omitted (it has no rows to render); an "unknown" track that somehow has
    # modules is appended after the known ones so it is never silently dropped.
    by_track: dict[str, int] = {}
    for m in manifest_modules:
        by_track[m.track] = by_track.get(m.track, 0) + 1

    track_counts: list[TrackCount] = []
    seen: set[str] = set()
    for t in TRACKS:
        if by_track.get(t, 0) > 0:
            track_counts.append(TrackCount(track=t, label=track_label(t), count=by_track[t]))
            seen.add(t)
    for t in sorted(by_track):
        if t not in seen:
            track_counts.append(TrackCount(track=t, label=track_label(t), count=by_track[t]))

    totals = {"modules": len(manifest_modules), "tracks": len(track_counts)}

    return CurriculumManifest(
        modules=manifest_modules,
        track_counts=track_counts,
        totals=totals,
    )
