"""학습 도구 엔드포인트 — 번역, 한→영 표현 가이드.

스트리밍(SSE) 만 노출. 응답 길이가 짧아 한 번에 받아도 되지만 UX(글자가 흐르는 느낌)
를 위해 동일 인터페이스를 통일.

엔드포인트:
  POST /tools/translate/stream  body: {text}
  POST /tools/phrasing/stream   body: {korean_text}
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.models.schemas import DictionaryRequest, PhrasingRequest, TranslateRequest
from app.services.tools_service import LearningToolsService, get_learning_tools_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["tools"])


def _sse(generator) -> StreamingResponse:
    """공통 SSE 응답 래퍼 — error/done 프레임 일관 처리."""

    async def event_stream():
        try:
            async for chunk in generator:
                payload = json.dumps({"delta": chunk}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except Exception as exc:
            logger.exception("tool stream failed")
            err = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"data: {err}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/translate/stream")
async def translate_stream(
    request: TranslateRequest,
    service: LearningToolsService = Depends(get_learning_tools_service),
) -> StreamingResponse:
    try:
        return _sse(service.translate_stream(request.text))
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


@router.post("/phrasing/stream")
async def phrasing_stream(
    request: PhrasingRequest,
    service: LearningToolsService = Depends(get_learning_tools_service),
) -> StreamingResponse:
    try:
        return _sse(service.explain_phrasing_stream(request.korean_text))
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


@router.post("/dictionary/stream")
async def dictionary_stream(
    request: DictionaryRequest,
    service: LearningToolsService = Depends(get_learning_tools_service),
) -> StreamingResponse:
    try:
        return _sse(service.lookup_word_stream(request.word, context=request.context))
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
