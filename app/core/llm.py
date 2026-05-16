"""Vertex AI Gemini 래퍼.

검색된 FAQ를 컨텍스트로 받아 사용자 질문에 답하도록 프롬프트를 구성한다.
시스템 지시는 GenerativeModel(system_instruction=...) 로 분리해서 전달한다.
"""

from __future__ import annotations

import logging
from typing import Iterable

from vertexai.generative_models import Content, GenerationConfig, GenerativeModel, Part

from app.core.config import Settings, get_settings
from app.core.embeddings import _ensure_vertex_initialized
from app.models.schemas import FAQHit

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """당신은 친절한 FAQ 어시스턴트입니다.
규칙:
1. 반드시 제공된 'FAQ 컨텍스트' 안의 정보만 근거로 답변합니다.
2. 컨텍스트가 질문과 무관하거나 부족하면 '해당 내용은 자료에서 찾을 수 없습니다.'라고 답합니다.
3. 답변은 한국어로, 핵심을 먼저 1~3문장으로 요약한 뒤 필요한 경우에만 부연합니다.
4. 추측하거나 외부 지식을 끌어오지 않습니다.
"""


def format_context(hits: Iterable[FAQHit]) -> str:
    """검색된 FAQ들을 LLM이 읽기 좋은 형태로 직렬화."""
    blocks: list[str] = []
    for idx, hit in enumerate(hits, start=1):
        blocks.append(
            f"[FAQ {idx}] (id={hit.faq_id}, score={hit.score:.3f})\n"
            f"Q: {hit.question}\n"
            f"A: {hit.answer}"
        )
    return "\n\n".join(blocks) if blocks else "(검색 결과 없음)"


def _history_to_contents(history: list[dict[str, str]]) -> list[Content]:
    """OpenAI 스타일 (role=user/assistant) → Gemini Content(role=user/model)."""
    contents: list[Content] = []
    for msg in history:
        role = "model" if msg.get("role") == "assistant" else "user"
        text = msg.get("content", "")
        if not text:
            continue
        contents.append(Content(role=role, parts=[Part.from_text(text)]))
    return contents


class LLMClient:
    """Vertex AI GenerativeModel 호출 담당."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        _ensure_vertex_initialized(self._settings)
        self._model = GenerativeModel(
            model_name=self._settings.llm_model,
            system_instruction=SYSTEM_PROMPT,
        )
        self._gen_config = GenerationConfig(temperature=self._settings.llm_temperature)

    def answer(
        self,
        user_message: str,
        hits: list[FAQHit],
        history: list[dict[str, str]] | None = None,
    ) -> str:
        """이전 대화 + 검색 결과를 바탕으로 답변을 생성한다."""
        context_block = format_context(hits)
        user_turn = (
            f"# FAQ 컨텍스트\n{context_block}\n\n"
            f"# 사용자 질문\n{user_message}"
        )

        contents = _history_to_contents(history or [])
        contents.append(Content(role="user", parts=[Part.from_text(user_turn)]))

        response = self._model.generate_content(contents, generation_config=self._gen_config)
        return (response.text or "").strip()
