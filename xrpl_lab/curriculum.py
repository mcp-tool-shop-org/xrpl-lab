"""Curriculum graph — track order, prerequisites, and progression truth."""

from __future__ import annotations

from dataclasses import dataclass, field

from .modules import ModuleDef

# Canonical tracks in display order.
TRACKS = ("foundations", "dex", "reserves", "audit", "amm")

# Canonical levels in progression order.
LEVELS = ("beginner", "intermediate", "advanced")

VALID_MODES = ("testnet", "dry-run")


@dataclass
class CurriculumIssue:
    """A problem found in curriculum structure."""

    level: str  # "error" | "warning"
    module: str
    message: str

    def __str__(self) -> str:
        tag = "ERROR" if self.level == "error" else "WARN"
        return f"[{tag}] {self.module}: {self.message}"


@dataclass
class CurriculumGraph:
    """Directed graph of modules with prerequisite edges."""

    modules: dict[str, ModuleDef]
    _children: dict[str, list[str]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        # Build adjacency: parent → children
        self._children = {mid: [] for mid in self.modules}
        for mid, mod in self.modules.items():
            for req in mod.requires:
                if req in self._children:
                    self._children[req].append(mid)

    # ── Queries ──────────────────────────────────────────────────────

    def prerequisites(self, module_id: str) -> list[str]:
        """Direct prerequisites for a module."""
        mod = self.modules.get(module_id)
        return list(mod.requires) if mod else []

    def all_prerequisites(self, module_id: str) -> set[str]:
        """Transitive closure of prerequisites (no cycles assumed)."""
        visited: set[str] = set()
        stack = list(self.prerequisites(module_id))
        while stack:
            mid = stack.pop()
            if mid in visited:
                continue
            visited.add(mid)
            stack.extend(self.prerequisites(mid))
        return visited

    def is_reachable(self, module_id: str) -> bool:
        """True if all transitive prerequisites exist in the graph."""
        try:
            for req in self.all_prerequisites(module_id):
                if req not in self.modules:
                    return False
        except RecursionError:
            return False
        return True

    def roots(self) -> list[str]:
        """Modules with no prerequisites (entry points)."""
        return [mid for mid, mod in self.modules.items() if not mod.requires]

    def orphans(self) -> list[str]:
        """Modules that reference a prerequisite not in the graph."""
        result = []
        for mid, mod in self.modules.items():
            for req in mod.requires:
                if req not in self.modules:
                    result.append(mid)
                    break
        return result

    def find_cycles(self) -> list[list[str]]:
        """Detect prerequisite cycles. Returns a list of cycle paths."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {mid: WHITE for mid in self.modules}
        path: list[str] = []
        cycles: list[list[str]] = []

        def dfs(mid: str) -> None:
            color[mid] = GRAY
            path.append(mid)
            for req in self.modules[mid].requires:
                if req not in color:
                    continue
                if color[req] == GRAY:
                    # Found a cycle — extract it
                    cycle_start = path.index(req)
                    cycles.append(path[cycle_start:] + [req])
                elif color[req] == WHITE:
                    dfs(req)
            path.pop()
            color[mid] = BLACK

        for mid in self.modules:
            if color[mid] == WHITE:
                dfs(mid)

        return cycles

    def canonical_order(self) -> list[str]:
        """Topological sort respecting (track order, module order, id).

        Returns module IDs in the order they should be presented.
        """
        track_rank = {t: i for i, t in enumerate(TRACKS)}

        def sort_key(mid: str) -> tuple:
            mod = self.modules[mid]
            return (track_rank.get(mod.track, 99), mod.order, mid)

        # Kahn's algorithm with priority
        in_degree: dict[str, int] = {mid: 0 for mid in self.modules}
        for mod in self.modules.values():
            for req in mod.requires:
                if req in in_degree:
                    in_degree[req]  # just ensure it exists
                    in_degree[mod.id] = in_degree.get(mod.id, 0)  # no-op

        # Actually compute in-degrees from requires (reversed edges)
        in_degree = {mid: 0 for mid in self.modules}
        for mod in self.modules.values():
            for req in mod.requires:
                if req in self.modules:
                    in_degree[mod.id] += 1

        ready = sorted(
            [mid for mid, deg in in_degree.items() if deg == 0],
            key=sort_key,
        )
        result: list[str] = []

        while ready:
            mid = ready.pop(0)
            result.append(mid)
            for child in sorted(self._children.get(mid, []), key=sort_key):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    ready.append(child)
            ready.sort(key=sort_key)

        return result

    def next_module(self, completed: set[str]) -> str | None:
        """Deterministic next valid module given completed set."""
        for mid in self.canonical_order():
            if mid in completed:
                continue
            mod = self.modules[mid]
            # All prerequisites must be completed
            if all(req in completed for req in mod.requires):
                return mid
        return None

    # ── Validation ───────────────────────────────────────────────────

    def validate(self) -> list[CurriculumIssue]:
        """Validate the entire curriculum graph. Returns issues."""
        issues: list[CurriculumIssue] = []

        all_ids = set(self.modules.keys())

        for mid, mod in self.modules.items():
            # Missing track
            if not mod.track:
                issues.append(CurriculumIssue(
                    level="error", module=mid,
                    message="Missing 'track' in frontmatter",
                ))
            elif mod.track not in TRACKS:
                issues.append(CurriculumIssue(
                    level="warning", module=mid,
                    message=f"Unknown track '{mod.track}' (expected: {', '.join(TRACKS)})",
                ))

            # Missing summary
            if not mod.summary:
                issues.append(CurriculumIssue(
                    level="error", module=mid,
                    message="Missing 'summary' in frontmatter",
                ))

            # Invalid level
            if mod.level not in LEVELS:
                issues.append(CurriculumIssue(
                    level="warning", module=mid,
                    message=f"Unknown level '{mod.level}' (expected: {', '.join(LEVELS)})",
                ))

            # Invalid mode
            if mod.mode not in VALID_MODES:
                issues.append(CurriculumIssue(
                    level="error", module=mid,
                    message=f"Invalid mode '{mod.mode}' (expected: {', '.join(VALID_MODES)})",
                ))

            # Prerequisites reference valid modules
            for req in mod.requires:
                if req not in all_ids:
                    issues.append(CurriculumIssue(
                        level="error", module=mid,
                        message=f"Prerequisite '{req}' not found in module set",
                    ))

        # Duplicate IDs (shouldn't happen with dict, but check load-time)
        # Cycles
        cycles = self.find_cycles()
        for cycle in cycles:
            issues.append(CurriculumIssue(
                level="error",
                module=cycle[0],
                message=f"Prerequisite cycle: {' → '.join(cycle)}",
            ))

        # Orphans (modules whose prereqs point outside the graph)
        # Already covered by "not found" above

        return issues


def build_graph(modules: dict[str, ModuleDef]) -> CurriculumGraph:
    """Build a curriculum graph from loaded modules."""
    return CurriculumGraph(modules=modules)
