"""Host and Origin guards for the HTTP API (F10).

``xrpl-lab serve`` has no authentication: CORS and the WebSocket Origin gate
are its only boundary. CORS alone leaves two holes on the HTTP side.

* **Simple-request CSRF.** CORS stops a cross-origin page from *reading* a
  response, not from *sending* the request. ``POST /api/run/{module_id}`` takes
  no body, so a plain cross-site ``fetch(..., {method: "POST", mode: "no-cors"})``
  from any page the learner opens would start a run, live on testnet unless
  serve ran with ``--dry-run``. The Origin gate rejects a state-changing
  request whose ``Origin`` is present and not on the allow-list. A missing
  Origin is allowed: browsers always send it on a cross-origin POST, so its
  absence means a non-browser client (the CLI, curl, a test).
* **DNS rebinding.** A hostile domain that re-resolves to 127.0.0.1 becomes
  same-origin to the browser, so its requests carry ``Origin`` and ``Host``
  of the hostile domain. The Host gate rejects any ``Host`` not on the
  allow-list, which closes reads as well as writes.

Starlette ships ``TrustedHostMiddleware``, but it cuts the Host header at the
first ``:``, which turns the IPv6 loopback ``[::1]:8321`` into ``[``, and it
answers in plain text. This guard parses bracketed IPv6 and answers with the
same ``{code, message, hint}`` envelope as every other API error.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

# Hosts every app accepts. ``testserver`` is the Host that Starlette's
# TestClient sends.
DEFAULT_ALLOWED_HOSTS: tuple[str, ...] = ("localhost", "127.0.0.1", "::1", "testserver")

# Bind addresses that listen on every interface. A request to such a server
# may arrive under any of the machine's names or addresses, so the Host gate
# can't enumerate them and stands down; the Origin gate still applies.
WILDCARD_BINDS: frozenset[str] = frozenset({"0.0.0.0", "::", ""})

STATE_CHANGING_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def host_of(host_header: str) -> str:
    """Return the hostname from a Host header, without the port.

    ``[::1]:8321`` -> ``::1``; ``localhost:8321`` -> ``localhost``.
    """
    value = host_header.strip().lower()
    if value.startswith("["):
        end = value.find("]")
        return value[1:end] if end != -1 else value
    if value.count(":") == 1:
        return value.split(":", 1)[0]
    return value


class HostOriginGuard:
    """Pure ASGI middleware: the Host gate for every request, the Origin gate
    for state-changing HTTP methods. WebSocket upgrades get the Host gate
    only; their Origin is checked in ``runner_ws.run_websocket``."""

    def __init__(
        self,
        app: ASGIApp,
        allowed_origins: Iterable[str],
        allowed_hosts: Iterable[str] | None = None,
    ) -> None:
        self.app = app
        self.allowed_origins = frozenset(allowed_origins)
        # None means a wildcard bind: no Host gate.
        self.allowed_hosts = (
            None if allowed_hosts is None else frozenset(h.lower() for h in allowed_hosts)
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)

        if self.allowed_hosts is not None:
            host = host_of(headers.get("host", ""))
            if host not in self.allowed_hosts:
                await self._reject(
                    scope, receive, send,
                    status=400,
                    code="HOST_REJECTED",
                    message=f"Host {host!r} is not one this server answers to.",
                    hint=(
                        "Open the dashboard at http://localhost:<port>/ or "
                        "http://127.0.0.1:<port>/. If you bound serve to a LAN "
                        "address, use that address."
                    ),
                )
                return

        if scope["type"] == "http" and scope["method"] in STATE_CHANGING_METHODS:
            origin = headers.get("origin")
            if origin is not None and origin not in self.allowed_origins:
                await self._reject(
                    scope, receive, send,
                    status=403,
                    code="ORIGIN_REJECTED",
                    message=f"Requests from origin {origin!r} can't change server state.",
                    hint=(
                        "Use the XRPL Lab dashboard, or call the API from the CLI "
                        "or curl, which send no Origin header."
                    ),
                )
                return

        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(
        scope: Scope, receive: Receive, send: Send,
        *, status: int, code: str, message: str, hint: str,
    ) -> None:
        if scope["type"] == "websocket":
            # Refuse the handshake; RFC 6455 policy-violation code.
            await send({"type": "websocket.close", "code": 4003, "reason": code})
            return
        body = json.dumps(
            {"detail": {"code": code, "message": message, "hint": hint}}
        ).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({"type": "http.response.body", "body": body})
