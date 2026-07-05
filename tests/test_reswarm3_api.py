"""Re-swarm 3 (Stage A AMEND) API regression tests.

Covers the HIGH/MED/LOW findings assigned to the Stage-A AMEND agent that are
unit-testable in Python against the FastAPI app:

* **AW-001** — POST /api/verify?live=true looped SEQUENTIALLY over every pasted
  claim with NO claim cap and NO request-body-size limit → unbounded outbound
  XRPL RPC amplification / worker exhaustion (LAN-reachable on
  ``serve --host 0.0.0.0``). The route now (a) rejects an oversized request
  body with a structured 400, and (b) rejects a live request whose pasted pack
  claims more txids than any real curriculum with a structured 400 — BEFORE any
  outbound work. The offline hash layer is untouched.

* **AW-003** — same endpoint is gated only by browser-CORS. The AW-001 caps are
  the primary mitigation; additionally, ONLY the ``live`` path performs outbound
  work and it is bounded by the same caps. Covered by the AW-001 tests below
  (a non-live request never touches the network and is never claim-capped).

* **AW-005** — ``live`` coercion was asymmetric: the query param accepted
  1/true/yes/on but the body key required a literal JSON ``true`` (so a pasted
  ``"live": "true"`` string was silently treated as false). Both paths now run
  through the SAME coercion helper.

These tests must not weaken any verified-held behaviour; they only add coverage
for the fixes above. Run in isolation:

    python -m pytest tests/test_reswarm3_api.py -q
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xrpl_lab.api.routes import (
    _MAX_LIVE_CLAIMS,
    _MAX_VERIFY_BODY_BYTES,
    _coerce_live,
)
from xrpl_lab.server import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with state + workspace redirected to a temp dir."""
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_WORKSPACE_DIR", ws)
    monkeypatch.setattr("xrpl_lab.reporting.get_workspace_dir", lambda: ws)
    monkeypatch.setattr("xrpl_lab.api.routes.get_workspace_dir", lambda: ws)
    return TestClient(create_app())


def _hashed_pack(pack: dict) -> dict:
    """Attach the correct SHA-256 so the offline hash layer PASSES.

    Mirrors reporting.generate_proof_pack: hash the pack (without the hash
    field) using sorted-keys compact JSON, then set ``sha256``.
    """
    body = {k: v for k, v in pack.items() if k != "sha256"}
    content = json.dumps(body, sort_keys=True, separators=(",", ":"))
    body["sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return body


def _minimal_pack(n_tx: int = 0, *, network: str = "dry-run") -> dict:
    """A structurally-valid proof pack with ``n_tx`` transaction claims."""
    txs = [
        {"txid": f"{i:064X}", "network": network, "tx_type": "Payment"}
        for i in range(n_tx)
    ]
    pack = {
        "xrpl_lab_proof_pack": True,
        "version": "2.2.0",
        "network": network,
        "address": "rTESTaddress0000000000000000000",
        "completed_modules": [],
        "transactions": txs,
    }
    return _hashed_pack(pack)


# ── AW-001: request-body-size cap ─────────────────────────────────────


class TestVerifyBodySizeCap:
    def test_oversized_body_is_rejected_with_structured_400(
        self, client: TestClient
    ) -> None:
        # A body comfortably over the cap — pad a benign string field.
        padding = "x" * (_MAX_VERIFY_BODY_BYTES + 1024)
        body = {"xrpl_lab_proof_pack": True, "junk": padding}
        raw = json.dumps(body).encode("utf-8")
        assert len(raw) > _MAX_VERIFY_BODY_BYTES

        resp = client.post(
            "/api/verify?live=true",
            content=raw,
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["code"] == "BODY_TOO_LARGE"
        assert "code" in detail and "message" in detail and "hint" in detail

    def test_normal_small_pack_is_not_size_capped(self, client: TestClient) -> None:
        # A tiny, valid, dry-run pack verifies fine (hash passes, no live work).
        pack = _minimal_pack(0)
        resp = client.post("/api/verify", json=pack)
        assert resp.status_code == 200
        data = resp.json()
        assert data["artifact_kind"] == "proof_pack"
        assert data["hash_valid"] is True


# ── AW-001: live-claim cap ────────────────────────────────────────────


class TestVerifyClaimCap:
    def test_too_many_live_claims_is_rejected_with_structured_400(
        self, client: TestClient
    ) -> None:
        # More claims than any real curriculum — must be rejected BEFORE the
        # sequential outbound loop runs (no network calls, structured 400).
        pack = _minimal_pack(_MAX_LIVE_CLAIMS + 1, network="testnet")
        resp = client.post("/api/verify?live=true", json=pack)
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["code"] == "TOO_MANY_CLAIMS"
        assert "code" in detail and "message" in detail and "hint" in detail

    def test_claim_cap_does_not_block_offline_verification(
        self, client: TestClient
    ) -> None:
        # The SAME oversized pack, verified OFFLINE (no ?live), must NOT be
        # claim-capped — the cap only guards the outbound live path. The hash
        # layer runs and passes.
        pack = _minimal_pack(_MAX_LIVE_CLAIMS + 1, network="testnet")
        resp = client.post("/api/verify", json=pack)
        assert resp.status_code == 200
        assert resp.json()["hash_valid"] is True

    def test_small_live_pack_within_cap_is_accepted(self, client: TestClient) -> None:
        # A dry-run pack under the cap passes the guards; live verification runs
        # but finds no on-ledger anchors (all dry-run) — 200, hash valid.
        pack = _minimal_pack(3, network="dry-run")
        resp = client.post("/api/verify?live=true", json=pack)
        assert resp.status_code == 200
        data = resp.json()
        assert data["hash_valid"] is True
        assert data["live_requested"] is True


# ── AW-005: symmetric ``live`` coercion ───────────────────────────────


class TestLiveCoercion:
    @pytest.mark.parametrize(
        "value",
        ["1", "true", "TRUE", "yes", "on", True],
    )
    def test_truthy_values_coerce_to_true(self, value) -> None:
        assert _coerce_live(value) is True

    @pytest.mark.parametrize(
        "value",
        ["0", "false", "no", "off", "", None, False, 0],
    )
    def test_falsy_values_coerce_to_false(self, value) -> None:
        assert _coerce_live(value) is False

    def test_body_string_true_is_honoured_like_query_param(
        self, client: TestClient
    ) -> None:
        # Regression: a pasted pack with ``"live": "true"`` (string) used to be
        # treated as False (only literal JSON true worked). It must now be
        # coerced the SAME way the ?live=true query param is.
        pack = _minimal_pack(0, network="dry-run")
        pack["live"] = "true"
        pack = _hashed_pack(pack)  # re-hash so the added key doesn't break hash
        resp = client.post("/api/verify", json=pack)
        assert resp.status_code == 200
        assert resp.json()["live_requested"] is True


# ── AW-004: list_reports must not inline unbounded content ────────────


class TestListReportsBounded:
    def test_many_large_reports_are_capped(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        # Write more + larger reports than the caps allow; the endpoint must
        # cap the count AND truncate oversized per-report content rather than
        # streaming everything back inline.
        from xrpl_lab.api.routes import (
            _MAX_REPORT_CONTENT_BYTES,
            _MAX_REPORTS_INLINE,
        )

        reports_dir = tmp_path / "ws" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        big = "A" * (_MAX_REPORT_CONTENT_BYTES + 5000)
        for i in range(_MAX_REPORTS_INLINE + 10):
            (reports_dir / f"report_{i:03d}.md").write_text(big, encoding="utf-8")

        resp = client.get("/api/artifacts/reports")
        assert resp.status_code == 200
        data = resp.json()
        # Count is capped.
        assert len(data) <= _MAX_REPORTS_INLINE
        # Each inlined report's content is bounded.
        for r in data:
            assert len(r["content"].encode("utf-8")) <= _MAX_REPORT_CONTENT_BYTES + 256
