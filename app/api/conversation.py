"""순수 대화 엔드포인트 — FAQ RAG 미사용.

영어 회화 에이전트의 텍스트 채팅 진입점. 음성 통화(/voice/*)와 같은
ConversationService를 공유하므로, 세션 ID가 같다면 채팅·음성 간 대화 흐름이
이어진다 (단, 메모리는 프로세스 내 in-memory 라 재시작 시 초기화됨).

RAG/FAQ 기반 답변이 필요하면 /chat 엔드포인트를 쓸 것.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.models.schemas import ChatRequest, ChatResponse
from app.services.conversation_service import ConversationService, get_conversation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversation", tags=["conversation"])


@router.post("", response_model=ChatResponse)
def converse(
    request: ChatRequest,
    service: ConversationService = Depends(get_conversation_service),
) -> ChatResponse:
    try:
        return service.handle(request)
    except RuntimeError as exc:
        # Vertex 인증 등 구성 오류.
        logger.exception("conversation configuration error")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except Exception as exc:
        logger.exception("conversation unexpected error")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "internal error"
        ) from exc


@router.post("/stream")
async def converse_stream(
    request: ChatRequest,
    service: ConversationService = Depends(get_conversation_service),
) -> StreamingResponse:
    """Server-Sent Events 스트리밍 응답.

    각 청크: ``data: {"delta": "..."}\\n\\n``
    종료:   ``data: [DONE]\\n\\n``
    오류:   ``data: {"error": "..."}\\n\\n`` 후 [DONE]
    """

    async def event_stream():
        try:
            async for chunk in service.handle_stream(request):
                payload = json.dumps({"delta": chunk}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except Exception as exc:
            logger.exception("conversation stream failed")
            err = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"data: {err}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            # 프록시/브라우저가 버퍼링 안 하도록.
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def reset_session(
    session_id: str,
    service: ConversationService = Depends(get_conversation_service),
) -> None:
    service.reset_session(session_id)
