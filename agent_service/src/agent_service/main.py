"""FastAPI application entry point for the Mwalimu Agent Service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_service.config import settings
from agent_service.presentation.routes import router as runs_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    """Manage application startup and shutdown lifecycles."""
    logger.info(
        "Mwalimu Agent Service starting up. Environment=%s Provider=%s",
        settings.ENVIRONMENT,
        settings.DEFAULT_MODEL_PROVIDER,
    )
    yield
    logger.info("Mwalimu Agent Service shutting down.")


def create_app() -> FastAPI:
    """Application factory for the Mwalimu Agent Service."""
    app = FastAPI(
        title="Mwalimu Agent Service",
        description=(
            "Independent FastAPI agent execution runtime orchestrating cognitive "
            "reasoning loops, capability execution, and real-time SSE streaming."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check route
    @app.get("/health", tags=["Health"], summary="Service health check")
    async def health_check() -> dict[str, str]:
        return {
            "status": "healthy",
            "service": "mwalimu-agent-service",
            "environment": settings.ENVIRONMENT,
        }

    # Mount API routers
    app.include_router(runs_router)

    return app


app = create_app()
