"""Wave 7/8 curriculum — F-d1b778d3 / Advisor F-7c4e91a2.

Every module that calls ``create_issuer_wallet`` must teach load-and-reuse
in the lesson (not only via the handlers console hint): resume/re-run
reuses ``.xrpl-lab/issuer_wallet.json``; minting fresh orphans trust lines
and locks owner reserve. ``dex_literacy`` must not say the step
\"re-creates\" the issuer. Point learners/facilitators at
``account_hygiene`` for leftover-line cleanup.

Do not edit handlers.py — curriculum owns ``modules/**``.

Run in isolation:
    python -m pytest tests/test_w7_curriculum_issuer_reuse_prose.py -q --tb=short
"""

from __future__ import annotations

import re

from xrpl_lab.modules import load_all_modules

# Call-site enumeration: every shipped module with create_issuer_wallet.
# Keep sorted; drift fails the suite (new module must get the prose beat).
CREATE_ISSUER_WALLET_MODULES: frozenset[str] = frozenset(
    {
        "account_hygiene",
        "amm_liquidity_101",
        "clawback_101",
        "delivered_amount_101",
        "dex_inventory_guardrails",
        "dex_literacy",
        "dex_market_making_101",
        "dex_vs_amm_risk_literacy",
        "mpt_distribution_101",
        "reserves_101",
        "token_escrow_101",
        "token_freeze_101",
        "trust_line_failures",
        "trust_lines_101",
    }
)

REUSE_RE = re.compile(r"\breuse[sd]?\b", re.I)
ORPHAN_RE = re.compile(r"\borphan(?:s|ed)?\b", re.I)
ACCOUNT_HYGIENE_RE = re.compile(r"account_hygiene", re.I)
# dex_literacy previously taught the opposite of load-and-reuse.
RECREATE_RE = re.compile(r"re-?creates?", re.I)


def _create_issuer_sites() -> list[tuple[str, str]]:
    mods = load_all_modules()
    sites: list[tuple[str, str]] = []
    for mid, mod in sorted(mods.items()):
        for step in mod.steps:
            if step.action == "create_issuer_wallet":
                sites.append((mid, step.text))
    return sites


def test_create_issuer_wallet_call_sites_enumerated():
    """Call-site contract: every create_issuer_wallet module is listed."""
    found = {mid for mid, _ in _create_issuer_sites()}
    assert found == CREATE_ISSUER_WALLET_MODULES, (
        "create_issuer_wallet call-site set drifted.\n"
        f"  missing from enum: {sorted(found - CREATE_ISSUER_WALLET_MODULES)}\n"
        f"  stale enum entries: {sorted(CREATE_ISSUER_WALLET_MODULES - found)}"
    )
    assert len(found) == 14, f"expected 14 create_issuer_wallet modules, got {len(found)}"


def test_every_create_issuer_wallet_step_teaches_reuse_and_orphan():
    """RED gate: lesson prose must say reuse + orphan (complement handlers hint)."""
    failures: list[str] = []
    for mid, text in _create_issuer_sites():
        missing: list[str] = []
        if not REUSE_RE.search(text):
            missing.append("reuse")
        if not ORPHAN_RE.search(text):
            missing.append("orphan")
        if not ACCOUNT_HYGIENE_RE.search(text):
            missing.append("account_hygiene")
        if missing:
            failures.append(f"{mid}: missing {missing} in create_issuer_wallet step prose")
    assert not failures, (
        "F-d1b778d3: create_issuer_wallet steps must document load-and-reuse, "
        "orphan risk, and point at account_hygiene. Offenders:\n  - "
        + "\n  - ".join(failures)
    )


def test_dex_literacy_does_not_say_recreates_issuer():
    """F-d1b778d3 / F-7c4e91a2: fix the 're-creates' wording that teaches mint-fresh."""
    mod = load_all_modules()["dex_literacy"]
    step = next(s for s in mod.steps if s.action == "create_issuer_wallet")
    assert not RECREATE_RE.search(step.text), (
        "dex_literacy create_issuer_wallet step still says re-create(s); "
        "load-and-reuse must not be described as recreating the issuer. "
        f"Step text:\n{step.text}"
    )
