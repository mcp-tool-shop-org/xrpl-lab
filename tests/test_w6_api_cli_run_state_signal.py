"""Wave-6 api-cli Stage C — SEED-C-run-state.

API/WS payloads the dashboard consumes must make stalled / reconnecting /
dry-run / live distinguishable (status field, banner text, or equivalent).
api-cli owns the signal; dashboard owns the pixels. No JS runner.

Run in isolation:
    python -m pytest tests/test_w6_api_cli_run_state_signal.py -q
"""

from __future__ import annotations

from xrpl_lab.api import runner_ws
from xrpl_lab.api.runner_ws import (
    ModuleRunSession,
    _session_to_public_dict,
)

REQUIRED_SIGNALS = ("live", "dry-run", "stalled", "reconnecting")


def test_run_signal_banners_name_all_four_states() -> None:
    """Canonical signal map must name live, dry-run, stalled, reconnecting."""
    signals = getattr(runner_ws, "RUN_SIGNAL_BANNERS", None)
    assert isinstance(signals, dict), (
        "runner_ws must export RUN_SIGNAL_BANNERS mapping the four run states "
        "to learner-facing banner text (dashboard owns pixels; api-cli owns signal)"
    )
    for key in REQUIRED_SIGNALS:
        assert key in signals, f"missing signal key {key!r} in RUN_SIGNAL_BANNERS"
        assert isinstance(signals[key], str) and signals[key].strip(), (
            f"banner for {key!r} must be non-empty text"
        )
    # Banners must be distinguishable from each other.
    values = [signals[k] for k in REQUIRED_SIGNALS]
    assert len(set(values)) == len(REQUIRED_SIGNALS), (
        f"run-state banners must be pairwise distinct, got {values!r}"
    )


def test_public_session_dict_exposes_mode_and_signal_for_dry_run() -> None:
    """GET /api/runs projection: dry-run session carries mode + banners."""
    session = ModuleRunSession(
        run_id="rs-dry-1",
        module_id="receipt_literacy",
        dry_run=True,
    )
    public = _session_to_public_dict(session)
    assert public.get("dry_run") is True
    assert public.get("mode") == "dry-run", (
        f"dry-run session must expose mode='dry-run', got {public.get('mode')!r}"
    )
    assert "mode_banner" in public and public["mode_banner"], (
        "public dict must include non-empty mode_banner"
    )
    assert "dry" in public["mode_banner"].lower() or "sandbox" in public["mode_banner"].lower()
    signals = public.get("signals")
    assert isinstance(signals, dict)
    for key in REQUIRED_SIGNALS:
        assert key in signals and signals[key]


def test_public_session_dict_exposes_mode_live() -> None:
    """Live (testnet) session must expose mode='live', not collapse into dry-run."""
    session = ModuleRunSession(
        run_id="rs-live-1",
        module_id="receipt_literacy",
        dry_run=False,
    )
    public = _session_to_public_dict(session)
    assert public.get("dry_run") is False
    assert public.get("mode") == "live"
    assert "mode_banner" in public and public["mode_banner"]
    assert "live" in public["mode_banner"].lower() or "testnet" in public["mode_banner"].lower()


def test_build_run_state_frame_distinguishes_modes() -> None:
    """WS run_state frame must carry type, mode, connection, banners, signals."""
    build = getattr(runner_ws, "_build_run_state_frame", None)
    assert callable(build), (
        "runner_ws must expose _build_run_state_frame(session) for the WS "
        "handshake / ping path so the dashboard can read mode without inventing it"
    )
    dry = ModuleRunSession(run_id="a", module_id="m", dry_run=True)
    live = ModuleRunSession(run_id="b", module_id="m", dry_run=False)
    dry.ws_attached = True
    live.ws_attached = True

    dry_frame = build(dry)
    live_frame = build(live)

    assert dry_frame["type"] == "run_state"
    assert live_frame["type"] == "run_state"
    assert dry_frame["mode"] == "dry-run"
    assert live_frame["mode"] == "live"
    assert dry_frame["connection"] == "live"
    assert live_frame["connection"] == "live"
    assert dry_frame["mode_banner"] != live_frame["mode_banner"]
    for frame in (dry_frame, live_frame):
        for key in REQUIRED_SIGNALS:
            assert key in frame["signals"]


def test_build_ping_frame_carries_mode() -> None:
    """Keepalive ping must carry mode so a quiet dry-run is still distinguishable."""
    build_ping = getattr(runner_ws, "_build_ping_frame", None)
    assert callable(build_ping), (
        "runner_ws must expose _build_ping_frame(session) so ping frames "
        "carry mode/connection instead of bare {type: ping}"
    )
    session = ModuleRunSession(run_id="p1", module_id="m", dry_run=True)
    session.ws_attached = True
    frame = build_ping(session)
    assert frame["type"] == "ping"
    assert frame["mode"] == "dry-run"
    assert frame["connection"] == "live"


def test_run_info_schema_includes_mode_fields() -> None:
    """RunInfo pydantic model must accept the new signal fields."""
    from xrpl_lab.api.schemas import RunInfo

    fields = set(RunInfo.model_fields)
    for required in ("mode", "mode_banner", "signals", "connection"):
        assert required in fields, (
            f"RunInfo missing {required!r} — GET /api/runs must survive refresh "
            f"with dry-run/live signal (have {sorted(fields)})"
        )
