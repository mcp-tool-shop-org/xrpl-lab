"""FastAPI application factory for XRPL Lab."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api.routes import router
from .api.runner_ws import _ALLOWED_ORIGINS
from .api.runner_ws import router as runner_ws_router

logger = logging.getLogger(__name__)

# Where the built Astro dashboard is mounted. The Astro site is built with
# ``base: '/xrpl-lab'`` (see site/astro.config.mjs), so the dist tree expects
# to be served under this prefix — the interactive dashboard lands at
# ``/xrpl-lab/app/``. The /api routes live outside this prefix, so there is no
# collision.
DASHBOARD_MOUNT_PATH = "/xrpl-lab"


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all so an unguarded route degrades to the structured envelope
    instead of Starlette's default 500 body (F-6beae9bb).

    Without this handler, ANY route that lets an exception escape (a
    UnicodeDecodeError from a bad-encoding file read, a future bug) falls
    through to Starlette's default ``{"detail": "Internal Server Error"}`` —
    a bare STRING, not the ``{code, message, hint}`` OBJECT every other
    error path in this API returns. The dashboard's error extraction
    (``site/src/lib/api.ts``: ``body?.detail?.message || body?.message``)
    assumes ``detail`` is an object, so that default shape silently yields
    an empty message instead of something a learner or facilitator can act
    on.

    This mirrors ``runner_ws._error_envelope``'s generic ``RUNTIME_INTERNAL``
    branch: full exception detail goes to the SERVER log only (never the
    client), and every unguarded route now degrades to the SAME envelope
    shape as every explicit ``HTTPException(detail={code,message,hint})``
    raised elsewhere in this module — so a client-side error handler has
    exactly one shape to parse, win or lose.

    Registering a handler for the bare ``Exception`` class does not change
    handling of ``HTTPException`` (FastAPI's built-in handler for it keeps
    matching first — Starlette dispatches to the most specific registered
    type), so every existing structured 4xx response is unaffected.
    """
    logger.error(
        "unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": "RUNTIME_INTERNAL",
                "message": (
                    "An internal server error occurred. This is a "
                    "server-side fault — not something you did wrong."
                ),
                "hint": (
                    "Note the request path and time, and notify the "
                    "workshop facilitator. They can check server logs to "
                    "diagnose."
                ),
            }
        },
    )


def create_app(
    dry_run: bool = False,
    dashboard_dir: Path | None = None,
    extra_origins: tuple[str, ...] = (),
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        dry_run: Default offline mode for runs (routes read it via
            ``request.app.state.dry_run``).
        dashboard_dir: When provided AND it is an existing directory, the
            built Astro dashboard at this path is mounted in-process so a
            single ``xrpl-lab serve`` hosts both the API and the dashboard.
            When ``None`` / missing, only the API is served (the dashboard is
            expected to run separately, e.g. the Astro dev server).
        extra_origins: Additional origins to add to the CORS + WebSocket
            allow-list. ``serve`` passes the in-process dashboard origin
            (``http://host:port``) here: when the dashboard is mounted on the
            API server, the browser's Origin on a WS upgrade is the API
            host:port rather than ``localhost:4321``, so it must be allowed.
    """
    app = FastAPI(
        title="XRPL Lab",
        version=__version__,
        description="XRPL Lab API — learn by doing, prove by artifact.",
    )

    # Store the dry_run preference so routes can read it via request.app.state.dry_run
    app.state.dry_run = dry_run

    # Effective allow-list: the shared base (single source of truth in
    # runner_ws._ALLOWED_ORIGINS) plus any serve-supplied extra origins. The
    # WS handler reads this off app.state so the HTTP CORS gate and the WS
    # Origin gate stay in lockstep.
    allowed_origins = tuple(_ALLOWED_ORIGINS) + tuple(extra_origins)
    app.state.allowed_origins = allowed_origins

    # CORS allow-list gates HTTP requests; the WS handshake is gated by the
    # same set in runner_ws. allow_credentials is EXPLICITLY False: there is
    # no cookie/session auth, and pairing credentials=True with wildcard
    # methods/headers would be unsafe (F-BRIDGE-A-002). Keep it False until a
    # real auth scheme lands, then gate the facilitator endpoints behind it
    # rather than CORS alone.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Catch-all so an unguarded route (or a future regression) degrades to
    # the structured envelope shape instead of Starlette's bare-string
    # default 500 body (F-6beae9bb). Registered on the FastAPI ``app``
    # instance (not the router) since Starlette wires an ``Exception``
    # handler into ``ServerErrorMiddleware`` at the application level.
    app.add_exception_handler(Exception, _unhandled_exception_handler)

    app.include_router(router)
    app.include_router(runner_ws_router)

    # Mount the built dashboard LAST so the /api routes and /docs are matched
    # first. html=True serves index.html for directory requests (Astro SSG
    # output), so /xrpl-lab/app/ resolves to the dashboard entry page.
    if dashboard_dir is not None and Path(dashboard_dir).is_dir():
        app.mount(
            DASHBOARD_MOUNT_PATH,
            StaticFiles(directory=str(dashboard_dir), html=True),
            name="dashboard",
        )

    return app


# Module-level app instance for uvicorn discovery (e.g. `uvicorn xrpl_lab.server:app`).
# Defaults to non-dry-run (testnet).  The CLI `serve` command creates its own
# app via create_app(dry_run=..., dashboard_dir=...) so this default only
# applies to bare uvicorn use (API only, no dashboard mount).
app = create_app()
