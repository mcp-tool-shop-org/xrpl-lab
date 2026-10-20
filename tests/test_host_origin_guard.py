"""F10: the Host and Origin guards on the HTTP API (xrpl_lab/api/guards.py).

CORS stops a cross-origin page from reading a response, not from sending a
simple request. ``POST /api/run/{module_id}`` takes no body, so before this
guard a cross-site ``no-cors`` POST from any page started a run. A rebinding
domain (one that re-resolves to 127.0.0.1) is same-origin to the browser and
gets past CORS entirely; the Host gate closes it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from xrpl_lab.api import runner_ws
from xrpl_lab.api.guards import host_of
from xrpl_lab.server import create_app

EVIL = "https://evil.example"


def _client(**kwargs) -> TestClient:
    return TestClient(create_app(dry_run=True, **kwargs))


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("localhost:8321", "localhost"),
        ("127.0.0.1", "127.0.0.1"),
        ("[::1]:8321", "::1"),
        ("[::1]", "::1"),
        ("EVIL.example:80", "evil.example"),
        ("", ""),
    ],
)
def test_host_of_strips_port_and_brackets(header: str, expected: str) -> None:
    assert host_of(header) == expected


# ── Origin gate ──────────────────────────────────────────────────────


def test_cross_site_post_to_start_run_is_refused_and_starts_nothing() -> None:
    client = _client()
    before = len(runner_ws._sessions)
    resp = client.post("/api/run/amm_liquidity_101", headers={"origin": EVIL})
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "ORIGIN_REJECTED"
    assert len(runner_ws._sessions) == before


@pytest.mark.parametrize("origin", [EVIL, "null", "http://localhost:9999"])
def test_state_changing_methods_refuse_a_disallowed_origin(origin: str) -> None:
    client = _client()
    resp = client.delete("/api/runs/no-such-run", headers={"origin": origin})
    assert resp.status_code == 403
    body = resp.json()["detail"]
    assert body["code"] == "ORIGIN_REJECTED"
    assert body["message"] and body["hint"]


def test_missing_origin_is_allowed() -> None:
    """The CLI and curl send no Origin; the request reaches the route."""
    resp = _client().delete("/api/runs/no-such-run")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "RUN_NOT_FOUND"


def test_allowed_origin_reaches_the_route() -> None:
    resp = _client().delete(
        "/api/runs/no-such-run", headers={"origin": "http://localhost:4321"}
    )
    assert resp.status_code == 404


def test_serve_origin_from_extra_origins_is_allowed() -> None:
    client = _client(extra_origins=("http://localhost:8321",))
    resp = client.delete(
        "/api/runs/no-such-run", headers={"origin": "http://localhost:8321"}
    )
    assert resp.status_code == 404


def test_reads_are_not_origin_gated() -> None:
    resp = _client().get("/api/health", headers={"origin": EVIL})
    assert resp.status_code == 200


# ── Host gate ────────────────────────────────────────────────────────


def test_rebinding_host_is_refused_even_for_reads() -> None:
    resp = _client().get("/api/health", headers={"host": "evil.example"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "HOST_REJECTED"


@pytest.mark.parametrize("host", ["localhost:8321", "127.0.0.1:8321", "[::1]:8321"])
def test_loopback_hosts_are_allowed(host: str) -> None:
    resp = _client().get("/api/health", headers={"host": host})
    assert resp.status_code == 200


def test_lan_bind_host_is_added_to_the_allow_list() -> None:
    client = _client(bind_host="192.168.1.5")
    assert client.get("/api/health", headers={"host": "192.168.1.5:8321"}).status_code == 200
    assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 400


@pytest.mark.parametrize("bind", ["0.0.0.0", "::"])
def test_wildcard_bind_turns_the_host_gate_off_but_keeps_the_origin_gate(bind: str) -> None:
    client = _client(bind_host=bind)
    assert client.get("/api/health", headers={"host": "my-laptop.lan:8321"}).status_code == 200
    resp = client.post(
        "/api/run/amm_liquidity_101",
        headers={"host": "my-laptop.lan:8321", "origin": EVIL},
    )
    assert resp.status_code == 403


def test_websocket_with_a_rebinding_host_is_refused() -> None:
    client = _client()
    with (
        pytest.raises(WebSocketDisconnect) as exc,
        client.websocket_connect(
            "/api/run/amm_liquidity_101/ws?run_id=x",
            headers={"host": "evil.example", "origin": "http://localhost:4321"},
        ),
    ):
        pass
    assert exc.value.code == 4003
