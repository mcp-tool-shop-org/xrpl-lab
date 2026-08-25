"""Wave 6 Stage C — wire expected_* on assert-worthy verify_* module steps.

SEED-C-expected-args: handlers already assert when expected_owner_delta /
expected_direction / expected_balance_delta / expected_offer_delta are
supplied. Modules whose lesson states a directional fact must pass those
args so the learner sees pass/fail, not a silent observation.

Hedged sites ("may increase", "roughly", inventory-conditional) stay
observed-only and are enumerated below as JUSTIFIED_OBSERVED.
"""

from __future__ import annotations

from xrpl_lab.modules import load_all_modules

VERIFY_ACTIONS = frozenset({"verify_reserve_change", "verify_position_delta"})

# (module_id, before, after) — lesson states a hard directional/delta fact.
MUST_ASSERT: dict[tuple[str, str, str], frozenset[str]] = {
    ("account_hygiene", "baseline", "dirty"): frozenset(
        {"expected_owner_delta", "expected_direction"}
    ),
    ("account_hygiene", "dirty", "clean"): frozenset(
        {"expected_owner_delta", "expected_direction"}
    ),
    ("account_hygiene", "baseline", "clean"): frozenset(
        {"expected_owner_delta", "expected_direction"}
    ),
    ("checks_101", "before_check", "after_check"): frozenset(
        {"expected_owner_delta", "expected_direction"}
    ),
    ("escrow_finish_101", "before_escrow", "after_finish"): frozenset(
        {"expected_owner_delta", "expected_direction"}
    ),
    ("reserves_101", "before", "after_create"): frozenset(
        {"expected_owner_delta", "expected_direction"}
    ),
    ("dex_market_making_101", "baseline", "after_offers"): frozenset(
        {"expected_owner_delta", "expected_direction", "expected_offer_delta"}
    ),
    ("dex_market_making_101", "baseline", "final"): frozenset(
        {"expected_owner_delta", "expected_direction", "expected_offer_delta"}
    ),
    # Offer count +2 is the hard dry-run-safe fact. Owner-count +2 is true on
    # live ledger but dry-run strategy offers bump offer_count without
    # owner_count — do not wire expected_owner_delta/direction here.
    ("dex_vs_amm_risk_literacy", "baseline", "after_dex"): frozenset(
        {"expected_offer_delta"}
    ),
}

# Hedged / conditional — stay observed-only (no expected_* required).
JUSTIFIED_OBSERVED: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("amm_liquidity_101", "before_amm", "after_deposit"),
        ("amm_liquidity_101", "before_amm", "after_withdraw"),
        ("dex_inventory_guardrails", "baseline", "after_offers"),
        ("dex_vs_amm_risk_literacy", "after_dex_cleanup", "after_amm"),
        ("dex_vs_amm_risk_literacy", "baseline", "final"),
    }
)

ASSERT_KEYS = frozenset(
    {
        "expected_owner_delta",
        "expected_direction",
        "expected_balance_delta",
        "expected_offer_delta",
    }
)


def _verify_sites():
    mods = load_all_modules()
    sites: list[tuple[str, str, str, dict]] = []
    for mid, mod in sorted(mods.items()):
        for step in mod.steps:
            if step.action not in VERIFY_ACTIONS:
                continue
            args = step.action_args or {}
            sites.append(
                (
                    mid,
                    args.get("before", "before"),
                    args.get("after", "after"),
                    args,
                )
            )
    return sites


def test_every_verify_call_site_is_classified():
    """Call-site enumeration contract: every verify_* site is assert or observed."""
    keys = {(m, b, a) for m, b, a, _ in _verify_sites()}
    classified = set(MUST_ASSERT) | JUSTIFIED_OBSERVED
    assert keys == classified, (
        "verify_* call-site set drifted vs Stage C classification.\n"
        f"  missing from class map: {sorted(keys - classified)}\n"
        f"  stale class entries: {sorted(classified - keys)}"
    )


def test_assert_worthy_verify_steps_wire_expected_args():
    """RED gate: directional lessons must opt into handler asserts."""
    sites = {(m, b, a): args for m, b, a, args in _verify_sites()}
    failures: list[str] = []
    for key, required in sorted(MUST_ASSERT.items()):
        mid, before, after = key
        args = sites.get(key)
        if args is None:
            failures.append(f"{mid}: missing verify step before={before} after={after}")
            continue
        missing = sorted(required - set(args))
        if missing:
            failures.append(
                f"{mid} before={before} after={after}: missing {missing}; "
                f"have={sorted(k for k in args if k in ASSERT_KEYS)}"
            )
    assert not failures, (
        "SEED-C-expected-args: assert-worthy verify_* steps lack expected_* args. "
        "Wire expected_owner_delta / expected_direction (and offer/balance deltas "
        "when the lesson claims them) so handlers assert instead of observe-only.\n  - "
        + "\n  - ".join(failures)
    )


def test_justified_observed_sites_remain_unasserted():
    """Hedged sites must not silently gain wrong expected_* without re-review."""
    sites = {(m, b, a): args for m, b, a, args in _verify_sites()}
    accidental: list[str] = []
    for key in sorted(JUSTIFIED_OBSERVED):
        args = sites.get(key)
        if args is None:
            accidental.append(f"{key}: site missing")
            continue
        present = sorted(ASSERT_KEYS & set(args))
        if present:
            accidental.append(f"{key[0]} before={key[1]} after={key[2]}: {present}")
    assert not accidental, (
        "JUSTIFIED_OBSERVED sites unexpectedly carry expected_* — either move "
        "them to MUST_ASSERT with a hard lesson claim, or drop the args.\n  - "
        + "\n  - ".join(accidental)
    )
