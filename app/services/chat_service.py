"""채팅 오케스트레이션 서비스.

흐름: 캐시 확인 → 검색 → 리랭킹 → LLM 응답 → 캐시 저장 → 메모리 갱신.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.core.config import Settings, get_settings
from app.core.embeddings import EmbeddingClient
from app.core.llm import LLMClient
from app.core.memory import ConversationMemory
from app.models.schemas import ChatRequest, ChatResponse, FAQHit
from app.services.ranker import Ranker
from app.services.retriever import Retriever
from app.services.vector_store import VectorStore
from app.utils.cache import AnswerCache
from app.utils.text_processing import hash_key, normalize_query

logger = logging.getLogger(__name__)


class ChatService:
    """전체 파이프라인을 구성하고 호출 단위로 실행."""

    def __init__(
        self,
        settings: Settings | None = None,
        retriever: Retriever | None = None,
        ranker: Ranker | None = None,
        llm: LLMClient | None = None,
        memory: ConversationMemory | None = None,
        cache: AnswerCache | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._memory = memory or ConversationMemory(self._settings)

        # 스텁 모드: Vertex/Chroma 초기화를 건너뛴다. handle()에서 고정 응답 반환.
        if self._settings.chat_stub_response is not None:
            logger.warning(
                "ChatService running in STUB MODE — 모든 답변이 고정 문구로 반환됩니다."
            )
            self._retriever = None  # type: ignore[assignment]
            self._ranker = None  # type: ignore[assignment]
            self._llm = None  # type: ignore[assignment]
            self._cache = cache or AnswerCache(self._settings)
            return

        # 명시적 주입이 없으면 기본 컴포넌트를 lazy-init.
        if retriever is None:
            embedder = EmbeddingClient(self._settings)
            store = VectorStore(self._settings, embedder=embedder)
            retriever = Retriever(store, self._settings)
        self._retriever = retriever
        self._ranker = ranker or Ranker(self._settings)
        self._llm = llm or LLMClient(self._settings)
        self._cache = cache or AnswerCache(self._settings)

    def _cache_key(self, message: str) -> str:
        return hash_key(
            self._settings.llm_model,
            self._settings.embedding_model,
            normalize_query(message),
        )

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

        cache_key = self._cache_key(request.message)
        cached = self._cache.get(cache_key)
        if cached:
            logger.info("cache hit session=%s", request.session_id)
            return ChatResponse(
                session_id=request.session_id,
                answer=cached["answer"],
                sources=[FAQHit(**hit) for hit in cached.get("sources", [])],
                used_cache=True,
            )

        # 검색 + 랭킹.
        raw_hits = self._retriever.search(request.message, top_k=self._settings.retrieval_top_k)
        ranked: list[FAQHit] = self._ranker.rerank(request.message, raw_hits)

        # LLM 호출.
        history = self._memory.get_history(request.session_id)
        answer = self._llm.answer(request.message, ranked, history=history)

        # 사이드이펙트: 메모리 + 캐시 업데이트.
        self._memory.add_turn(request.session_id, request.message, answer)
        self._cache.set(
            cache_key,
            {
                "answer": answer,
                "sources": [hit.model_dump(mode="json") for hit in ranked],
            },
        )

        return ChatResponse(
            session_id=request.session_id,
            answer=answer,
            sources=ranked,
            used_cache=False,
        )

    def reset_session(self, session_id: str) -> None:
        self._memory.clear(session_id)


# 모듈 단위 싱글톤 (FastAPI 의존성 주입에서 재사용).
_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    global _service
    if _service is None:
        _service = ChatService()
    return _service
