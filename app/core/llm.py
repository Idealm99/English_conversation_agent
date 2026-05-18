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


# RAG 모드용 시스템 프롬프트 — FAQ 컨텍스트와 함께 사용.
RAG_SYSTEM_PROMPT = """You are a friendly assistant.

Rules:
1. Base your answer primarily on the provided 'FAQ Context' when relevant.
   If the context does not cover the user's question, you may answer from general knowledge,
   but say so briefly ("The FAQ doesn't cover this, but...").
2. **Always reply in the same language the user just spoke in.**
   If the user spoke Korean, reply in Korean. If English, reply in English.
3. Keep the reply short and natural for a phone call — 1~3 sentences first,
   add detail only if asked. No bullet lists, no markdown.
4. Do not read out source IDs or scores aloud.
"""

# 호환성 — 기존 import 깨지지 않게.
SYSTEM_PROMPT = RAG_SYSTEM_PROMPT


# 음성 통화용 대화 시스템 프롬프트 — RAG 없이 순수 conversation.
CONVERSATION_SYSTEM_PROMPT = """You are a warm, friendly English conversation partner having a phone call with a Korean learner.

Style:
- Keep each reply to 1~2 short sentences in most turns. Phone conversations need quick back-and-forth.
- Sound like a real friend chatting — not a customer-service assistant.
  Avoid stock phrases like "How may I help you today?".
- Ask natural follow-up questions to keep the conversation flowing.
- Match the user's level: if they speak simply, reply simply.
- Be warm and encouraging, but not over-the-top.

Language:
- Respond in the SAME language the user just used (English or Korean).
- If they switch, switch fluidly with them.

Important:
- DO NOT correct grammar or vocabulary inline — that feedback happens AFTER the call.
- Don't lecture. Just chat.
- No markdown, no bullet lists — this is being spoken aloud.
"""


# 번역 모드 — AI 답변을 한국어로 옮긴다.
TRANSLATION_SYSTEM_PROMPT = """You translate English text into natural, conversational Korean for an English learner.

Output rules:
- Output ONLY the Korean translation. No preface like "번역:", no English, no quotation marks around the whole thing.
- Match the tone (casual stays casual, formal stays formal). Default to natural 반말 unless the source is clearly formal.
- Idioms → equivalent Korean idiom or natural paraphrase, not literal translation.
- Keep it concise. One paragraph, no bullet lists.
"""


# 사전 모드 (grounded) — Free Dictionary API 의 권위 데이터를 ground truth 로 받는다.
DICTIONARY_GROUNDED_SYSTEM_PROMPT = """You are a Korean-friendly assistant explaining an English word to a learner.

You will receive:
- 'WORD: ...' — the target word
- Dictionary data from a reliable source (Free Dictionary API). Treat this as ground truth.
- Optionally, '사용 문맥' — the English sentence/paragraph where the word appears. Use it to pick the most relevant meaning first.

Rules:
- NEVER invent IPA, definitions, or example sentences. Use ONLY what's in the dictionary data.
- If the dictionary data is sparse, say so briefly rather than filling gaps with guesses.
- Output Korean explanations (definitions translated to natural Korean) but keep English example sentences verbatim from the data, then translate them.

Output strictly in this order, plain text only (no markdown, no asterisks, no dashes for bullets):

1) 발음
   - IPA: <복사 그대로>
   - 한글 발음: <IPA를 한글로 옮긴 근사치>

2) 뜻
   사전 데이터에서 문맥과 가장 잘 맞는 의미부터 한국어로 번역. 2~3개. 각 줄 끝에 품사 표기.

3) 예문
   사전 데이터의 example 1~2개. 영어 원문 그대로 + 한국어 번역.

4) Synonyms / Antonyms
   사전 데이터에 있으면 4~6개 나열. 없으면 "데이터 없음".

5) 주의점
   문맥과 다른 의미가 헷갈리기 쉽다면 짧게 짚기. Konglish 함정이 있으면 한 줄.
   해당사항 없으면 "특이사항 없음".

마지막 줄에 "(출처: Free Dictionary API + Gemini 해설)" 표기.
총 150~220단어.
"""


# 사전 모드 (LLM-only fallback) — Free Dictionary 가 못 찾았을 때 사용.
DICTIONARY_SYSTEM_PROMPT = """You are a bilingual English-Korean dictionary helper for a Korean learner.

The user gives you an English word or phrase. They may also include the surrounding sentence as context — use it to pick the most relevant meaning first.

Provide in this EXACT order, plain text only (no markdown):

1) 발음
   - IPA: /…/
   - 한글 발음: …

2) 뜻
   문맥상 가장 가까운 뜻부터 2~3개. 각 뜻에 한두 문장 설명.

3) 품사 / 활용
   noun / verb / adjective 등. 동사면 과거형 + 과거분사, 명사면 불규칙 복수형, 형용사면 비교급/최상급. 규칙적이면 생략.

4) 예문 (2개)
   영어 원문 + 한국어 번역. 가능하면 다른 문맥으로.

5) Collocations (자주 같이 쓰는 표현, 2~3개)
   각 표현 + 짧은 뜻.

6) 주의점
   비슷한 단어와의 차이, Konglish 함정 등이 있으면. 없으면 "없음".

규칙:
- 마크다운 금지 (별표·대시 없음).
- 항목 번호는 "1)", "2)" 형식 그대로.
- 항목 간 빈 줄 1개.
- 설명은 한국어, 영어 예문은 큰따옴표 안에.
- 총 150~200 단어.
"""


# 표현 도움 모드 — 사용자가 한국어를 주고 "영어로 어떻게?" 묻는다.
PHRASING_SYSTEM_PROMPT = """You are an English coach for a Korean speaker who is preparing to say something in English.

The user will give you a Korean sentence or phrase. Your job:

1) Give 2~3 natural English versions, from casual to formal. Label each with the register and a short situation note (e.g. "친구한테 카톡으로", "직장 동료한테 슬랙으로", "비즈니스 이메일").

2) Explain WHEN to pick which — audience, tone, situation. Be specific.

3) Pronunciation or grammar tip — if there's a tricky sound, stress pattern, or grammar trap, mention it briefly.

4) Common mistake — if Korean speakers typically translate this incorrectly (e.g. literal Konglish), call it out and contrast with the natural English.

Format strictly:
- Plain text only. NO markdown headings, NO asterisks for bold, NO dash bullets.
- Number main items as "1)", "2)", "3)" exactly.
- Use blank lines between sections.
- Write explanations in Korean. Put English example sentences in double quotes.
- Total length around 150~250 words. Warm, encouraging teacher tone.
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


def _dictionary_user_text(word: str, context: str | None) -> str:
    """사전 모드 (LLM-only) 사용자 메시지 — 단어 + 선택적 문맥."""
    parts = [f"단어/표현: {word.strip()}"]
    if context and context.strip():
        parts.append(f"\n문맥 (이 단어가 등장한 영어 문장):\n{context.strip()}")
    return "\n".join(parts)


def _grounded_user_text(word: str, dictionary_text: str, context: str | None) -> str:
    """사전 모드 (grounded) 사용자 메시지 — 단어 + 사전 데이터 + 선택적 문맥."""
    parts = [
        f"WORD: {word.strip()}",
        "",
        "사전 데이터:",
        dictionary_text.strip(),
    ]
    if context and context.strip():
        parts.append("")
        parts.append("사용 문맥:")
        parts.append(context.strip())
    return "\n".join(parts)


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
    """Vertex AI GenerativeModel 호출 담당.

    두 가지 모드:
      - `answer(...)` : RAG 모드. FAQ 컨텍스트와 함께 답변.
      - `chat(...)`   : 순수 대화 모드. 음성 통화에서 사용.
    각 모드는 system_instruction이 다르므로 GenerativeModel을 분리해 lazy-init 한다.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        _ensure_vertex_initialized(self._settings)
        # 모드별 모델 (system_instruction 이 달라서 분리). 모두 lazy.
        self._models: dict[str, GenerativeModel] = {}
        self._gen_config = GenerationConfig(temperature=self._settings.llm_temperature)

    def _model_for(self, system_prompt: str) -> GenerativeModel:
        # system_prompt 가 key 로 사용 — 같은 프롬프트면 같은 인스턴스 재사용.
        cached = self._models.get(system_prompt)
        if cached is not None:
            return cached
        model = GenerativeModel(
            model_name=self._settings.llm_model,
            system_instruction=system_prompt,
        )
        self._models[system_prompt] = model
        return model

    def _ensure_rag_model(self) -> GenerativeModel:
        return self._model_for(RAG_SYSTEM_PROMPT)

    def _ensure_chat_model(self) -> GenerativeModel:
        return self._model_for(CONVERSATION_SYSTEM_PROMPT)

    def answer(
        self,
        user_message: str,
        hits: list[FAQHit],
        history: list[dict[str, str]] | None = None,
    ) -> str:
        """RAG 모드 — 검색된 FAQ를 컨텍스트로 답변 생성."""
        context_block = format_context(hits)
        user_turn = (
            f"# FAQ 컨텍스트\n{context_block}\n\n"
            f"# 사용자 질문\n{user_message}"
        )

        contents = _history_to_contents(history or [])
        contents.append(Content(role="user", parts=[Part.from_text(user_turn)]))

        response = self._ensure_rag_model().generate_content(
            contents, generation_config=self._gen_config
        )
        return (response.text or "").strip()

    def chat(
        self,
        user_message: str,
        history: list[dict[str, str]] | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """대화 모드 — RAG 없이 자연스러운 회화.

        system_prompt 를 명시하면 캐릭터 페르소나로 교체 가능. 미지정 시 기본 대화 프롬프트.
        """
        prompt = system_prompt or CONVERSATION_SYSTEM_PROMPT
        contents = _history_to_contents(history or [])
        contents.append(Content(role="user", parts=[Part.from_text(user_message)]))
        response = self._model_for(prompt).generate_content(
            contents, generation_config=self._gen_config
        )
        return (response.text or "").strip()

    def chat_stream(
        self,
        user_message: str,
        history: list[dict[str, str]] | None = None,
        system_prompt: str | None = None,
    ):
        """동기 generator — 부분 응답 텍스트 청크를 yield. 캐릭터별 system_prompt 지원."""
        prompt = system_prompt or CONVERSATION_SYSTEM_PROMPT
        contents = _history_to_contents(history or [])
        contents.append(Content(role="user", parts=[Part.from_text(user_message)]))
        stream = self._model_for(prompt).generate_content(
            contents, generation_config=self._gen_config, stream=True
        )
        for chunk in stream:
            text = getattr(chunk, "text", None) or ""
            if text:
                yield text

    # --- 학습 도구 ---

    def translate(self, text: str) -> str:
        """영문 텍스트 → 자연스러운 한국어. system prompt 가 출력 형식 강제."""
        return self._oneshot(TRANSLATION_SYSTEM_PROMPT, text)

    def translate_stream(self, text: str):
        yield from self._oneshot_stream(TRANSLATION_SYSTEM_PROMPT, text)

    def explain_phrasing(self, korean_text: str) -> str:
        """한국어 표현 → 영어로 어떻게 말할지 상세 가이드."""
        return self._oneshot(PHRASING_SYSTEM_PROMPT, korean_text)

    def explain_phrasing_stream(self, korean_text: str):
        yield from self._oneshot_stream(PHRASING_SYSTEM_PROMPT, korean_text)

    def lookup_word(self, word: str, context: str | None = None) -> str:
        """영어 단어/표현 → 학습자용 사전 항목 (LLM-only). context 가 있으면 다의어 해소."""
        return self._oneshot(DICTIONARY_SYSTEM_PROMPT, _dictionary_user_text(word, context))

    def lookup_word_stream(self, word: str, context: str | None = None):
        yield from self._oneshot_stream(
            DICTIONARY_SYSTEM_PROMPT, _dictionary_user_text(word, context)
        )

    def explain_dictionary_entry_stream(
        self,
        word: str,
        dictionary_text: str,
        context: str | None = None,
    ):
        """Free Dictionary 데이터를 ground truth 로 주고 한국어 해설을 스트리밍.

        dictionary_text 는 dictionary_api.format_entry_for_llm 의 결과를 그대로 넣는다.
        """
        user_text = _grounded_user_text(word, dictionary_text, context)
        yield from self._oneshot_stream(DICTIONARY_GROUNDED_SYSTEM_PROMPT, user_text)

    # --- 내부 헬퍼 ---

    def _oneshot(self, system_prompt: str, user_text: str) -> str:
        contents = [Content(role="user", parts=[Part.from_text(user_text)])]
        response = self._model_for(system_prompt).generate_content(
            contents, generation_config=self._gen_config
        )
        return (response.text or "").strip()

    def _oneshot_stream(self, system_prompt: str, user_text: str):
        contents = [Content(role="user", parts=[Part.from_text(user_text)])]
        stream = self._model_for(system_prompt).generate_content(
            contents, generation_config=self._gen_config, stream=True
        )
        for chunk in stream:
            text = getattr(chunk, "text", None) or ""
            if text:
                yield text
