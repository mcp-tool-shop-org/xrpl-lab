"""Module linter — validate modules at author time."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .modules import parse_module
from .registry import PayloadError, PayloadSchema, is_registered, resolve


@dataclass
class LintIssue:
    """A single lint finding."""

    level: str  # "error" | "warning"
    module: str  # module file or id
    location: str  # e.g., "frontmatter", "step 3", "action ensure_wallet"
    message: str

    def __str__(self) -> str:
        tag = "ERROR" if self.level == "error" else "WARN"
        return f"[{tag}] {self.module}: {self.location} — {self.message}"


@dataclass
class LintResult:
    """Aggregate lint result for one or more modules."""

    issues: list[LintIssue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(i.level == "error" for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.level == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.level == "warning")

    def to_json(self) -> str:
        return json.dumps(
            {
                "passed": self.passed,
                "errors": self.error_count,
                "warnings": self.warning_count,
                "issues": [
                    {
                        "level": i.level,
                        "module": i.module,
                        "location": i.location,
                        "message": i.message,
                    }
                    for i in self.issues
                ],
            },
            indent=2,
        )


def lint_module_text(text: str, filename: str = "<unknown>") -> list[LintIssue]:
    """Lint a single module from its raw text. Returns a list of issues."""
    # Import handlers to ensure registry is populated
    import xrpl_lab.handlers  # noqa: F401

    issues: list[LintIssue] = []

    # 1. Parse frontmatter
    try:
        mod = parse_module(text)
    except ValueError as exc:
        issues.append(LintIssue(
            level="error",
            module=filename,
            location="frontmatter",
            message=str(exc),
        ))
        return issues  # Can't continue without a valid parse

    module_name = mod.id or filename

    # 2. Validate frontmatter fields
    if not mod.title.strip():
        issues.append(LintIssue(
            level="error",
            module=module_name,
            location="frontmatter",
            message="Empty title",
        ))

    if mod.level not in ("beginner", "intermediate", "advanced"):
        issues.append(LintIssue(
            level="warning",
            module=module_name,
            location="frontmatter",
            message=f"Unusual level '{mod.level}' (expected beginner/intermediate/advanced)",
        ))

    # 3. Validate actions against registry
    has_amm = False
    for i, step in enumerate(mod.steps, 1):
        if not step.action:
            continue

        step_label = f"step {i}"

        if not is_registered(step.action):
            issues.append(LintIssue(
                level="error",
                module=module_name,
                location=f"{step_label}, action '{step.action}'",
                message=f"Unknown action '{step.action}'",
            ))
            continue

        # Track AMM usage for dry_run_only check
        if step.action in ("ensure_amm_pair", "amm_deposit", "amm_withdraw"):
            has_amm = True

        # 4. Validate payload against schema
        action_def = resolve(step.action)
        if action_def.payload_fields:
            schema = PayloadSchema(fields=tuple(action_def.payload_fields))
            try:
                schema.validate(step.action_args)
            except PayloadError as exc:
                issues.append(LintIssue(
                    level="error",
                    module=module_name,
                    location=f"{step_label}, action '{step.action}', field '{exc.field}'",
                    message=str(exc),
                ))

    # 5. dry_run_only labeling check
    if has_amm and not mod.dry_run_only:
        issues.append(LintIssue(
            level="warning",
            module=module_name,
            location="frontmatter",
            message="Module uses AMM actions but is not marked dry_run_only: true",
        ))

    if mod.dry_run_only and not has_amm:
        issues.append(LintIssue(
            level="warning",
            module=module_name,
            location="frontmatter",
            message="Module is marked dry_run_only but has no AMM actions",
        ))

    return issues


def lint_module_file(path: Path) -> list[LintIssue]:
    """Lint a single module file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [LintIssue(
            level="error",
            module=str(path),
            location="file",
            message=f"Cannot read file: {exc}",
        )]
    return lint_module_text(text, filename=path.name)


def lint_all_modules(modules_dir: Path | None = None) -> LintResult:
    """Lint all .md files in the modules directory."""
    if modules_dir is None:
        # Default: try the package's bundled modules
        from importlib import resources

        try:
            modules_dir = Path(str(resources.files("xrpl_lab"))) / ".." / "modules"
            modules_dir = modules_dir.resolve()
        except (TypeError, FileNotFoundError):
            modules_dir = Path("modules")

    result = LintResult()
    if not modules_dir.is_dir():
        result.issues.append(LintIssue(
            level="error",
            module="<lint>",
            location="modules_dir",
            message=f"Modules directory not found: {modules_dir}",
        ))
        return result

    for md_file in sorted(modules_dir.glob("*.md")):
        result.issues.extend(lint_module_file(md_file))

    return result


def lint_curriculum(modules: dict | None = None) -> list[LintIssue]:
    """Validate curriculum structure across all modules.

    Checks track/summary presence, prerequisite validity, cycles, and mode.
    Returns issues as LintIssues (same type as per-module lint).
    """
    from .curriculum import build_graph
    from .modules import load_all_modules

    if modules is None:
        modules = load_all_modules()

    graph = build_graph(modules)
    curriculum_issues = graph.validate()

    return [
        LintIssue(
            level=ci.level,
            module=ci.module,
            location="curriculum",
            message=ci.message,
        )
        for ci in curriculum_issues
    ]
