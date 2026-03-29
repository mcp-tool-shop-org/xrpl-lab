"""FastAPI application factory for XRPL Lab."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api.routes import router
from .api.runner_ws import router as runner_ws_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="XRPL Lab",
        version=__version__,
        description="XRPL Lab API — learn by doing, prove by artifact.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.include_router(runner_ws_router)

    return app


# Module-level app instance for uvicorn (uvicorn xrpl_lab.server:app)
app = create_app()
