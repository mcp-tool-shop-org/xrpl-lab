"""Module system — load and parse markdown modules with YAML front-matter."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import yaml


@dataclass
class ModuleStep:
    """A single step in a module (rendered as a block of text)."""

    text: str
    action: str | None = None  # e.g., "ensure_wallet", "submit_payment"
    action_args: dict[str, str] = field(default_factory=dict)


@dataclass
class ModuleDef:
    """Parsed module definition."""

    id: str
    title: str
    time: str
    level: str
    requires: list[str]
    produces: list[str]
    checks: list[str]
    steps: list[ModuleStep]
    raw_body: str = ""
    order: int = 99
    dry_run_only: bool = False
    track: str = ""
    summary: str = ""
    mode: str = "testnet"

    @property
    def summary_line(self) -> str:
        return f"{self.title}  [{self.level}, ~{self.time}]"


# ── Front-matter regex ──────────────────────────────────────────────
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# ── Step markers ────────────────────────────────────────────────────
# Steps are delimited by "## Step N:" or "## Checkpoint:" headers
_STEP_RE = re.compile(r"^##\s+(?:Step\s+\d+[.:]\s*|Checkpoint[.:]\s*)(.*)", re.MULTILINE)

# Action markers inside steps: <!-- action: ensure_wallet -->
_ACTION_RE = re.compile(r"<!--\s*action:\s*(\w+)(?:\s+(.*?))?\s*-->")


def _parse_action_args(raw: str | None) -> dict[str, str]:
    """Parse 'key=value key2="value with spaces"' from action comment.

    Supports:
    - Unquoted values: ``currency=LAB``
    - Double-quoted values: ``memo="hello world"``
    - Single-quoted values: ``memo='hello world'``
    """
    if not raw:
        return {}
    args: dict[str, str] = {}
    i = 0
    n = len(raw)
    while i < n:
        # Skip whitespace
        while i < n and raw[i] in (" ", "\t"):
            i += 1
        if i >= n:
            break
        # Read key
        key_start = i
        while i < n and raw[i] not in ("=", " ", "\t"):
            i += 1
        key = raw[key_start:i].strip()
        if not key or i >= n or raw[i] != "=":
            i += 1
            continue
        i += 1  # skip '='
        if i >= n:
            args[key] = ""
            break
        # Read value
        if raw[i] in ('"', "'"):
            quote = raw[i]
            i += 1
            val_start = i
            while i < n and raw[i] != quote:
                i += 1
            args[key] = raw[val_start:i]
            if i < n:
                i += 1  # skip closing quote
        else:
            val_start = i
            while i < n and raw[i] not in (" ", "\t"):
                i += 1
            args[key] = raw[val_start:i]
    return args


def parse_module(text: str) -> ModuleDef:
    """Parse a module markdown file into a ModuleDef."""
    fm_match = _FRONTMATTER_RE.match(text)
    if not fm_match:
        raise ValueError("Module is missing YAML front-matter (---)")

    meta = yaml.safe_load(fm_match.group(1))
    body = text[fm_match.end() :]

    required_keys = {"id", "title", "time", "level", "track", "summary"}
    missing = required_keys - set(meta.keys())
    if missing:
        raise ValueError(f"Module front-matter missing keys: {', '.join(sorted(missing))}")

    # Parse steps
    steps: list[ModuleStep] = []
    parts = _STEP_RE.split(body)

    # parts[0] is intro text before first step header
    # Then alternating: header_text, body_text, header_text, body_text...
    if parts[0].strip():
        steps.append(ModuleStep(text=parts[0].strip()))

    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        step_body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        full_text = f"**{header}**\n\n{step_body}" if header else step_body

        action = None
        action_args: dict[str, str] = {}
        action_match = _ACTION_RE.search(step_body)
        if action_match:
            action = action_match.group(1)
            action_args = _parse_action_args(action_match.group(2))

        steps.append(ModuleStep(text=full_text, action=action, action_args=action_args))

    # Derive mode from explicit field or dry_run_only flag
    explicit_mode = meta.get("mode", "")
    dry_run_only = bool(meta.get("dry_run_only", False))
    if explicit_mode:
        mode = explicit_mode
        dry_run_only = mode == "dry-run"
    elif dry_run_only:
        mode = "dry-run"
    else:
        mode = "testnet"

    return ModuleDef(
        id=meta["id"],
        title=meta["title"],
        time=str(meta.get("time", "?")),
        level=meta.get("level", "beginner"),
        requires=meta.get("requires", []) or [],
        produces=meta.get("produces", []) or [],
        checks=meta.get("checks", []) or [],
        steps=steps,
        raw_body=body,
        order=int(meta.get("order", 99)),
        dry_run_only=dry_run_only,
        track=meta.get("track", ""),
        summary=meta.get("summary", ""),
        mode=mode,
    )


def _builtin_modules_dir() -> Path:
    """Path to the bundled modules/ directory."""
    # PyInstaller frozen binary: modules are bundled next to the executable
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "modules"
    ref = resources.files("xrpl_lab").joinpath("../modules")
    # resources.files returns a Traversable; for our case it's always a Path
    return Path(str(ref))


def render_module_skeleton(
    *,
    module_id: str,
    track: str,
    title: str,
    time: str,
    requires: list[str] | None = None,
    level: str = "beginner",
    mode: str = "testnet",
) -> str:
    """Render a lint-passing module skeleton for the scaffolder.

    Generates a markdown body with valid frontmatter, three numbered
    step sections, and action comment hints. The output passes
    ``xrpl-lab lint`` immediately so contributors get a green
    starting point and edit forward.

    The summary is derived from the title — contributors should
    rewrite it before publishing, but a real-string default keeps
    the lint pass clean.

    F-BACKEND-FT-006 (community contribution path; pairs with the
    CI/Docs CONTRIBUTING.md from the parallel commit).
    """
    requires_yaml = (
        "requires: []"
        if not requires
        else "requires:\n" + "\n".join(f"  - {r}" for r in requires)
    )

    # produces + checks: minimal lint-clean placeholders. Authors edit.
    frontmatter = (
        "---\n"
        f"id: {module_id}\n"
        f"title: {title}\n"
        f"track: {track}\n"
        f"summary: TODO — one-line summary of what the learner will do.\n"
        f"time: {time}\n"
        f"level: {level}\n"
        f"mode: {mode}\n"
        f"{requires_yaml}\n"
        "produces:\n"
        "  - txid\n"
        "  - report\n"
        "checks:\n"
        "  - \"TODO: first verifiable check\"\n"
        "  - \"TODO: second verifiable check\"\n"
        "---\n"
    )

    body = (
        "\n"
        f"<!-- TODO: 1-2 sentence intro for '{title}'. Tell the learner\n"
        f"     what they'll learn and why this module matters. -->\n"
        "\n"
        "## Step 1: Ensure your wallet is ready\n"
        "\n"
        "<!-- TODO: explain what this step accomplishes. -->\n"
        "\n"
        "<!-- action: ensure_wallet -->\n"
        "\n"
        "## Step 2: Do the core thing this module teaches\n"
        "\n"
        "<!-- TODO: walk through the substantive operation.\n"
        "     Available actions you can drop in (replace this comment\n"
        "     with one of the action lines below):\n"
        "       <!-- action: ensure_funded -->\n"
        "       <!-- action: submit_payment destination=ADDRESS amount=10 -->\n"
        "       <!-- action: set_trust_line currency=LAB limit=1000 -->\n"
        "     Reference the linter (xrpl-lab lint) for the canonical\n"
        "     payload schema of each registered action. -->\n"
        "\n"
        "## Step 3: Verify and reflect\n"
        "\n"
        "<!-- TODO: have the learner inspect what just happened.\n"
        "     A good closing step turns this module's outputs into\n"
        "     evidence the learner can read on the explorer. -->\n"
        "\n"
        "## Checkpoint: You did it\n"
        "\n"
        "<!-- TODO: summarize what the learner now knows + name the\n"
        "     next module to flow into. -->\n"
    )

    return frontmatter + body


def load_all_modules(extra_dirs: list[Path] | None = None) -> dict[str, ModuleDef]:
    """Load all modules from built-in + optional extra directories.

    Modules are sorted by (order, id) so the returned dict preserves
    the intended curriculum sequence.
    """
    modules: dict[str, ModuleDef] = {}

    dirs = [_builtin_modules_dir()]
    if extra_dirs:
        dirs.extend(extra_dirs)

    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.md")):
            try:
                mod = parse_module(f.read_text(encoding="utf-8"))
                modules[mod.id] = mod
            except (ValueError, yaml.YAMLError) as e:
                print(f"Warning: skipping malformed module {f.name}: {e}", file=sys.stderr)
                continue

    # Sort by (order, id) so the dict iteration order matches curriculum
    sorted_items = sorted(modules.items(), key=lambda kv: (kv[1].order, kv[0]))
    return dict(sorted_items)
