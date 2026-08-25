"""Wave 5 Stage B — curriculum checks: must not overclaim verify_* handlers.

F-305bb7e8: verify_reserve_change / verify_position_delta are informational
comparisons unless they carry expected_direction / expected_delta. checks:
bullets must not present their output as a confirmed fact.

F-839dcc62: reserves_101 must not claim owner-count decreased after removing
objects when the module never removes anything.
"""

from __future__ import annotations

import re

from xrpl_lab.modules import load_all_modules

VERIFY_ACTIONS = frozenset({"verify_reserve_change", "verify_position_delta"})
REMOVAL_ACTIONS = frozenset(
    {
        "cancel_offer",
        "remove_trust_line",
        "cancel_module_offers",
        "cancel_check",
        "finish_escrow",
        "amm_withdraw",
    }
)

# Absolute / confirmed-fact phrasing that an always-True comparison handler
# cannot prove. Observational rewrites must include an OBSERVED_MARKERS token.
ABSOLUTE_CHECK_PATTERNS = (
    re.compile(r"Funds NOT locked", re.I),
    re.compile(r"spendable balance is unchanged", re.I),
    re.compile(r"Owner count returned to baseline", re.I),
    re.compile(r"owner reserve freed", re.I),
    re.compile(r"Owner count increased after creating", re.I),
    re.compile(r"Owner count decreased after removing", re.I),
)

OBSERVED_MARKERS = re.compile(
    r"\b(observed|compared|narrated|observation)\b",
    re.I,
)

DECREASE_AFTER_REMOVAL = re.compile(
    r"decreased after remov",
    re.I,
)


def _has_assert_args(steps) -> bool:
    return any(
        "expected_direction" in (s.action_args or {})
        or "expected_delta" in (s.action_args or {})
        for s in steps
        if s.action in VERIFY_ACTIONS
    )


def test_reserves_101_does_not_claim_decrease_without_removal():
    """F-839dcc62: no phantom 'decreased after removing' when nothing is removed."""
    mod = load_all_modules()["reserves_101"]
    actions = {s.action for s in mod.steps if s.action}
    has_removal = bool(actions & REMOVAL_ACTIONS)
    phantom = [c for c in mod.checks if DECREASE_AFTER_REMOVAL.search(c)]
    assert not phantom or has_removal, (
        "reserves_101 checks: claim owner-count decrease after removal, but the "
        f"module never removes objects (actions={sorted(actions)}). "
        f"Offending checks: {phantom!r}"
    )


def test_verify_backed_checks_are_observed_or_asserted():
    """F-305bb7e8: absolute checks: language requires expected_* or 'observed'."""
    mods = load_all_modules()
    failures: list[str] = []

    for mid, mod in sorted(mods.items()):
        verify_steps = [s for s in mod.steps if s.action in VERIFY_ACTIONS]
        if not verify_steps:
            continue
        if _has_assert_args(verify_steps):
            continue
        for check in mod.checks:
            if not any(p.search(check) for p in ABSOLUTE_CHECK_PATTERNS):
                continue
            if OBSERVED_MARKERS.search(check):
                continue
            failures.append(f"{mid}: {check!r}")

    assert not failures, (
        "checks: bullets claim a confirmed fact that informational "
        "verify_reserve_change / verify_position_delta cannot prove. "
        "Reword to observed/compared language, or wire expected_direction / "
        "expected_delta once handlers assert. Offenders:\n  - "
        + "\n  - ".join(failures)
    )


def test_every_verify_call_site_is_enumerated_in_suite():
    """Guard: suite knows every shipped module that calls the comparison handlers."""
    mods = load_all_modules()
    callers = sorted(
        mid
        for mid, mod in mods.items()
        if any(s.action in VERIFY_ACTIONS for s in mod.steps)
    )
    expected = [
        "account_hygiene",
        "amm_liquidity_101",
        "checks_101",
        "dex_inventory_guardrails",
        "dex_market_making_101",
        "dex_vs_amm_risk_literacy",
        "escrow_finish_101",
        "reserves_101",
    ]
    assert callers == expected, (
        f"verify_* call-site set drifted: got {callers}, expected {expected}. "
        "Update this list and classify each site (fix checks: or justify)."
    )
