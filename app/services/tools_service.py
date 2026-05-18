"""학습 도구 서비스 — 번역, 한→영 표현 가이드.

대화 서비스와 분리(SRP): 메모리/세션 없음, 캐시 없음, RAG 없음.
LLMClient의 학습 도구 모드(translate / explain_phrasing)를 얇게 감싼다.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator, Optional

from app.core.config import Settings, get_settings
from app.core.llm import LLMClient
from app.services.dictionary_api import fetch_dictionary_entry, format_entry_for_llm
from app.utils.streaming import bridge_sync_to_async

logger = logging.getLogger(__name__)


_STUB_TRANSLATION = "(스텁) 번역 결과 자리입니다."
_STUB_PHRASING = (
    "(스텁) 영어 표현 가이드 자리입니다.\n\n"
    "1) 캐주얼 — \"Hi.\"\n"
    "2) 포멀 — \"Good morning.\"\n"
)
_STUB_DICTIONARY = (
    "(스텁) 사전 결과 자리입니다.\n\n"
    "1) 발음\n   IPA: /…/\n   한글 발음: …\n\n"
    "2) 뜻\n   여기에 학습자용 뜻 풀이가 들어갑니다.\n"
)


class LearningToolsService:
    """번역/표현 가이드 한 단위씩 처리."""

    def __init__(
        self,
        settings: Settings | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        # 스텁 모드에선 외부 호출 없이 고정 문구.
        if self._settings.chat_stub_response is not None:
            logger.warning(
                "LearningToolsService running in STUB MODE — 모든 응답이 고정 문구입니다."
            )
            self._llm = None  # type: ignore[assignment]
            return
        self._llm = llm or LLMClient(self._settings)

    # --- non-streaming (간단한 호출) ---

    def translate(self, text: str) -> str:
        if self._llm is None:
            return _STUB_TRANSLATION
        return self._llm.translate(text)

    def explain_phrasing(self, korean_text: str) -> str:
        if self._llm is None:
            return _STUB_PHRASING
        return self._llm.explain_phrasing(korean_text)

    def lookup_word(self, word: str, context: str | None = None) -> str:
        if self._llm is None:
            return _STUB_DICTIONARY
        return self._llm.lookup_word(word, context)

    # --- streaming (SSE 용) ---

    async def translate_stream(self, text: str) -> AsyncIterator[str]:
        if self._llm is None:
            yield _STUB_TRANSLATION
            return
        async for chunk in bridge_sync_to_async(lambda: self._llm.translate_stream(text)):
            yield chunk

    async def explain_phrasing_stream(self, korean_text: str) -> AsyncIterator[str]:
        if self._llm is None:
            yield _STUB_PHRASING
            return
        async for chunk in bridge_sync_to_async(
            lambda: self._llm.explain_phrasing_stream(korean_text)
        ):
            yield chunk

    async def lookup_word_stream(
        self, word: str, context: str | None = None
    ) -> AsyncIterator[str]:
        """사전 조회 — Free Dictionary API 우선, miss 시 LLM-only fallback."""
        if self._llm is None:
            yield _STUB_DICTIONARY
            return

        # 1) Free Dictionary API 시도 (5초 timeout, 실패시 None).
        entry = await fetch_dictionary_entry(word)

        if entry:
            # 2) hit — 사전 데이터를 ground truth 로 LLM에 한국어 해설 요청.
            dict_text = format_entry_for_llm(entry)
            logger.info("dictionary hit: word=%r → %d bytes of dict data", word, len(dict_text))
            async for chunk in bridge_sync_to_async(
                lambda: self._llm.explain_dictionary_entry_stream(word, dict_text, context)
            ):
                yield chunk
            return

        # 3) miss — 구문/숙어/오타 등. LLM-only 로 폴백.
        logger.info("dictionary miss: word=%r → falling back to LLM-only", word)
        async for chunk in bridge_sync_to_async(
            lambda: self._llm.lookup_word_stream(word, context)
        ):
            yield chunk


# 모듈 단위 싱글톤 (FastAPI 의존성 주입에서 재사용).
_service: Optional[LearningToolsService] = None


def get_learning_tools_service() -> LearningToolsService:
    global _service
    if _service is None:
        _service = LearningToolsService()
    return _service
