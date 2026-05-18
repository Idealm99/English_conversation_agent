"""채팅 엔드포인트."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.schemas import ChatRequest, ChatResponse
from app.services.chat_service import ChatService, get_chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    try:
        return service.handle(request)
    except RuntimeError as exc:
        # 환경 변수 미설정 등 구성 오류.
        logger.exception("chat configuration error")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except Exception as exc:
        logger.exception("chat unexpected error")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "internal error"
        ) from exc


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def reset_session(
    session_id: str,
    service: ChatService = Depends(get_chat_service),
) -> None:
    service.reset_session(session_id)
