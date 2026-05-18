"""음성 통화용 순수 대화 서비스.

ChatService(RAG)와 분리:
  - ChatService : 벡터 검색 + 랭킹 + LLM. /chat HTTP, 그리고 통화 종료 후 분석에서 사용.
  - ConversationService : RAG 없이 LLM.chat() 만 호출. 실시간 음성 통화에서 사용.

세션 메모리는 보관하지만 답변 캐시는 사용하지 않는다 (대화의 매 턴은 컨텍스트 의존).
"""

from __future__ import annotations

import logging
from typing import AsyncIterator, Optional

from app.core.characters import get_character
from app.core.config import Settings, get_settings
from app.core.llm import LLMClient
from app.core.memory import ConversationMemory
from app.models.schemas import ChatRequest, ChatResponse
from app.utils.streaming import bridge_sync_to_async

logger = logging.getLogger(__name__)


class ConversationService:
    """음성 통화에서 한 턴씩 LLM에 묻는 얇은 오케스트레이션."""

    def __init__(
        self,
        settings: Settings | None = None,
        llm: LLMClient | None = None,
        memory: ConversationMemory | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._memory = memory or ConversationMemory(self._settings)

        # 스텁 모드에선 LLM 초기화도 건너뛴다 (Vertex 인증 없이 음성 흐름 테스트용).
        if self._settings.chat_stub_response is not None:
            logger.warning(
                "ConversationService running in STUB MODE — 모든 답변이 고정 문구로 반환됩니다."
            )
            self._llm = None  # type: ignore[assignment]
            return

        self._llm = llm or LLMClient(self._settings)

    def handle(self, request: ChatRequest) -> ChatResponse:
        if self._settings.chat_stub_response is not None:
            answer = self._settings.chat_stub_response
            self._memory.add_turn(request.session_id, request.message, answer)
            return ChatResponse(
                session_id=request.session_id,
                answer=answer,
                sources=[],
                used_cache=False,
            )

        character = get_character(request.character_id)
        history = self._memory.get_history(request.session_id)
        answer = self._llm.chat(
            request.message, history=history, system_prompt=character.system_prompt
        )
        self._memory.add_turn(request.session_id, request.message, answer)
        return ChatResponse(
            session_id=request.session_id,
            answer=answer,
            sources=[],
            used_cache=False,
        )

    def reset_session(self, session_id: str) -> None:
        self._memory.clear(session_id)

    async def handle_stream(self, request: ChatRequest) -> AsyncIterator[str]:
        """LLM 응답을 청크 단위로 yield 한다 (SSE/스트리밍 응답용)."""
        if self._settings.chat_stub_response is not None:
            answer = self._settings.chat_stub_response
            self._memory.add_turn(request.session_id, request.message, answer)
            yield answer
            return

        character = get_character(request.character_id)
        history = self._memory.get_history(request.session_id)
        accumulated: list[str] = []
        try:
            async for chunk in bridge_sync_to_async(
                lambda: self._llm.chat_stream(
                    request.message,
                    history=history,
                    system_prompt=character.system_prompt,
                )
            ):
                accumulated.append(chunk)
                yield chunk
        finally:
            # 메모리 갱신 — 부분 응답이라도 그대로 저장(연결 끊겨도 컨텍스트 유지).
            if accumulated:
                self._memory.add_turn(
                    request.session_id, request.message, "".join(accumulated)
                )


# 모듈 단위 싱글톤 (FastAPI 의존성 주입에서 재사용).
_service: Optional[ConversationService] = None


def get_conversation_service() -> ConversationService:
    global _service
    if _service is None:
        _service = ConversationService()
    return _service
