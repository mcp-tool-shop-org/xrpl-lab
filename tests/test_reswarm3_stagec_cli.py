"""Re-swarm-3 Stage C (AMEND) — CLI / doctor / config surgical fixes.

Covers five findings, test-first:

* PTC-001 — the pytest ``filterwarnings`` config must ACTUALLY match the
  live ``StarletteDeprecationWarning`` emitted at ``fastapi.testclient``
  import (a ``UserWarning`` subclass, NOT ``DeprecationWarning``, with a
  back-ticked message). A meta-test asserts the configured filter catches
  the real warning so the suppression can't silently rot again.
* PC-001 — the doctor "warn" severity tier was dead code: informational
  checks (curriculum drift, safe env override, last-error) rendered as hard
  red failures under an "environment is broken" banner. They now carry a
  ``severity`` and map to ``status="warn"`` / ``overall="warning"``.
* PC-003 — ``xrpl-lab fund``'s generic (non-rate-limited) faucet failure
  printed "Funding failed" but exited 0, so a cohort script saw success.
  It now exits non-zero, matching the rate-limited path.
* PC-005 — the missing-prereq status blocker now names the actual command
  to run (``xrpl-lab run <first_missing_prereq>``), like the wallet and
  dry-run blockers.
* PTC-004 — an OPT-IN guard (skipped when the KB db is absent) that the
  four product-expected capability slugs EXIST in the live xrpl-knowledge
  KB ``capabilities`` table, catching a KB-side rename when present.
"""

from __future__ import annotations

import re
import warnings

import pytest
from click.testing import CliRunner

from xrpl_lab.cli import main

# ── PTC-001: the deprecation-warning suppression must actually match ──────
#
# THE GAP: pyproject's filterwarnings ignored ``...:DeprecationWarning`` but
# the live warning is ``StarletteDeprecationWarning`` — a *UserWarning*
# subclass — and the ignore regex lacked the back-ticks the real message
# carries. So neither the ``error::DeprecationWarning`` escalation NOR the
# ignore matched it; the suite was green by accident, and a starlette bump
# that re-parents or removes the httpx shim would turn the whole API suite
# red. These tests pin the fix to the LIVE warning object, so the config and
# the reality can't drift apart silently again.


def _live_starlette_deprecation():
    """Return (category, message) for the warning fastapi.testclient emits.

    The shim warning fires at ``starlette.testclient`` *import* time, not at
    ``TestClient()`` construction, so once any earlier test has imported the
    module a plain ``import`` won't re-emit it. We force re-execution of the
    module body with ``importlib.reload`` inside an isolated
    ``catch_warnings`` block (all filters reset) so we capture the REAL
    warning object regardless of test order or ambient config.

    Returns ``None`` if the shim was removed (a future starlette) — the tests
    below then skip rather than fail, because the warning vanishing is itself
    the migration we want and not a regression here.
    """
    import importlib

    try:
        import starlette.testclient as st_testclient
    except Exception:  # noqa: BLE001 — starlette testclient gone entirely
        return None

    with warnings.catch_warnings(record=True) as caught:
        warnings.resetwarnings()
        warnings.simplefilter("always")
        try:
            importlib.reload(st_testclient)
        except Exception:  # noqa: BLE001 — best-effort probe
            return None
    for w in caught:
        if "starlette.testclient" in str(w.message):
            return (w.category, str(w.message))
    return None


def _configured_filterwarnings() -> list[str]:
    """Read the effective ``filterwarnings`` list from pyproject.toml."""
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    with open(root / "pyproject.toml", "rb") as fh:
        data = tomllib.load(fh)
    return data["tool"]["pytest"]["ini_options"]["filterwarnings"]


class TestFilterWarningsActuallyMatch:
    def test_live_warning_is_a_userwarning_not_deprecationwarning(self):
        """Regression pin for the misdiagnosis in the OLD config: the live
        warning is NOT a DeprecationWarning, so a ``:DeprecationWarning``
        scoped ignore could never have matched it."""
        live = _live_starlette_deprecation()
        if live is None:
            pytest.skip("starlette httpx-testclient shim removed — nothing to match")
        category, message = live
        assert not issubclass(category, DeprecationWarning), (
            "the live warning is a UserWarning subclass "
            f"({category.__module__}.{category.__name__}); a "
            "':DeprecationWarning'-scoped ignore is a no-op against it"
        )
        assert issubclass(category, UserWarning)
        # The real message carries back-ticks around httpx / starlette.testclient.
        assert "`httpx`" in message and "`starlette.testclient`" in message

    def test_a_configured_ignore_filter_catches_the_live_warning(self):
        """META-TEST — at least one configured ``ignore:`` filter, parsed the
        way pytest parses ini filterwarnings, must actually suppress the live
        warning. This is the guard that stops the suppression rotting again:
        if starlette changes the message or re-parents the class and the
        config isn't updated, this goes red."""
        live = _live_starlette_deprecation()
        if live is None:
            pytest.skip("starlette httpx-testclient shim removed — nothing to match")
        category, message = live

        from _pytest.config import parse_warning_filter

        configured = _configured_filterwarnings()
        ignore_lines = [c for c in configured if c.startswith("ignore")]
        assert ignore_lines, "no ignore filter configured for the shim warning"

        # First prove the warning WOULD raise without the ignore — escalate
        # the live category itself to error. This makes the test rigorous:
        # a passing result means the ignore actively MATCHED and suppressed a
        # warning that was otherwise erroring, not merely that a lax default
        # let it through.
        with warnings.catch_warnings():
            warnings.resetwarnings()
            warnings.simplefilter("error", category)
            with pytest.raises(category):
                warnings.warn(message, category, stacklevel=1)

        suppressed_by_any = False
        matched_line = None
        for line in ignore_lines:
            parsed = parse_warning_filter(line, escape=False)
            with warnings.catch_warnings():
                warnings.resetwarnings()
                # Escalate the live category to error, THEN apply the ignore.
                # If the ignore matches, the warning is suppressed and nothing
                # raises; if it doesn't match, the escalation fires and we move
                # on to the next candidate line.
                warnings.simplefilter("error", category)
                warnings.filterwarnings(*parsed)
                try:
                    warnings.warn(message, category, stacklevel=1)
                    suppressed_by_any = True
                    matched_line = line
                    break
                except Warning:
                    continue
        assert suppressed_by_any, (
            "no configured ignore filter matches the live "
            f"{category.__name__}: {message!r} — the suppression is a no-op"
        )
        assert matched_line is not None

    def test_config_still_escalates_real_deprecations(self):
        """The ``error::DeprecationWarning`` escalation for OTHER (genuine
        DeprecationWarning) deprecations must survive the PTC-001 fix — we
        only widened the ignore to the real shim category, not disarmed the
        net."""
        configured = _configured_filterwarnings()
        assert any(
            c.replace(" ", "") == "error::DeprecationWarning" for c in configured
        ), "the error::DeprecationWarning escalation must remain for real deprecations"

    def test_ignore_filter_targets_the_backticked_message(self):
        """The ignore must match the REAL message (with back-ticks). A regex
        without them — the old bug — matches nothing."""
        live = _live_starlette_deprecation()
        if live is None:
            pytest.skip("starlette httpx-testclient shim removed — nothing to match")
        _category, message = live
        configured = _configured_filterwarnings()
        ignore_lines = [c for c in configured if c.startswith("ignore")]
        # Extract the message-regex field (2nd colon-delimited field) of each
        # ignore filter and confirm at least one matches the live message.
        matched = False
        for line in ignore_lines:
            fields = line.split(":")
            if len(fields) < 2 or not fields[1]:
                continue
            if re.search(fields[1], message):
                matched = True
                break
        assert matched, (
            "no ignore-filter message-regex matches the back-ticked live "
            f"message {message!r} — did the regex drop the back-ticks?"
        )


# ── PC-001: the doctor "warn" tier must fire for informational checks ─────
#
# THE GAP: get_doctor mapped every failed check to status="fail" and
# overall="error", so informational checks (curriculum drift, a SAFE env
# override, last-error) rendered as red ✕ under "environment is broken" —
# over-alarming a learner whose environment is fine. The frontend and
# schema already support a "warn" tier; the backend never produced one.


class TestDoctorWarnTier:
    def test_check_dataclass_has_severity_field(self):
        """The doctor Check gains a ``severity`` so a check can declare
        itself informational (warn) vs hard failure (fail)."""
        from xrpl_lab.doctor import Check

        c = Check("x", passed=True)
        assert hasattr(c, "severity")
        # Default is a hard failure — existing checks keep failing loudly.
        assert c.severity == "fail"

    def test_curriculum_drift_check_is_warn_severity(self, tmp_path, monkeypatch):
        """A completed module whose prereqs aren't completed is curriculum
        DRIFT — informational, not a broken environment. It must carry
        severity='warn'."""
        from xrpl_lab.doctor import _check_last_module_state
        from xrpl_lab.state import LabState, save_state

        monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
        monkeypatch.setattr(
            "xrpl_lab.doctor.state_path", lambda: tmp_path / "state.json"
        )
        state = LabState()
        # Complete a module that HAS prerequisites without completing them,
        # forcing the drift branch.
        from xrpl_lab.curriculum import build_graph
        from xrpl_lab.modules import load_all_modules

        graph = build_graph(load_all_modules())
        drifted = next(
            (mid for mid in graph.modules if graph.prerequisites(mid)), None
        )
        assert drifted is not None, "fixture needs a module with prereqs"
        state.complete_module(drifted)
        save_state(state)

        check = _check_last_module_state()
        assert not check.passed, "this fixture is engineered to drift"
        assert check.severity == "warn", (
            "curriculum drift is informational, not a hard failure"
        )

    def test_safe_env_override_present_is_warn_severity(self, monkeypatch):
        """A SAFE (still-testnet) env override present is informational: the
        learner overrode the endpoint but stayed on a safe network. It should
        surface as warn, not pass silently and not fail loudly."""
        from xrpl_lab.doctor import _check_env_overrides

        monkeypatch.delenv("XRPL_LAB_FAUCET_URL", raising=False)
        monkeypatch.setenv(
            "XRPL_LAB_RPC_URL", "https://s.altnet.rippletest.net:51234"
        )
        check = _check_env_overrides()
        # Present-but-safe: not a hard failure. The check surfaces the fact
        # that an override is active (warn), rather than a silent pass.
        assert check.severity == "warn"

    def test_unsafe_env_override_stays_hard_fail(self, monkeypatch):
        """A NON-testnet override is a real-funds risk — it must remain a
        hard fail (severity='fail'), never demoted to warn."""
        from xrpl_lab.doctor import _check_env_overrides

        monkeypatch.delenv("XRPL_LAB_FAUCET_URL", raising=False)
        monkeypatch.setenv("XRPL_LAB_RPC_URL", "https://s1.ripple.com:51234")
        check = _check_env_overrides()
        assert not check.passed
        assert check.severity == "fail", "a mainnet override must stay a hard fail"

    def test_get_doctor_maps_warn_check_to_warn_status(self, monkeypatch):
        """A warn-severity failed check yields status='warn' and
        overall='warning' — not the red 'error' banner."""
        import asyncio

        from xrpl_lab.api.routes import get_doctor
        from xrpl_lab.doctor import Check, DoctorReport

        async def _fake_run_doctor() -> DoctorReport:
            report = DoctorReport()
            report.checks.append(Check("Wallet", passed=True, detail="ok"))
            report.checks.append(
                Check(
                    "Env overrides",
                    passed=False,
                    detail="informational",
                    severity="warn",
                )
            )
            return report

        monkeypatch.setattr(
            "xrpl_lab.api.routes.run_doctor", _fake_run_doctor
        )
        resp = asyncio.run(get_doctor())
        env = next(c for c in resp.checks if c.name == "Env overrides")
        assert env.status == "warn", "warn-severity check must map to status=warn"
        assert resp.overall == "warning", (
            "warns with no hard fails must give overall=warning, not error"
        )

    def test_get_doctor_hard_fail_still_error(self, monkeypatch):
        """A real (severity='fail') failure still yields status='fail' and
        overall='error' — the fix must not soften genuine breakage."""
        import asyncio

        from xrpl_lab.api.routes import get_doctor
        from xrpl_lab.doctor import Check, DoctorReport

        async def _fake_run_doctor() -> DoctorReport:
            report = DoctorReport()
            report.checks.append(
                Check("Wallet", passed=False, detail="Not found", severity="fail")
            )
            return report

        monkeypatch.setattr(
            "xrpl_lab.api.routes.run_doctor", _fake_run_doctor
        )
        resp = asyncio.run(get_doctor())
        wallet = next(c for c in resp.checks if c.name == "Wallet")
        assert wallet.status == "fail"
        assert resp.overall == "error"

    def test_get_doctor_warn_and_fail_prefers_error(self, monkeypatch):
        """When both a warn and a hard fail are present, overall is 'error' —
        a hard fail dominates. Warns never mask a real failure."""
        import asyncio

        from xrpl_lab.api.routes import get_doctor
        from xrpl_lab.doctor import Check, DoctorReport

        async def _fake_run_doctor() -> DoctorReport:
            report = DoctorReport()
            report.checks.append(
                Check("Env overrides", passed=False, detail="info", severity="warn")
            )
            report.checks.append(
                Check("Wallet", passed=False, detail="Not found", severity="fail")
            )
            return report

        monkeypatch.setattr(
            "xrpl_lab.api.routes.run_doctor", _fake_run_doctor
        )
        resp = asyncio.run(get_doctor())
        assert resp.overall == "error", "a hard fail must dominate a warn"


# ── PC-003: fund's generic faucet failure must exit non-zero ──────────────
#
# THE GAP: the rate-limited faucet path exits with a distinct code, but the
# GENERIC failure printed "Funding failed" and returned exit 0. A cohort
# script running `xrpl-lab fund && next-step` treated a failed fund as
# success. The exit code must match the printed failure.


class _FakeTransport:
    def __init__(self, result):
        self._result = result

    async def fund_from_faucet(self, address):
        return self._result


class TestFundGenericFailureExit:
    def _run_fund(self, monkeypatch, result):
        from xrpl_lab.state import LabState

        monkeypatch.setattr(
            "xrpl_lab.cli.load_state",
            lambda: LabState(wallet_address="rFUNDTEST"),
        )
        monkeypatch.setattr(
            "xrpl_lab.cli._get_transport",
            lambda dry_run=False: _FakeTransport(result),
        )
        return CliRunner().invoke(main, ["fund"])

    def test_generic_faucet_failure_exits_nonzero(self, monkeypatch):
        from xrpl_lab.transport.base import FundResult

        # A generic (non-rate-limited) failure: no special code.
        result = FundResult(
            success=False,
            address="rFUNDTEST",
            message="faucet returned HTTP 500",
            code="",
        )
        outcome = self._run_fund(monkeypatch, result)
        assert outcome.exit_code != 0, (
            "a failed fund must exit non-zero so `fund && next` short-circuits"
        )
        assert "Funding failed" in outcome.output

    def test_successful_fund_exits_zero(self, monkeypatch):
        from xrpl_lab.transport.base import FundResult

        result = FundResult(success=True, address="rFUNDTEST", balance="1000")
        outcome = self._run_fund(monkeypatch, result)
        assert outcome.exit_code == 0
        assert "Funded" in outcome.output

    def test_rate_limited_still_exits_nonzero(self, monkeypatch):
        """The already-correct rate-limited path stays non-zero — the fix
        must not regress it."""
        from xrpl_lab.transport.base import FundResult

        result = FundResult(
            success=False,
            address="rFUNDTEST",
            message="rate limited",
            code="RUNTIME_FAUCET_RATE_LIMITED",
        )
        outcome = self._run_fund(monkeypatch, result)
        assert outcome.exit_code != 0


# ── PC-005: the missing-prereq blocker must name the run command ──────────
#
# THE GAP: the wallet and dry-run blockers name the exact command to run,
# but the missing-prereq blocker said "'X' builds on Y — finish that first"
# with no command. A learner had to guess the syntax. It now appends
# ``: xrpl-lab run <first_missing_prereq>``.


class TestPrereqBlockerNamesCommand:
    """The missing-prereq blocker branch in ``get_learner_status`` only fires
    when the graph's ``next_module`` returns a module with an unmet prereq.
    The deterministic next-picker guarantees all prereqs are met for its pick,
    so we force the branch by patching ``next_module`` to return a real module
    that HAS a prerequisite while the completed-set is empty. This exercises
    the exact string-building code path (workshop.py) rather than relying on a
    curriculum shape that may not surface it."""

    def _status_with_forced_missing_prereq(self, monkeypatch):
        from xrpl_lab.curriculum import build_graph
        from xrpl_lab.modules import load_all_modules
        from xrpl_lab.state import LabState
        from xrpl_lab.workshop import get_learner_status

        graph = build_graph(load_all_modules())
        # A real module that declares at least one prerequisite.
        target = next(
            (mid for mid in graph.modules if graph.prerequisites(mid)), None
        )
        assert target is not None, "curriculum needs a module with a prereq"
        first_missing = graph.prerequisites(target)[0]

        # Force next_module to resolve to `target` with an EMPTY completed set,
        # so `first_missing` is genuinely uncompleted → the blocker fires.
        monkeypatch.setattr(
            "xrpl_lab.workshop.build_graph",
            lambda mods: _StubGraph(graph, target),
        )
        status = get_learner_status(LabState(wallet_address="rPREREQTEST"))
        prereq_blockers = [b for b in status.blockers if "builds on" in b]
        assert prereq_blockers, (
            "forced next_module with unmet prereq must surface a blocker; "
            f"blockers were: {status.blockers}"
        )
        return prereq_blockers[0], first_missing

    def test_prereq_blocker_contains_run_command(self, monkeypatch):
        blocker, _first_missing = self._status_with_forced_missing_prereq(
            monkeypatch
        )
        assert "xrpl-lab run " in blocker, (
            f"missing-prereq blocker must name the run command: {blocker!r}"
        )

    def test_prereq_blocker_names_the_first_missing_module_id(self, monkeypatch):
        """The named command references the FIRST missing prerequisite module
        id — the concrete next thing to run, not the blocked module."""
        blocker, first_missing = self._status_with_forced_missing_prereq(
            monkeypatch
        )
        assert f"xrpl-lab run {first_missing}" in blocker, (
            f"blocker must name `xrpl-lab run {first_missing}`: {blocker!r}"
        )


class _StubGraph:
    """Wraps a real CurriculumGraph but pins ``next_module`` to a chosen id,
    delegating everything else (prerequisites, modules, etc.) to the real
    graph so the surrounding code sees authentic curriculum data."""

    def __init__(self, real, forced_next):
        self._real = real
        self._forced_next = forced_next

    def next_module(self, completed):  # noqa: ARG002 — force a fixed pick
        return self._forced_next

    def __getattr__(self, name):
        return getattr(self._real, name)


# ── PTC-004: product-expected KB slugs must exist in the live KB ──────────
#
# THE GAP: the four capability slugs the product ships (nftokenmint,
# mpt-issuance-create-config, escrow-xrp, did-transactions) are hand-mirrored
# from the KB's MODULE_CAPABILITY dict and never validated against the live
# KB. A KB-side rename would silently drop those proofs at ingest. This
# OPT-IN guard (skipped when the KB db is absent, mirroring
# load_kb_capability_slugs's graceful-degrade) asserts each slug EXISTS in
# the live KB capabilities table when the KB is present.


def _product_expected_slugs() -> set[str]:
    """The capability slugs the product expects. Read from test_v2_kbsource
    if importable (single source of truth), else hardcode the four shipped
    slugs — never fail collection if the sibling module is unavailable."""
    try:
        from tests.test_v2_kbsource import EXPECTED_KB_SOURCES

        return set(EXPECTED_KB_SOURCES.values())
    except Exception:  # noqa: BLE001 — sibling not importable; use the known set
        return {
            "nftokenmint",
            "mpt-issuance-create-config",
            "escrow-xrp",
            "did-transactions",
        }


class TestProductSlugsExistInLiveKb:
    def test_expected_slugs_present_in_live_kb(self):
        from xrpl_lab.linter import load_kb_capability_slugs

        live = load_kb_capability_slugs()
        if live is None:
            pytest.skip("xrpl-knowledge KB db not present — opt-in guard skipped")
        expected = _product_expected_slugs()
        missing = sorted(s for s in expected if s not in live)
        assert not missing, (
            "product-expected capability slugs absent from the live KB "
            f"capabilities table (KB-side rename?): {missing}"
        )
