"""Tests for curriculum graph and progression truth (Phase 3B)."""

from __future__ import annotations

from xrpl_lab.curriculum import build_graph
from xrpl_lab.modules import ModuleDef, load_all_modules


def _mod(
    id: str,
    track: str = "foundations",
    level: str = "beginner",
    order: int = 1,
    requires: list[str] | None = None,
    summary: str = "Test summary.",
    mode: str = "testnet",
) -> ModuleDef:
    """Quick helper to build a minimal ModuleDef."""
    return ModuleDef(
        id=id,
        title=id.replace("_", " ").title(),
        time="5 min",
        level=level,
        requires=requires or [],
        produces=[],
        checks=[],
        steps=[],
        order=order,
        track=track,
        summary=summary,
        mode=mode,
    )


# ── Graph structure ──────────────────────────────────────────────────


class TestGraphBasics:
    def test_roots(self):
        mods = {
            "a": _mod("a"),
            "b": _mod("b", requires=["a"]),
        }
        g = build_graph(mods)
        assert g.roots() == ["a"]

    def test_prerequisites(self):
        mods = {
            "a": _mod("a"),
            "b": _mod("b", requires=["a"]),
        }
        g = build_graph(mods)
        assert g.prerequisites("b") == ["a"]
        assert g.prerequisites("a") == []

    def test_transitive_prerequisites(self):
        mods = {
            "a": _mod("a"),
            "b": _mod("b", requires=["a"]),
            "c": _mod("c", requires=["b"]),
        }
        g = build_graph(mods)
        assert g.all_prerequisites("c") == {"a", "b"}

    def test_orphan_detection(self):
        mods = {
            "a": _mod("a", requires=["nonexistent"]),
        }
        g = build_graph(mods)
        assert "a" in g.orphans()

    def test_no_orphans_in_valid_graph(self):
        mods = {
            "a": _mod("a"),
            "b": _mod("b", requires=["a"]),
        }
        g = build_graph(mods)
        assert g.orphans() == []


# ── Cycles ───────────────────────────────────────────────────────────


class TestCycles:
    def test_no_cycles_in_linear(self):
        mods = {
            "a": _mod("a"),
            "b": _mod("b", requires=["a"]),
            "c": _mod("c", requires=["b"]),
        }
        g = build_graph(mods)
        assert g.find_cycles() == []

    def test_simple_cycle_detected(self):
        mods = {
            "a": _mod("a", requires=["b"]),
            "b": _mod("b", requires=["a"]),
        }
        g = build_graph(mods)
        cycles = g.find_cycles()
        assert len(cycles) >= 1

    def test_self_cycle_detected(self):
        mods = {
            "a": _mod("a", requires=["a"]),
        }
        g = build_graph(mods)
        cycles = g.find_cycles()
        assert len(cycles) >= 1


# ── Canonical order ──────────────────────────────────────────────────


class TestCanonicalOrder:
    def test_respects_prerequisites(self):
        mods = {
            "a": _mod("a", order=1),
            "b": _mod("b", order=2, requires=["a"]),
            "c": _mod("c", order=3, requires=["b"]),
        }
        g = build_graph(mods)
        order = g.canonical_order()
        assert order.index("a") < order.index("b") < order.index("c")

    def test_respects_track_order(self):
        mods = {
            "dex_mod": _mod("dex_mod", track="dex", order=1),
            "found_mod": _mod("found_mod", track="foundations", order=1),
        }
        g = build_graph(mods)
        order = g.canonical_order()
        assert order.index("found_mod") < order.index("dex_mod")

    def test_all_modules_present(self):
        mods = {
            "a": _mod("a"),
            "b": _mod("b", requires=["a"]),
        }
        g = build_graph(mods)
        order = g.canonical_order()
        assert set(order) == {"a", "b"}


# ── Next module ──────────────────────────────────────────────────────


class TestNextModule:
    def test_first_module_when_empty(self):
        mods = {
            "a": _mod("a", order=1),
            "b": _mod("b", order=2, requires=["a"]),
        }
        g = build_graph(mods)
        assert g.next_module(set()) == "a"

    def test_second_module_after_first(self):
        mods = {
            "a": _mod("a", order=1),
            "b": _mod("b", order=2, requires=["a"]),
        }
        g = build_graph(mods)
        assert g.next_module({"a"}) == "b"

    def test_none_when_all_done(self):
        mods = {
            "a": _mod("a"),
        }
        g = build_graph(mods)
        assert g.next_module({"a"}) is None

    def test_skips_blocked_module(self):
        mods = {
            "a": _mod("a", order=1),
            "b": _mod("b", order=2, requires=["a"]),
            "c": _mod("c", order=3),  # no prereqs
        }
        g = build_graph(mods)
        # Nothing completed — a and c are both available, a comes first by order
        assert g.next_module(set()) == "a"
        # a not done, but c has no prereqs
        assert g.next_module({"c"}) == "a"

    def test_deterministic(self):
        """next_module returns the same result on repeated calls."""
        mods = {
            "a": _mod("a", order=1),
            "b": _mod("b", order=2),
        }
        g = build_graph(mods)
        results = {g.next_module(set()) for _ in range(10)}
        assert len(results) == 1


# ── Validation ───────────────────────────────────────────────────────


class TestValidation:
    def test_valid_graph_clean(self):
        mods = {
            "a": _mod("a", track="foundations", summary="Okay"),
            "b": _mod("b", track="dex", summary="Also okay", requires=["a"]),
        }
        g = build_graph(mods)
        issues = g.validate()
        errors = [i for i in issues if i.level == "error"]
        assert not errors

    def test_missing_track_is_error(self):
        mods = {"a": _mod("a", track="")}
        g = build_graph(mods)
        issues = g.validate()
        assert any("track" in i.message.lower() for i in issues if i.level == "error")

    def test_missing_summary_is_error(self):
        mods = {"a": _mod("a", summary="")}
        g = build_graph(mods)
        issues = g.validate()
        assert any("summary" in i.message.lower() for i in issues if i.level == "error")

    def test_bad_prerequisite_is_error(self):
        mods = {"a": _mod("a", requires=["nonexistent"])}
        g = build_graph(mods)
        issues = g.validate()
        assert any("nonexistent" in i.message for i in issues if i.level == "error")

    def test_invalid_mode_is_error(self):
        mods = {"a": _mod("a", mode="turbo")}
        g = build_graph(mods)
        issues = g.validate()
        assert any("mode" in i.message.lower() for i in issues if i.level == "error")

    def test_unknown_track_is_warning(self):
        mods = {"a": _mod("a", track="exotic")}
        g = build_graph(mods)
        issues = g.validate()
        assert any("track" in i.message.lower() for i in issues if i.level == "warning")

    def test_cycle_is_error(self):
        mods = {
            "a": _mod("a", requires=["b"]),
            "b": _mod("b", requires=["a"]),
        }
        g = build_graph(mods)
        issues = g.validate()
        assert any("cycle" in i.message.lower() for i in issues if i.level == "error")


# ── Real modules ─────────────────────────────────────────────────────


class TestRealCurriculum:
    def test_all_bundled_modules_valid(self):
        """The real curriculum should have zero errors."""
        modules = load_all_modules()
        g = build_graph(modules)
        issues = g.validate()
        errors = [i for i in issues if i.level == "error"]
        assert not errors, f"Curriculum errors: {errors}"

    def test_no_cycles_in_real_modules(self):
        modules = load_all_modules()
        g = build_graph(modules)
        assert g.find_cycles() == []

    def test_no_orphans_in_real_modules(self):
        modules = load_all_modules()
        g = build_graph(modules)
        assert g.orphans() == []

    def test_canonical_order_includes_all(self):
        modules = load_all_modules()
        g = build_graph(modules)
        order = g.canonical_order()
        assert set(order) == set(modules.keys())

    def test_next_module_is_deterministic(self):
        modules = load_all_modules()
        g = build_graph(modules)
        results = {g.next_module(set()) for _ in range(10)}
        assert len(results) == 1

    def test_first_module_has_no_prereqs(self):
        modules = load_all_modules()
        g = build_graph(modules)
        first = g.next_module(set())
        assert first is not None
        assert modules[first].requires == [] or all(
            r not in modules for r in modules[first].requires
        )
