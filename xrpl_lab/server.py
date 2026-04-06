"""FastAPI application factory for XRPL Lab."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api.routes import router
from .api.runner_ws import router as runner_ws_router


def create_app(dry_run: bool = False) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="XRPL Lab",
        version=__version__,
        description="XRPL Lab API — learn by doing, prove by artifact.",
    )

    # Store the dry_run preference so routes can read it via request.app.state.dry_run
    app.state.dry_run = dry_run

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:4321",
            "http://localhost:3000",
            "http://127.0.0.1:4321",
            "http://127.0.0.1:3000",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.include_router(runner_ws_router)

    return app


# Module-level app instance for uvicorn discovery (e.g. `uvicorn xrpl_lab.server:app`).
# Defaults to non-dry-run (testnet).  The CLI `serve` command creates its own
# app via create_app(dry_run=...) so this default only applies to bare uvicorn use.
app = create_app()
