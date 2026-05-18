"""FastAPI 진입점."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.characters import router as characters_router
from app.api.chat import router as chat_router
from app.api.conversation import router as conversation_router
from app.api.devices import router as devices_router
from app.api.notifications import router as notifications_router
from app.api.tools import router as tools_router
from app.api.voice import router as voice_router
from app.core.config import get_settings
from app.models.schemas import HealthResponse

STATIC_DIR = Path(__file__).parent / "static"


def _configure_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def create_app() -> FastAPI:
    settings = get_settings()
    _configure_logging(settings.debug)

    app = FastAPI(title=settings.app_name, version=settings.version)
    app.include_router(chat_router)
    app.include_router(conversation_router)
    app.include_router(tools_router)
    app.include_router(characters_router)
    app.include_router(devices_router)
    app.include_router(notifications_router)
    app.include_router(voice_router)

    @app.get("/health", response_model=HealthResponse, tags=["meta"])
    def health() -> HealthResponse:
        return HealthResponse(version=settings.version)

    # 정적 채팅 페이지 — /web/ 로 접속.
    if STATIC_DIR.exists():
        app.mount(
            "/web",
            StaticFiles(directory=str(STATIC_DIR), html=True),
            name="web",
        )

    return app


app = create_app()
