"""Wave-7/8 handlers — F-7f86ff25 (+ Advisor F-e8c41b7a) and F-657a12cf
(+ Advisor F-2f9d06c3).

F-7f86ff25: issuer reuse already prints the address, but silent reuse leaves
learners without cleanup guidance. The reuse branch must print a yellow
workshop hint naming account_hygiene / remove_trust_line (and issuer=).

F-657a12cf: remove_trust_line / verify_trust_line_removed hard-wire the peer
to context['issuer_address']. Optional PayloadField issuer= must override so
orphaned pre-reuse peers and leftover currencies can be cleared. A hint
without this override is theater.

Do not edit modules/.
"""

from __future__ import annotations

import ast
import io
import json
from pathlib import Path

import pytest
from rich.console import Console

import xrpl_lab.handlers as handlers_mod
from xrpl_lab.actions import wallet as wallet_mod
from xrpl_lab.handlers import (
    handle_create_issuer_wallet,
    handle_remove_trust_line,
    handle_verify_trust_line_removed,
)
from xrpl_lab.modules import ModuleStep
from xrpl_lab.registry import resolve
from xrpl_lab.runtime import _SecretValue
from xrpl_lab.state import LabState
from xrpl_lab.transport.dry_run import DryRunTransport

HANDLERS_PATH = Path(handlers_mod.__file__).resolve()


def _console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    console = Console(file=buf, no_color=True, markup=True, width=200)
    console.input = lambda _p="": ""  # type: ignore[assignment]
    return console, buf


# ---------------------------------------------------------------------------
# F-7f86ff25 — reuse-path cleanup hint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reuse_path_prints_cleanup_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reuse must name account_hygiene / remove_trust_line (and issuer=)."""
    monkeypatch.setenv("XRPL_LAB_HOME", str(tmp_path / ".xrpl-lab-home"))
    monkeypatch.chdir(tmp_path)

    console, buf = _console()
    step = ModuleStep(text="", action="create_issuer_wallet", action_args={})
    state = LabState(network="dry-run")
    transport = DryRunTransport()

    first = await handle_create_issuer_wallet(
        step, state, transport, "", {}, console,
    )
    issuer = first["issuer_address"]
    assert (Path(".xrpl-lab") / "issuer_wallet.json").is_file()

    buf.truncate(0)
    buf.seek(0)
    second = await handle_create_issuer_wallet(
        step, state, transport, "", {}, console,
    )
    printed = buf.getvalue()

    assert second["issuer_address"] == issuer
    assert f"Reusing existing issuer wallet: {issuer}" in printed, (
        f"reuse address line missing:\n{printed}"
    )
    lower = printed.lower()
    assert "account_hygiene" in lower, (
        "F-7f86ff25: reuse path must name module account_hygiene for cleanup:\n"
        f"{printed}"
    )
    assert "remove_trust_line" in lower, (
        "F-7f86ff25: reuse path must name remove_trust_line:\n"
        f"{printed}"
    )
    assert "issuer=" in lower or "issuer =" in lower, (
        "F-7f86ff25 paired with F-657a12cf: cleanup hint must name "
        "remove_trust_line issuer= for orphaned peers:\n"
        f"{printed}"
    )
    assert "owner" in lower and "reserve" in lower, (
        "reuse cleanup hint must mention owner reserve lock:\n"
        f"{printed}"
    )


@pytest.mark.asyncio
async def test_fresh_create_path_does_not_print_cleanup_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh mint is not the workshop-resume case — no cleanup hint."""
    monkeypatch.setenv("XRPL_LAB_HOME", str(tmp_path / ".xrpl-lab-home"))
    monkeypatch.chdir(tmp_path)

    console, buf = _console()
    step = ModuleStep(text="", action="create_issuer_wallet", action_args={})
    await handle_create_issuer_wallet(
        step, LabState(network="dry-run"), DryRunTransport(), "", {}, console,
    )
    printed = buf.getvalue().lower()
    assert "reusing existing" not in printed
    assert "account_hygiene" not in printed


# ---------------------------------------------------------------------------
# F-657a12cf — optional issuer= on remove / verify-removed
# ---------------------------------------------------------------------------


def test_remove_and_verify_payload_fields_expose_optional_issuer() -> None:
    """ActionDef must advertise issuer so modules/facilitators can override."""
    import xrpl_lab.handlers  # noqa: F401 — register

    for name in ("remove_trust_line", "verify_trust_line_removed"):
        fields = {f.name: f for f in resolve(name).payload_fields}
        assert "currency" in fields, f"{name} lost currency field"
        assert "issuer" in fields, (
            f"F-657a12cf: {name} ActionDef must expose optional PayloadField "
            f"issuer= (got {[f.name for f in resolve(name).payload_fields]})"
        )
        assert fields["issuer"].required is False, (
            f"{name}.issuer must be optional (default context issuer)"
        )


def test_remove_verify_handlers_read_args_issuer_override() -> None:
    """Source gate: handlers must prefer args.get('issuer') over context only."""
    tree = ast.parse(HANDLERS_PATH.read_text(encoding="utf-8"))
    targets = {
        "handle_remove_trust_line": False,
        "handle_verify_trust_line_removed": False,
    }
    for node in tree.body:
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        if node.name not in targets:
            continue
        src = ast.get_source_segment(
            HANDLERS_PATH.read_text(encoding="utf-8"), node
        ) or ""
        # Prefer args issuer, fall back to context issuer_address.
        reads_args = (
            'args.get("issuer"' in src
            or "args.get('issuer'" in src
        )
        targets[node.name] = reads_args

    missing = [n for n, ok in targets.items() if not ok]
    assert not missing, (
        "F-657a12cf: these handlers still hard-wire context['issuer_address'] "
        f"with no args.get('issuer') override: {missing}"
    )


@pytest.mark.asyncio
async def test_remove_trust_line_issuer_override_clears_foreign_peer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Set LAB@issuerA, switch context to issuerB, remove with issuer=A."""
    monkeypatch.setenv("XRPL_LAB_HOME", str(tmp_path / ".xrpl-lab-home"))
    monkeypatch.chdir(tmp_path)

    holder = wallet_mod.create_wallet()
    issuer_a = wallet_mod.create_wallet()
    issuer_b = wallet_mod.create_wallet()
    assert issuer_a.address != issuer_b.address

    transport = DryRunTransport()
    await transport.fund_from_faucet(holder.address)
    await transport.submit_trust_set(
        wallet_seed=holder.seed,
        issuer=issuer_a.address,
        currency="LAB",
        limit="1000",
        wallet_address=holder.address,
    )
    lines = await transport.get_trust_lines(holder.address)
    assert any(
        tl.currency == "LAB" and tl.peer == issuer_a.address for tl in lines
    ), lines

    state = LabState(network="dry-run", wallet_address=holder.address)
    # Context points at the *reused* issuer B — without override, remove
    # would target B and leave the orphaned LAB@A line sticky.
    context = {
        "wallet_seed": _SecretValue(holder.seed),
        "issuer_address": issuer_b.address,
        "module_id": "hygiene_override",
    }
    console, buf = _console()
    step = ModuleStep(
        text="",
        action="remove_trust_line",
        action_args={"currency": "LAB", "issuer": issuer_a.address},
    )
    await handle_remove_trust_line(
        step, state, transport, holder.seed, context, console,
    )
    printed = buf.getvalue()

    assert issuer_a.address in printed, (
        "F-657a12cf: explicit issuer= override must be printed so the "
        f"facilitator sees which peer is cleared:\n{printed}"
    )

    lines_after = await transport.get_trust_lines(holder.address)
    lab_a = [
        tl for tl in lines_after
        if tl.currency == "LAB" and tl.peer == issuer_a.address
    ]
    assert lab_a == [], (
        "remove_trust_line with issuer=A must clear LAB@A even when context "
        f"issuer is B ({issuer_b.address}); leftover={lab_a}"
    )


@pytest.mark.asyncio
async def test_verify_trust_line_removed_honors_issuer_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """verify_trust_line_removed with issuer=A must not false-pass on B."""
    monkeypatch.setenv("XRPL_LAB_HOME", str(tmp_path / ".xrpl-lab-home"))
    monkeypatch.chdir(tmp_path)

    holder = wallet_mod.create_wallet()
    issuer_a = wallet_mod.create_wallet()
    issuer_b = wallet_mod.create_wallet()

    transport = DryRunTransport()
    await transport.fund_from_faucet(holder.address)
    # Line still present against A.
    await transport.submit_trust_set(
        wallet_seed=holder.seed,
        issuer=issuer_a.address,
        currency="LAB",
        limit="1000",
        wallet_address=holder.address,
    )

    state = LabState(network="dry-run", wallet_address=holder.address)
    context = {
        "wallet_seed": _SecretValue(holder.seed),
        "issuer_address": issuer_b.address,  # wrong peer if no override
    }
    console, buf = _console()

    # Without override, verifying removal against context B would PASS
    # (LAB@A is ignored) — that is the defect class. With issuer=A it must
    # FAIL while the line remains.
    step = ModuleStep(
        text="",
        action="verify_trust_line_removed",
        action_args={"currency": "LAB", "issuer": issuer_a.address},
    )
    ctx = await handle_verify_trust_line_removed(
        step, state, transport, holder.seed, context, console,
    )
    recs = ctx.get("verifications", [])
    assert recs, "must record verification"
    assert recs[-1]["passed"] is False, (
        "verify_trust_line_removed(issuer=A) must fail while LAB@A remains; "
        f"got {recs[-1]!r} (context issuer was B={issuer_b.address})"
    )

    # Remove with override, then verify passes.
    await handle_remove_trust_line(
        ModuleStep(
            text="",
            action="remove_trust_line",
            action_args={"currency": "LAB", "issuer": issuer_a.address},
        ),
        state,
        transport,
        holder.seed,
        context,
        console,
    )
    ctx2 = await handle_verify_trust_line_removed(
        step, state, transport, holder.seed, context, console,
    )
    assert ctx2["verifications"][-1]["passed"] is True


@pytest.mark.asyncio
async def test_remove_trust_line_defaults_to_context_issuer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing modules (no issuer=) keep using context issuer_address."""
    monkeypatch.setenv("XRPL_LAB_HOME", str(tmp_path / ".xrpl-lab-home"))
    monkeypatch.chdir(tmp_path)

    holder = wallet_mod.create_wallet()
    issuer = wallet_mod.create_wallet()
    transport = DryRunTransport()
    await transport.fund_from_faucet(holder.address)
    await transport.submit_trust_set(
        wallet_seed=holder.seed,
        issuer=issuer.address,
        currency="HYGIENE",
        limit="100",
        wallet_address=holder.address,
    )

    state = LabState(network="dry-run", wallet_address=holder.address)
    context = {
        "wallet_seed": _SecretValue(holder.seed),
        "issuer_address": issuer.address,
        "module_id": "account_hygiene",
    }
    console, _ = _console()
    await handle_remove_trust_line(
        ModuleStep(
            text="",
            action="remove_trust_line",
            action_args={"currency": "HYGIENE"},
        ),
        state,
        transport,
        holder.seed,
        context,
        console,
    )
    lines = await transport.get_trust_lines(holder.address)
    assert not any(tl.currency == "HYGIENE" for tl in lines)


def test_issuer_wallet_json_roundtrip_still_loads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sanity: issuer file shape used by reuse tests is loadable."""
    monkeypatch.setenv("XRPL_LAB_HOME", str(tmp_path / ".xrpl-lab-home"))
    monkeypatch.chdir(tmp_path)
    w = wallet_mod.create_wallet()
    path = Path(".xrpl-lab") / "issuer_wallet.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    wallet_mod.save_wallet(w, path)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["address"] == w.address
