"""Module linter — validate modules at author time."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .modules import _ACTION_RE, _STEP_RE, parse_module
from .registry import PayloadError, PayloadSchema, is_registered, resolve

# Explicit opt-out for ## Step headings that are intentionally actionless
# (literacy tables, reflection prompts). Checkpoints are exempt by kind;
# Steps need either one action or this marker — otherwise a forgotten or
# typo'd action comment (``<!-- action: set-trust-line -->`` fails
# ``_ACTION_RE`` because ``\w+`` rejects hyphens) ships as silent no-op.
_NARRATIVE_ONLY_RE = re.compile(r"<!--\s*narrative-only\s*-->", re.IGNORECASE)

# Kind-aware step heading matcher for the action-count lint. Same headings
# as ``_STEP_RE``, but keeps Step vs Checkpoint so zero-action rules can
# exempt narrative wrap-ups without rewriting the parser.
_STEP_HEADING_KIND_RE = re.compile(
    r"^##\s+(?P<kind>Step\s+\d+|Checkpoint)[.:]\s*(?P<title>.*)",
    re.MULTILINE,
)

# Tracks whose modules are sourced from the XRPL knowledge base (KB). A module
# on one of these tracks SHOULD carry a ``kb_source`` capability slug so its
# real testnet receipt self-describes which capability it proves (FT-ARCH-02 —
# the join that used to live only in the KB's external MODULE_CAPABILITY map).
# This is a WARNING, never an error: new modules (some authored by other agents
# in the same wave) lint green before the slug is backfilled, so a missing
# kb_source never blocks a release.
_KB_DERIVED_TRACKS = frozenset({"nfts", "tokens", "payments", "identity"})

# The xrpl-knowledge KB is an OPTIONAL external dependency — it lives in the
# ``readouts`` monorepo, NOT in this repo and NOT in CI — so its absence must
# never fail a lint run. Activation is explicit via the ``XRPL_LAB_KB_DB`` env
# var (used by tests and non-default checkouts).
#
# F-99b70cc9 (LOW): there used to be a hardcoded fallback path here
# (``E:\AI\readouts\xrpl-knowledge\xrpl.db``) specific to one contributor's
# local machine — harmless functionally (still guarded by ``path.is_file()``)
# but a packaging smell: baking a personal Windows path into published source
# also meant the cross-check silently never activated for any OTHER
# contributor/CI environment unless they happened to know the env var existed
# and discover the exact path to point it at. Dropped in favor of requiring
# ``XRPL_LAB_KB_DB`` to be set explicitly — no default, no rig-specific
# assumption. Contributors who have the KB checked out locally opt in by
# setting the env var; everyone else (including CI) gets a clean, honest
# ``None`` — same graceful degrade as before, just without the personal path.


def _resolve_kb_db() -> Path | None:
    """Resolve the KB db path from ``XRPL_LAB_KB_DB``, or ``None`` if unset."""
    import os

    override = os.environ.get("XRPL_LAB_KB_DB")
    return Path(override) if override else None


def load_kb_capability_slugs(db_path: Path | None = None) -> frozenset[str] | None:
    """Load the set of capability slugs from the xrpl-knowledge KB.

    Returns ``None`` when no KB db path is configured, or the configured path
    is absent/unreadable — the KB is an optional external dependency (not in
    this repo, not in CI, no default path), so its absence silently skips the
    cross-check rather than failing lint. When the KB is present, returns a
    (possibly empty) frozenset of ``capabilities.slug`` values. Opens the db
    read-only so a lint run never mutates the KB.
    """
    path = db_path or _resolve_kb_db()
    if path is None or not path.is_file():
        return None

    import sqlite3

    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = con.execute("SELECT slug FROM capabilities").fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        # Wrong schema, locked, or corrupt db — treat like an absent KB. The
        # cross-check is best-effort polish, never a hard dependency.
        return None

    return frozenset(r[0] for r in rows if r[0])


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


def lint_module_text(
    text: str,
    filename: str = "<unknown>",
    kb_slugs: frozenset[str] | None = None,
) -> list[LintIssue]:
    """Lint a single module from its raw text. Returns a list of issues.

    ``kb_slugs``, when supplied, is the set of capability slugs from the
    xrpl-knowledge KB (see :func:`load_kb_capability_slugs`). It enables the
    optional ``kb_source`` validity cross-check. When ``None`` (the default,
    and what happens whenever the KB db is absent — e.g. in CI), the
    cross-check is skipped entirely.
    """
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

    # 6. kb_source presence check for KB-derived tracks (FT-ARCH-02).
    # Warning-only: a missing slug doesn't fail lint (new modules backfill the
    # slug later), but it surfaces the gap so a KB-sourced module's receipt
    # eventually carries its capability identity end-to-end.
    if mod.track in _KB_DERIVED_TRACKS and not mod.kb_source.strip():
        issues.append(LintIssue(
            level="warning",
            module=module_name,
            location="frontmatter",
            message=(
                f"Module is on KB-derived track '{mod.track}' but has no "
                "kb_source capability slug — its receipt won't carry a "
                "capability identity for KB proof ingestion (backfill when ready)"
            ),
        ))

    # 7. kb_source VALIDITY cross-check (optional — only when the KB is present).
    # A kb_source that is present but does NOT exist in the KB's capabilities
    # table is a hard ERROR, by direct analogy to the "Unknown action" error
    # above: both reference an identifier absent from an authoritative table.
    # This is the gap that let three modules ship with hand-invented slugs:
    # the KB's ingest_proofs.py record() gates every proof insert on
    # ``SELECT 1 FROM capabilities WHERE slug=?``, so a fabricated/typo'd slug
    # passes lint but is SILENTLY DROPPED at ingest — the receipt never carries
    # its capability identity. Skipped when kb_slugs is None (KB db absent, as
    # in CI), so it never fails a release gate. A *missing* slug stays a
    # warning (deferred backfill, handled in §6); only a *wrong* slug errors.
    if kb_slugs is not None:
        slug = mod.kb_source.strip()
        if slug and slug not in kb_slugs:
            issues.append(LintIssue(
                level="error",
                module=module_name,
                location="frontmatter",
                message=(
                    f"Unknown kb_source capability '{slug}' — not in the "
                    "xrpl-knowledge KB capabilities table; a proof for this "
                    "module would be silently dropped at KB ingest "
                    "(ingest_proofs.py gates on SELECT 1 FROM capabilities "
                    "WHERE slug=?)"
                ),
            ))

    # 8. Action count per step heading (exactly one, unless exempt).
    #
    # ``parse_module`` binds a step to its action with ``_ACTION_RE.search()``,
    # which returns only the FIRST ``<!-- action: ... -->`` in a heading's body.
    # A second action comment under the same heading is therefore parsed away
    # and NEVER executes — silently, with no warning and no runtime error. That
    # is exactly how token_escrow_101 shipped a Step 6 carrying both
    # ``set_trust_line`` and ``issue_token``: only the trust line ran, the
    # holder never received the token the lesson promised, and the module's own
    # happy path failed ``tecUNFUNDED`` on every run.
    #
    # The curriculum convention is ONE action per heading (see clawback_101's
    # Step 11/12 split), so a second action is an authoring error, not a
    # supported form. Zero matches are the other face of the same defect: a
    # forgotten comment, or a typo that makes ``_ACTION_RE`` miss entirely
    # (e.g. hyphenated ``set-trust-line``), also runs as a silent no-op at
    # parse/runner time. ``## Checkpoint:`` wrap-ups are exempt; a ``## Step``
    # may opt out with ``<!-- narrative-only -->``.
    #
    # Scanned from ``raw_body`` rather than ``mod.steps`` — by the time parsing
    # is done the extra actions are already gone, so the parsed steps cannot
    # see the defect they are the symptom of. Parser stays first-match; this
    # lint does not change execute-all behavior.
    raw_parts = _STEP_RE.split(mod.raw_body)
    # Mirror parse_module's indexing so the reported step number matches the
    # one used everywhere else: an intro before the first heading occupies
    # step 1, shifting every heading down by one.
    heading_offset = 2 if raw_parts[0].strip() else 1
    headings = list(_STEP_HEADING_KIND_RE.finditer(mod.raw_body))
    for j, match in enumerate(headings):
        kind = match.group("kind")
        start = match.end()
        end = headings[j + 1].start() if j + 1 < len(headings) else len(mod.raw_body)
        step_body = mod.raw_body[start:end]
        found = _ACTION_RE.findall(step_body)
        step_label = f"step {j + heading_offset}"
        if len(found) > 1:
            names = [name for name, _args in found]
            dropped = ", ".join(f"'{n}'" for n in names[1:])
            issues.append(LintIssue(
                level="error",
                module=module_name,
                location=step_label,
                message=(
                    f"Step declares {len(names)} actions ({', '.join(names)}) "
                    f"but only the first ('{names[0]}') will run — {dropped} "
                    "would be silently dropped at parse time. Split each "
                    "action into its own '## Step N:' heading."
                ),
            ))
        elif len(found) == 0:
            if kind.startswith("Checkpoint"):
                continue
            if _NARRATIVE_ONLY_RE.search(step_body):
                continue
            issues.append(LintIssue(
                level="error",
                module=module_name,
                location=step_label,
                message=(
                    "Step declares no actions — the runner will print the "
                    "prose and move on with nothing executed. Add exactly one "
                    "<!-- action: ... --> comment, or mark the step "
                    "<!-- narrative-only --> if it is intentionally "
                    "actionless. (A typo'd action name that fails to match "
                    "the action comment regex also lands here.)"
                ),
            ))

    return issues


def lint_module_file(
    path: Path,
    kb_slugs: frozenset[str] | None = None,
) -> list[LintIssue]:
    """Lint a single module file.

    ``kb_slugs`` is forwarded to :func:`lint_module_text` to enable the
    optional ``kb_source`` validity cross-check (see that function).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [LintIssue(
            level="error",
            module=str(path),
            location="file",
            message=f"Cannot read file: {exc}",
        )]
    return lint_module_text(text, filename=path.name, kb_slugs=kb_slugs)


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

    # Load the KB capability slugs once (None when the KB db is absent) and
    # thread them through every module so the validity cross-check runs at
    # most one db query per lint, not one per file.
    kb_slugs = load_kb_capability_slugs()
    for md_file in sorted(modules_dir.glob("*.md")):
        result.issues.extend(lint_module_file(md_file, kb_slugs=kb_slugs))

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
