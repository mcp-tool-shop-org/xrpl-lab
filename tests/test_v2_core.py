"""v2.0.0 CORE regression tests — TEST-FIRST invariants for the dogfood swarm.

Each test probes the FULL invariant for one finding (CORE-A-001/002/003/004,
API-A-001). Tests are written to fail against the v1.8.0 code, then pass after
the fix lands. Do not weaken these — they are permanent anti-drift gates.
"""

from __future__ import annotations

import io
import json
import logging
import tomllib
from pathlib import Path

import pytest
from click.testing import CliRunner

import xrpl_lab
from xrpl_lab import state as state_mod
from xrpl_lab.cli import main
from xrpl_lab.curriculum import build_graph
from xrpl_lab.modules import ModuleDef, ModuleStep
from xrpl_lab.state import LabState
from xrpl_lab.transport.base import SubmitResult
from xrpl_lab.transport.dry_run import DryRunTransport

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _pyproject_version() -> str:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    return data["project"]["version"]


# ── CORE-A-001: version single-source ────────────────────────────────────


def test_version_matches_pyproject():
    """The runtime __version__ MUST equal pyproject [project].version.

    Anti-drift gate: the v1.8.0 package hardcoded __version__ = "1.7.1",
    so proof packs / certs / --version all carried a stale stamp. This
    test fails any time the source-checkout fallback drifts from the
    declared package version.
    """
    assert xrpl_lab.__version__ == _pyproject_version()


# ── CORE-A-001 cont.: state.py default version ────────────────────────────


def test_labstate_default_version_tracks_package():
    """A freshly-constructed LabState stamps the current package version.

    state.py:80 had `version: str = "1.7.1"` as a literal default — it
    must instead default to xrpl_lab.__version__ so the stamp can never
    be a stale literal.
    """
    assert LabState().version == xrpl_lab.__version__


def test_labstate_version_default_is_name_reference_not_literal():
    """IT-001: prove the default is a NAME reference, not a string literal.

    The runtime-equality check above stays GREEN even if the default were
    reverted to a literal that happens to equal the current version
    (e.g. `version: str = "1.8.0"`). That is the half-invariant: it only
    pins value-equality-today, not the source-of-truth binding.

    Parse state.py and assert the `version` field default node is
    `ast.Name(id='__version__')` — a reference to the module's single
    source of truth — and explicitly NOT an `ast.Constant`. This goes RED
    the moment the default becomes a literal (even one equal to the
    current version) and GREEN only for `version: str = __version__`.
    """
    import ast

    state_src = (
        Path(state_mod.__file__).read_text(encoding="utf-8")
    )
    tree = ast.parse(state_src)

    classdef = next(
        (n for n in tree.body
         if isinstance(n, ast.ClassDef) and n.name == "LabState"),
        None,
    )
    assert classdef is not None, "LabState class not found in state.py"

    version_default = None
    for stmt in classdef.body:
        # `version: str = <default>` is an AnnAssign with a target Name.
        if (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.target.id == "version"
        ):
            version_default = stmt.value
            break

    assert version_default is not None, (
        "no `version: <type> = <default>` annotated field on LabState"
    )
    assert not isinstance(version_default, ast.Constant), (
        "LabState.version default is a literal — it must be a reference to "
        "__version__, not a hardcoded string (even one equal to the current "
        f"version). Got constant: {ast.dump(version_default)}"
    )
    assert isinstance(version_default, ast.Name), (
        f"LabState.version default must be a Name node; got "
        f"{type(version_default).__name__}"
    )
    assert version_default.id == "__version__", (
        f"LabState.version must default to __version__; got "
        f"reference to {version_default.id!r}"
    )


# ── CORE-A-003: load_state OSError handling (no path leak) ────────────────


def test_load_state_handles_oserror_without_path_leak(monkeypatch, tmp_path):
    """load_state() must not raise a bare OSError nor leak the abs path.

    A locked-down / shared-machine state.json can raise PermissionError
    from read_text(). The v1.8.0 try only caught (JSONDecodeError,
    ValueError, ValidationError), so the OSError escaped as a raw
    traceback that printed the absolute state.json path.
    """
    home = tmp_path / ".xrpl-lab"
    home.mkdir()
    state_file = home / "state.json"
    state_file.write_text('{"version": "1.8.0"}', encoding="utf-8")
    monkeypatch.setenv("XRPL_LAB_HOME", str(home))

    real_read_text = Path.read_text

    def boom(self, *args, **kwargs):
        # Only sabotage the state.json read; let everything else through.
        if self == state_file:
            raise PermissionError(13, "Permission denied", str(state_file))
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", boom)

    warnings: list[str] = []
    monkeypatch.setattr(
        "builtins.print",
        lambda *a, **k: warnings.append(" ".join(str(x) for x in a)),
    )

    # Must NOT raise a bare OSError/PermissionError.
    try:
        result = state_mod.load_state()
    except OSError as exc:  # pragma: no cover - this is the failure we guard
        pytest.fail(f"load_state leaked a raw OSError: {exc!r}")

    # Returns a usable fresh state (or a LabState) rather than crashing.
    assert isinstance(result, LabState)

    # The absolute state.json path must not appear in any user-facing message.
    abs_path = str(state_file)
    leaked = [w for w in warnings if abs_path in w]
    assert not leaked, f"absolute path leaked to user output: {leaked}"


# ── CORE-A-002: curriculum cycle-drop ─────────────────────────────────────


def _mod(
    id: str,
    track: str = "foundations",
    order: int = 1,
    requires: list[str] | None = None,
) -> ModuleDef:
    return ModuleDef(
        id=id,
        title=id.title(),
        time="5 min",
        level="beginner",
        requires=requires or [],
        produces=[],
        checks=[],
        steps=[],
        order=order,
        track=track,
        summary="Test.",
        mode="testnet",
    )


def test_canonical_order_does_not_drop_cyclic_nodes(caplog):
    """Modules in a prerequisite cycle must NOT vanish from canonical_order.

    v1.8.0 used Kahn's algorithm and silently dropped any node whose
    in_degree never reached 0 (the cyclic a<->b pair). Those modules then
    became unreachable via next_module / start / status / recovery. The
    clean node c must also remain. After the fix, all three appear.

    IT-002: this also pins the *warning-surfacing* half of the invariant.
    The no-silent-drop fix must not become a no-quiet-swallow regression:
    canonical_order emits a ``logger.warning`` on the xrpl_lab.curriculum
    logger that names the cyclic modules (it interpolates the leftover
    ids). Removing that ``logger.warning(...)`` call must turn this RED.
    """
    mods = {
        "a": _mod("a", order=1, requires=["b"]),
        "b": _mod("b", order=2, requires=["a"]),
        "c": _mod("c", order=3),
    }
    g = build_graph(mods)

    with caplog.at_level(logging.WARNING, logger="xrpl_lab.curriculum"):
        order = g.canonical_order()

    # No-drop half: every module — including the cyclic pair — survives.
    assert set(order) == {"a", "b", "c"}, (
        f"cyclic nodes were dropped: got {order}"
    )

    # Warning-surfacing half: a WARNING must fire AND name the cyclic
    # modules, so a facilitator can act on the malformed curriculum rather
    # than silently shipping an imperfect ordering.
    cycle_warnings = [
        rec for rec in caplog.records
        if rec.levelno == logging.WARNING
        and rec.name == "xrpl_lab.curriculum"
    ]
    assert cycle_warnings, (
        "canonical_order silently appended cyclic nodes without warning — "
        "the cycle must be surfaced, not quietly swallowed"
    )
    warning_text = " ".join(rec.getMessage() for rec in cycle_warnings)
    assert "a" in warning_text and "b" in warning_text, (
        f"cycle warning did not name the cyclic modules a/b: {warning_text!r}"
    )

    # next_module reaches the clean root; the cyclic pair stays *selectable*
    # via canonical_order (its mutual prereq blocks prereq-gated next_module,
    # but a recovery/manual-start path iterates canonical_order, so the pair
    # must remain present AND ordered after the clean root).
    reached: set[str] = set()
    completed: set[str] = set()
    for _ in range(len(mods) + 2):
        nxt = g.next_module(completed)
        if nxt is None:
            break
        reached.add(nxt)
        completed.add(nxt)
    assert "c" in reached, "the clean root c must be reachable via next_module"

    # Meaningful selectability check (replaces the tautological `{a,b} <= set(order)`
    # that was implied by the `== {a,b,c}` above): iterating canonical_order —
    # the path recovery/manual-start use to offer modules — must yield each
    # cyclic module exactly once, so they are individually selectable.
    selectable = [mid for mid in g.canonical_order() if mid in {"a", "b"}]
    assert sorted(selectable) == ["a", "b"], (
        f"cyclic modules not individually selectable via canonical_order: "
        f"{selectable}"
    )


# ── CORE-A-004: handlers record_tx on success-when-fail-expected ──────────


class _NoFailTransport(DryRunTransport):
    """DryRunTransport whose set_fail_next is a no-op.

    handle_submit_payment_fail calls transport.set_fail_next(True) itself,
    so to drive the 'unexpected success' branch we neutralize that toggle;
    submit_payment then returns tesSUCCESS with a real txid.
    """

    def set_fail_next(self, fail: bool = True) -> None:  # noqa: ARG002
        self._fail_next = False


@pytest.mark.asyncio
async def test_submit_payment_fail_success_branch_records_tx():
    """The success branch of handle_submit_payment_fail must record the tx.

    v1.8.0 appended the txid to context['txids'] but never called
    state.record_tx(...) on the unexpected-success path. That left the
    txid in the proof pack's completed list with no matching tx_index
    record (no explorer link, undercounted total_transactions).
    """
    from rich.console import Console

    from xrpl_lab import handlers
    from xrpl_lab.reporting import generate_proof_pack

    transport = _NoFailTransport()
    state = LabState(network="dry-run", wallet_address="rHOLDER")
    step = ModuleStep(text="fail test", action="submit_payment_fail", action_args={})
    context: dict = {"module_id": "failure_literacy", "wallet_seed": "seed"}
    console = Console(file=io.StringIO())

    result = await handlers.handle_submit_payment_fail(
        step, state, transport, "seed", context, console
    )

    # txid landed in context...
    assert result.get("txids"), "no txid recorded in context on success"
    txid = result["txids"][-1]

    # ...and MUST also be in state.tx_index (the single source of truth).
    recorded = [r for r in state.tx_index if r.txid == txid]
    assert recorded, "success txid missing from state.tx_index"
    assert recorded[0].success is True

    # Proof-pack total reflects the recorded tx.
    pack = generate_proof_pack(state)
    assert pack["total_transactions"] == len(state.tx_index)
    assert pack["total_transactions"] >= 1


# ── VC-001: handle_issue_token_expect_fail success-branch (sibling of A-004) ──


class _SuccessfulIssueTransport(DryRunTransport):
    """DryRunTransport whose submit_issued_payment unexpectedly SUCCEEDS.

    handle_issue_token_expect_fail expects the issuance to fail, but a
    pre-existing trust line (or a transport that doesn't simulate the
    chosen failure) yields tesSUCCESS. Mirror the testnet success shape:
    a real txid AND a non-empty explorer_url — the v1.8.0 handler dropped
    the explorer_url on this branch (record_tx called without it) and
    double-counted the tx as a failure in context['failed_txids'].
    """

    async def submit_issued_payment(self, *args, **kwargs):  # noqa: ARG002
        return SubmitResult(
            success=True,
            txid="ISSUE_UNEXPECTED_SUCCESS_TX",
            result_code="tesSUCCESS",
            fee="12",
            ledger_index=99999999,
            explorer_url="https://testnet.xrpl.org/transactions/ISSUE_UNEXPECTED_SUCCESS_TX",
        )


@pytest.mark.asyncio
async def test_issue_token_expect_fail_success_branch_records_with_explorer():
    """VC-001: the unexpected-success branch of handle_issue_token_expect_fail
    must record the tx WITH its explorer_url and must NOT mark it failed.

    v1.8.0 (a) called record_tx without explorer_url on the success branch,
    so the successful tx had no explorer link, and (b) appended to
    context['failed_txids'] UNCONDITIONALLY, double-counting a confirmed tx
    as a failure. This mirrors the corrected handle_submit_payment_fail.
    """
    from rich.console import Console

    from xrpl_lab import handlers

    transport = _SuccessfulIssueTransport()
    state = LabState(network="dry-run", wallet_address="rHOLDER")
    step = ModuleStep(
        text="issue expect fail", action="issue_token_expect_fail", action_args={},
    )
    context: dict = {
        "module_id": "trust_lines",
        "issuer_seed": "sIssuerSeed",
        "issuer_address": "rISSUER",
    }
    console = Console(file=io.StringIO())

    result = await handlers.handle_issue_token_expect_fail(
        step, state, transport, "seed", context, console
    )

    txid = "ISSUE_UNEXPECTED_SUCCESS_TX"

    # The successful txid is in tx_index WITH a non-empty explorer_url.
    recorded = [r for r in state.tx_index if r.txid == txid]
    assert recorded, "unexpected-success txid missing from state.tx_index"
    assert recorded[0].success is True
    assert recorded[0].explorer_url, (
        "successful issuance recorded WITHOUT an explorer_url (VC-001)"
    )

    # And it must NOT be counted as a failure.
    failed = result.get("failed_txids", [])
    assert not failed, (
        f"confirmed tx was double-counted as a failure in failed_txids: {failed}"
    )


# ── API-A-001: serve bind-safety ──────────────────────────────────────────


def _invoke_serve(host: str, monkeypatch) -> str:
    """Invoke `serve` with create_app + uvicorn.run mocked; return output."""

    def fake_create_app(dry_run=False, **kwargs):
        return object()

    def fake_uvicorn_run(app, host, port):  # noqa: ARG001
        return None

    monkeypatch.setattr("xrpl_lab.server.create_app", fake_create_app)
    monkeypatch.setattr("uvicorn.run", fake_uvicorn_run)

    runner = CliRunner()
    result = runner.invoke(
        main, ["serve", "--dry-run", "--port", "9999", "--host", host]
    )
    assert result.exit_code == 0, result.output
    return result.output


_NO_AUTH_MARKER = "no authentication"


def test_serve_warns_no_auth_for_bind_all_host(monkeypatch):
    """0.0.0.0 binds ALL interfaces — the no-auth exposure warning MUST fire.

    v1.8.0 grouped 0.0.0.0 into `loopback`, suppressing the warning for
    the single most-exposed bind address.
    """
    out = _invoke_serve("0.0.0.0", monkeypatch)
    assert _NO_AUTH_MARKER in out, "no-auth warning missing for --host 0.0.0.0"


def test_serve_no_warning_for_loopback_host(monkeypatch):
    """127.0.0.1 is true loopback — the no-auth warning must be ABSENT."""
    out = _invoke_serve("127.0.0.1", monkeypatch)
    assert _NO_AUTH_MARKER not in out, "no-auth warning wrongly fired for loopback"


def test_serve_warns_no_auth_for_ipv6_bind_all_host(monkeypatch):
    """IF-002: `::` is IPv6 all-interfaces (not ::1 loopback) — the no-auth
    exposure warning MUST fire, exactly as it does for 0.0.0.0.

    `loopback` only whitelists 127.0.0.1 / localhost / ::1; `::` must fall
    through to the exposure branch. Coverage gate against a future edit that
    accidentally groups `::` with the loopback aliases.
    """
    out = _invoke_serve("::", monkeypatch)
    assert _NO_AUTH_MARKER in out, "no-auth warning missing for --host ::"


def test_serve_cors_allowlist_for_lan_ip_is_not_overwidened(monkeypatch, tmp_path):
    """IF-002: a LAN-IP bind must pass an allow-list of ONLY the host:port plus
    loopback aliases to create_app — never a wildcard or arbitrary origin.

    With a built dashboard present, serve hands create_app `extra_origins`
    so the in-process dashboard's WebSocket can pass the Origin gate. This
    pins that the gate is scoped to {http://<IP>:port, http://localhost:port,
    http://127.0.0.1:port} and nothing wider — a '*' or stray origin would be
    a silent CORS over-widening on a network-exposed bind.
    """
    # A built dashboard must exist for extra_origins to be populated.
    dash = tmp_path / "site_dist"
    dash.mkdir()
    monkeypatch.setenv("XRPL_LAB_DASHBOARD_DIR", str(dash))

    captured: dict = {}

    def fake_create_app(dry_run=False, **kwargs):
        captured["kwargs"] = kwargs
        return object()

    def fake_uvicorn_run(app, host, port):  # noqa: ARG001
        return None

    monkeypatch.setattr("xrpl_lab.server.create_app", fake_create_app)
    monkeypatch.setattr("uvicorn.run", fake_uvicorn_run)

    lan_ip = "192.168.1.50"
    port = 9999
    runner = CliRunner()
    result = runner.invoke(
        main, ["serve", "--dry-run", "--port", str(port), "--host", lan_ip]
    )
    assert result.exit_code == 0, result.output

    origins = set(captured["kwargs"].get("extra_origins", ()))
    allowed = {
        f"http://{lan_ip}:{port}",
        f"http://localhost:{port}",
        f"http://127.0.0.1:{port}",
    }
    # No wildcard / arbitrary origin: the set is EXACTLY the allowed three.
    assert "*" not in origins, "CORS allow-list contains a wildcard origin"
    assert origins == allowed, (
        f"CORS allow-list over-widened: got {origins}, expected {allowed}"
    )


# ── IF-001: cohort-status tolerates an unreadable per-learner state.json ──────


def test_cohort_status_survives_permission_error_without_path_leak(
    monkeypatch, tmp_path
):
    """IF-001: a learner whose state.json raises PermissionError on read must
    NOT crash cohort-status, and the absolute path must NOT be surfaced.

    cli.py caught only (FileNotFoundError, ValueError); an OSError from
    read_text escaped as a raw traceback printing the absolute path (and OS
    username). The fix adds OSError to the except tuple and surfaces only the
    exception TYPE name in the warning row — never str(exc)/the abs path.
    """
    # One learner with an (otherwise valid) state.json we will sabotage.
    learner = tmp_path / "learner_a"
    (learner / ".xrpl-lab").mkdir(parents=True)
    bad_state = learner / ".xrpl-lab" / "state.json"
    bad_state.write_text('{"version": "1.8.0"}', encoding="utf-8")

    real_read_text = Path.read_text

    def boom(self, *args, **kwargs):
        if self == bad_state:
            raise PermissionError(13, "Permission denied", str(bad_state))
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", boom)

    runner = CliRunner()
    # JSON format makes the warning payload directly assertable.
    result = runner.invoke(
        main, ["cohort-status", "--dir", str(tmp_path), "--format", "json"]
    )

    # Must not crash the whole scan.
    assert result.exit_code == 0, result.output
    assert result.exception is None, (
        f"cohort-status crashed on an unreadable state.json: {result.exception!r}"
    )

    payload = json.loads(result.output)
    warns = payload["warnings"]
    assert warns, "the unreadable learner produced no warning row"
    assert any(w["learner_id"] == "learner_a" for w in warns)

    # The absolute path must not leak anywhere in the output.
    abs_path = str(bad_state)
    assert abs_path not in result.output, (
        "absolute state.json path leaked to cohort-status output"
    )
    # And the warning detail is the exception TYPE name, not str(exc).
    leak_rows = [w for w in warns if abs_path in w["error"]]
    assert not leak_rows, f"abs path leaked in warning error field: {leak_rows}"


# ── DOCBCD-001: module init --track derived from curriculum.TRACKS ────────


def test_module_init_track_choices_equal_curriculum_tracks():
    """`module init --track` choices MUST be the full curriculum.TRACKS set.

    v1.8.0 hardcoded `click.Choice([foundations,dex,reserves,audit,amm])` —
    omitting the 4 v1.8.0 tracks (nfts/tokens/payments/identity), so the
    documented CONTRIBUTING scaffold workflow hard-errored for them. Single-
    source the choices from curriculum.TRACKS so every curriculum track is
    automatically valid and the two can never drift apart again.
    """
    from xrpl_lab import curriculum
    from xrpl_lab.cli import module_init

    # Find the --track option's Choice and compare its choice set to TRACKS.
    track_param = next(
        (p for p in module_init.params if getattr(p, "name", None) == "track"),
        None,
    )
    assert track_param is not None, "module init has no --track option"
    choices = set(track_param.type.choices)
    assert choices == set(curriculum.TRACKS), (
        f"--track choices {sorted(choices)} != curriculum.TRACKS "
        f"{sorted(curriculum.TRACKS)} — they must be single-sourced"
    )


@pytest.mark.parametrize("track", ["nfts", "tokens", "payments", "identity"])
def test_module_init_scaffolds_v18_tracks_lint_clean(track, tmp_path, monkeypatch):
    """`module init --track <v1.8.0 track>` must succeed AND lint clean.

    The 4 KB-sourced v1.8.0 tracks were rejected by the old hardcoded
    Choice. After the fix each scaffolds a module skeleton that passes
    the linter immediately (the contributor's green starting point).
    """
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    out_path = tmp_path / f"new_{track}_mod.md"
    result = runner.invoke(
        main,
        [
            "module", "init",
            "--id", f"new_{track}_mod",
            "--track", track,
            "--title", f"New {track} module",
            "--time", "20 min",
            "--outfile", str(out_path),
        ],
    )
    assert result.exit_code == 0, (
        f"module init --track {track} failed: {result.output}\n"
        f"exc={result.exception!r}"
    )
    assert out_path.exists(), f"scaffold not written for track {track}"

    # The generated skeleton must pass the linter (no errors).
    from xrpl_lab.linter import lint_module_file

    issues = lint_module_file(out_path)
    errors = [i for i in issues if i.level == "error"]
    assert not errors, f"scaffold for track {track} has lint errors: {errors}"


# ── COREBCD-001: report-section collection is registry-derived ────────────


def _reportable_actions() -> set[str]:
    """The set of actions the runner collects a report section for.

    Imports the runner predicate so the test stays bound to the SAME
    single source the runner uses (not a re-listed copy).
    """
    import xrpl_lab.handlers  # noqa: F401 — ensure registry is populated
    from xrpl_lab.registry import all_actions
    from xrpl_lab.runner import _is_reportable_action

    return {name for name in all_actions() if _is_reportable_action(name)}


@pytest.mark.parametrize(
    "action",
    [
        "mint_nft", "verify_nft",
        "create_escrow", "verify_escrow",
        "set_did", "verify_did",
        "create_mpt_issuance", "verify_mpt_issuance",
    ],
)
def test_v18_actions_are_reportable(action):
    """The 8 v1.8.0 actions MUST be collected into the module report.

    v1.8.0 gated report sections on a hardcoded action tuple that omitted
    all eight, so NFT/escrow/DID/MPT steps silently vanished from the
    written report even though their txids landed in state. The fix derives
    reportability from the registry; this pins that each new action is in.
    """
    assert action in _reportable_actions(), (
        f"action {action!r} is not collected into the module report — "
        "the v1.8.0 modules' steps would silently vanish from the report"
    )


def test_every_tx_producing_action_is_reportable():
    """GUARD: every registered tx-producing/verify action is reportable.

    Anti-drift gate so module #17 fails loudly here, not silently in a
    learner's report. Any registered action that produces a transaction
    (wallet_required, i.e. it can submit) OR verifies on-ledger state
    (name starts with `verify_`) MUST be collected into the report. The
    only deliberate exceptions are the setup/no-tx actions and the
    completion-time write_report sink.
    """
    import xrpl_lab.handlers  # noqa: F401
    from xrpl_lab.registry import all_actions
    from xrpl_lab.runner import _is_reportable_action

    actions = all_actions()
    # Setup / non-report actions deliberately excluded.
    _NON_REPORT = {
        "ensure_wallet", "ensure_funded",
        "create_issuer_wallet", "fund_issuer",
        "write_report",
    }
    for name, adef in actions.items():
        report_worthy = adef.wallet_required or name.startswith("verify_")
        if report_worthy and name not in _NON_REPORT:
            assert _is_reportable_action(name), (
                f"tx-producing/verify action {name!r} is NOT reportable — "
                "it will silently vanish from the module report"
            )


@pytest.mark.asyncio
async def test_run_module_report_contains_v18_action_line(tmp_path, monkeypatch):
    """End-to-end: a module with an NFT step writes that step into the report.

    Drives a real run_module over a dry-run transport with a single
    mint_nft step and asserts the written report markdown carries the
    step's `Action: \\`mint_nft\\`` line. v1.8.0 produced a report with the
    step missing entirely.
    """
    import xrpl_lab.handlers  # noqa: F401
    from xrpl_lab import runner as runner_mod
    from xrpl_lab.actions import wallet as wallet_mod
    from xrpl_lab.modules import ModuleDef, ModuleStep

    # Isolate home + workspace into tmp_path so state/report writes land here.
    monkeypatch.setenv("XRPL_LAB_HOME", str(tmp_path / ".xrpl-lab-home"))
    monkeypatch.chdir(tmp_path)

    # A funded wallet so the mint step has a seed in context.
    w = wallet_mod.create_wallet()
    wallet_mod.save_wallet(w)
    st = LabState(network="dry-run", wallet_address=w.address)
    st.wallet_address = w.address
    state_mod.save_state(st)

    module = ModuleDef(
        id="nft_report_mod",
        title="NFT Report Module",
        time="5 min",
        level="beginner",
        requires=[],
        produces=["txid", "report"],
        checks=[],
        steps=[
            ModuleStep(
                text="Mint an NFToken.",
                action="mint_nft",
                action_args={"uri": "ipfs://x", "taxon": "7"},
            ),
        ],
        order=1,
        track="nfts",
        summary="Mint then report.",
        mode="dry-run",
    )

    from rich.console import Console

    transport = DryRunTransport()
    ok = await runner_mod.run_module(
        module, transport, dry_run=True,
        console=Console(file=io.StringIO()),
    )
    assert ok is True

    reports = list((tmp_path / ".xrpl-lab" / "reports").glob("*.md"))
    assert reports, "no module report was written"
    body = reports[0].read_text(encoding="utf-8")
    assert "mint_nft" in body, (
        "the mint_nft step is missing from the written module report"
    )
    assert "Action: `mint_nft`" in body, (
        f"report has no Action line for mint_nft; body was:\n{body}"
    )


# ── COREBCD-006: new create handlers teach on failure ─────────────────────


class _FailEscrowTransport(DryRunTransport):
    """DryRunTransport whose escrow create fails with a known result_code."""

    async def submit_escrow_create(self, *args, **kwargs):  # noqa: ARG002
        return SubmitResult(
            success=False,
            result_code="tecNO_PERMISSION",
            fee="12",
            error="[dry-run] Simulated failure: escrow create",
        )


@pytest.mark.asyncio
async def test_create_escrow_failure_explains_result_code():
    """handle_create_escrow failure path MUST teach via explain_result_code.

    v1.8.0 printed only the bare `result.error`. Older handlers (e.g.
    handle_issue_token_expect_fail) route the result_code through
    explain_result_code to print Category/Meaning/Action so a failing tx
    teaches its XRPL concept inline. This pins the same behavior for the
    KB-sourced create handlers (escrow chosen as the representative).
    """
    from rich.console import Console

    from xrpl_lab import handlers
    from xrpl_lab.doctor import explain_result_code

    transport = _FailEscrowTransport()
    state = LabState(network="dry-run", wallet_address="rOWNER")
    step = ModuleStep(text="escrow", action="create_escrow", action_args={"amount": "10"})
    context: dict = {
        "module_id": "escrow_basics",
        "wallet_seed": _secret("sSeed"),
    }
    buf = io.StringIO()
    console = Console(file=buf, width=200)

    await handlers.handle_create_escrow(step, state, transport, "sSeed", context, console)

    out = buf.getvalue()
    info = explain_result_code("tecNO_PERMISSION")
    # The educational triplet must appear inline on the failure path.
    assert "Category" in out, f"no Category line printed on failure:\n{out}"
    assert info["category"] in out
    assert "Meaning" in out
    assert "Action" in out


def _secret(value: str):
    """Wrap a seed in the runner's _SecretValue (handlers call .get())."""
    from xrpl_lab.runtime import _SecretValue

    return _SecretValue(value)


# ── COREBCD-002: doctor RPC/faucet catch-all does not leak endpoint ───────


@pytest.mark.asyncio
async def test_doctor_rpc_catchall_does_not_leak_endpoint(monkeypatch, caplog):
    """_check_rpc generic-exception branch MUST NOT put str(exc) in detail.

    A raw exception whose message embeds an endpoint/proxy URL would land
    in the facilitator-shared support bundle / feedback markdown. The fix
    mirrors the humanized TimeoutError branch: a path-free detail plus a
    WARNING-level log of the full str(exc) to the package logger.
    """
    from xrpl_lab import doctor

    sentinel = "https://secret-proxy.internal.example:9999/rpc"

    class _BoomTransport:
        @property
        def network_name(self):
            return "testnet"

        async def get_network_info(self):
            raise RuntimeError(f"connection refused to {sentinel}")

    monkeypatch.setattr(
        "xrpl_lab.transport.xrpl_testnet.XRPLTestnetTransport",
        lambda *a, **k: _BoomTransport(),
    )

    with caplog.at_level(logging.WARNING, logger="xrpl_lab"):
        check = await doctor._check_rpc()

    assert check.passed is False
    assert sentinel not in check.detail, (
        f"endpoint URL leaked into Check.detail: {check.detail!r}"
    )
    assert sentinel not in check.hint, "endpoint URL leaked into Check.hint"
    # Full detail is preserved for the operator in the WARNING log.
    assert any(sentinel in rec.getMessage() for rec in caplog.records), (
        "full str(exc) was not logged at WARNING for the operator"
    )


@pytest.mark.asyncio
async def test_doctor_faucet_catchall_does_not_leak_endpoint(monkeypatch, caplog):
    """_check_faucet generic-exception branch MUST NOT leak str(exc)."""
    from xrpl_lab import doctor

    sentinel = "https://secret-faucet.internal.example:9999/accounts"
    monkeypatch.setenv("XRPL_LAB_FAUCET_URL", sentinel)

    import httpx

    class _BoomClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            raise httpx.ConnectError(f"cannot connect to {sentinel}")

    monkeypatch.setattr("httpx.AsyncClient", _BoomClient)

    with caplog.at_level(logging.WARNING, logger="xrpl_lab"):
        check = await doctor._check_faucet()

    assert check.passed is False
    assert sentinel not in check.detail, (
        f"faucet URL leaked into Check.detail: {check.detail!r}"
    )
    assert any(sentinel in rec.getMessage() for rec in caplog.records), (
        "full str(exc) was not logged at WARNING for the operator"
    )


# ── COREBCD-003: handle_fund_issuer rate-limit UX ─────────────────────────


@pytest.mark.asyncio
async def test_fund_issuer_rate_limited_shows_wait_guidance():
    """handle_fund_issuer MUST surface wait/--dry-run guidance on a 429.

    v1.8.0 printed the generic "retry by re-running" line for ALL faucet
    failures including rate-limit. The fix branches on
    code == RUNTIME_FAUCET_RATE_LIMITED and prints the faucet-rate-limited
    message + hint (mirroring `cli.py fund` / runtime.ensure_funded).
    """
    from rich.console import Console

    from xrpl_lab import handlers
    from xrpl_lab.errors import faucet_rate_limited
    from xrpl_lab.transport.base import FundResult

    class _RateLimitedTransport(DryRunTransport):
        async def fund_from_faucet(self, address):  # noqa: ARG002
            return FundResult(
                success=False,
                address=address,
                message="429 Too Many Requests",
                code="RUNTIME_FAUCET_RATE_LIMITED",
            )

    transport = _RateLimitedTransport()
    state = LabState(network="dry-run")
    step = ModuleStep(text="fund issuer", action="fund_issuer", action_args={})
    context: dict = {"issuer_address": "rISSUER", "module_id": "trust_lines"}
    buf = io.StringIO()
    console = Console(file=buf, width=200)

    await handlers.handle_fund_issuer(step, state, transport, "seed", context, console)

    out = buf.getvalue()
    err = faucet_rate_limited()
    # The rate-limited message + hint must appear; NOT the generic retry line.
    assert err.message in out or err.hint in out, (
        f"rate-limit guidance missing; output was:\n{out}"
    )
    assert "retry by re-running this module" not in out, (
        "generic retry line shown for a rate-limited result"
    )


# ── COREBCD-004: certificate empty-state start hint ───────────────────────


def test_certificate_empty_state_shows_start_hint(tmp_path, monkeypatch):
    """`certificate` with no completed modules must point at `xrpl-lab start`.

    proof-pack already has the "Complete a module first, then export: run
    xrpl-lab start to begin." hint; certificate lacked it. Pin the same hint.
    """
    monkeypatch.setenv("XRPL_LAB_HOME", str(tmp_path / ".xrpl-lab-home"))
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(main, ["certificate"])
    assert result.exit_code == 0, result.output
    assert "xrpl-lab start" in result.output, (
        f"certificate empty-state lacks the start hint:\n{result.output}"
    )


# ── COREBCD-005: support-bundle --verify guarded read ─────────────────────


def test_support_bundle_verify_oserror_is_clean(tmp_path, monkeypatch):
    """support-bundle --verify on an unreadable file → clean structured error.

    v1.8.0 did an unguarded Path(verify_path).read_text(), so an OSError on
    read produced a raw traceback that leaked the absolute path. The fix
    wraps the read like the sibling verify commands: a structured path-free
    failure + non-zero exit.
    """
    target = tmp_path / "bundle.md"
    target.write_text("placeholder", encoding="utf-8")
    abs_path = str(target)

    real_read_text = Path.read_text

    def boom(self, *args, **kwargs):
        if self == target:
            raise PermissionError(13, "Permission denied", abs_path)
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", boom)

    runner = CliRunner()
    result = runner.invoke(
        main, ["support-bundle", "--verify", abs_path]
    )

    # Non-zero exit, no uncaught traceback, and no abs-path leak.
    assert result.exit_code != 0, "unreadable bundle should exit non-zero"
    assert not isinstance(result.exception, PermissionError), (
        f"raw OSError escaped to the CLI: {result.exception!r}"
    )
    assert abs_path not in result.output, (
        f"absolute path leaked to support-bundle --verify output:\n{result.output}"
    )
