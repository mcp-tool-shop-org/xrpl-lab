"""FastAPI application factory for XRPL Lab."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api.routes import router
from .api.runner_ws import _ALLOWED_ORIGINS
from .api.runner_ws import router as runner_ws_router

# Where the built Astro dashboard is mounted. The Astro site is built with
# ``base: '/xrpl-lab'`` (see site/astro.config.mjs), so the dist tree expects
# to be served under this prefix — the interactive dashboard lands at
# ``/xrpl-lab/app/``. The /api routes live outside this prefix, so there is no
# collision.
DASHBOARD_MOUNT_PATH = "/xrpl-lab"


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
