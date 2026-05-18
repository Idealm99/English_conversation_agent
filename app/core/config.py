"""환경 변수 기반 설정 (pydantic BaseModel + os.environ 사용)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


class Settings(BaseModel):
    """전역 애플리케이션 설정."""

    # 메타
    app_name: str = "faq-chatbot"
    version: str = "0.1.0"
    debug: bool = Field(default_factory=lambda: _env("DEBUG", "false") == "true")

    # GCP / Vertex AI
    gcp_project: str | None = Field(
        default_factory=lambda: _env("GOOGLE_CLOUD_PROJECT") or _env("GCP_PROJECT")
    )
    gcp_location: str = Field(
        default_factory=lambda: _env("GOOGLE_CLOUD_LOCATION", "us-central1")
        or _env("GCP_LOCATION", "us-central1")
        or "us-central1"
    )
    llm_model: str = Field(
        default_factory=lambda: _env("LLM_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash"
    )
    embedding_model: str = Field(
        default_factory=lambda: _env("EMBEDDING_MODEL", "text-multilingual-embedding-002")
        or "text-multilingual-embedding-002"
    )
    llm_temperature: float = Field(
        default_factory=lambda: float(_env("LLM_TEMPERATURE", "0.2") or 0.2)
    )

    # Chroma 벡터 저장소
    chroma_persist_dir: Path = Field(
        default_factory=lambda: Path(_env("CHROMA_PERSIST_DIR", "./.chroma") or "./.chroma")
    )
    chroma_collection: str = Field(
        default_factory=lambda: _env("CHROMA_COLLECTION", "faqs") or "faqs"
    )

    # 검색/랭킹
    retrieval_top_k: int = Field(
        default_factory=lambda: int(_env("RETRIEVAL_TOP_K", "8") or 8)
    )
    rerank_top_k: int = Field(
        default_factory=lambda: int(_env("RERANK_TOP_K", "4") or 4)
    )
    min_score: float = Field(
        default_factory=lambda: float(_env("MIN_SCORE", "0.25") or 0.25)
    )

    # Redis 캐시
    redis_url: str | None = Field(default_factory=lambda: _env("REDIS_URL"))
    cache_ttl_seconds: int = Field(
        default_factory=lambda: int(_env("CACHE_TTL_SECONDS", "3600") or 3600)
    )

    # 메모리(대화 히스토리)
    memory_max_turns: int = Field(
        default_factory=lambda: int(_env("MEMORY_MAX_TURNS", "10") or 10)
    )

    # 개발용 스텁: 설정되면 ChatService가 Vertex/Chroma를 건너뛰고 이 문구를 그대로 답변으로 반환.
    chat_stub_response: str | None = Field(default_factory=lambda: _env("CHAT_STUB_RESPONSE"))

    # 데이터 경로
    faq_data_path: Path = Field(
        default_factory=lambda: Path(_env("FAQ_DATA_PATH", "./data/faqs.json") or "./data/faqs.json")
    )

    # 모바일 푸시 / 디바이스 저장소
    device_db_path: Path = Field(
        default_factory=lambda: Path(_env("DEVICE_DB_PATH", "./.data/devices.json") or "./.data/devices.json")
    )
    expo_push_url: str = Field(
        default_factory=lambda: _env("EXPO_PUSH_URL", "https://exp.host/--/api/v2/push/send")
        or "https://exp.host/--/api/v2/push/send"
    )
    # Expo 유료 프로젝트의 액세스 토큰. 무료 사용 시 None.
    expo_access_token: str | None = Field(default_factory=lambda: _env("EXPO_ACCESS_TOKEN"))

    # Twilio Voice
    twilio_account_sid: str | None = Field(default_factory=lambda: _env("TWILIO_ACCOUNT_SID"))
    twilio_auth_token: str | None = Field(default_factory=lambda: _env("TWILIO_AUTH_TOKEN"))
    # Twilio에서 발신용으로 구매한 번호 (E.164 형식, 예: +15551234567).
    twilio_from_number: str | None = Field(default_factory=lambda: _env("TWILIO_FROM_NUMBER"))
    # Twilio가 우리 webhook을 호출할 때 사용하는 공개 베이스 URL (ngrok 주소 등).
    public_base_url: str | None = Field(default_factory=lambda: _env("PUBLIC_BASE_URL"))
    # 통화 음성 설정 (Polly Korean voice / language tag).
    voice_language: str = Field(
        default_factory=lambda: _env("VOICE_LANGUAGE", "ko-KR") or "ko-KR"
    )
    voice_tts_voice: str = Field(
        default_factory=lambda: _env("VOICE_TTS_VOICE", "Polly.Seoyeon") or "Polly.Seoyeon"
    )
    # 무음 N초 이상이면 Twilio가 Gather를 종료한다. 'auto'면 Twilio가 자동 판단.
    voice_speech_timeout: str = Field(
        default_factory=lambda: _env("VOICE_SPEECH_TIMEOUT", "auto") or "auto"
    )
    # 통화 한 건당 최대 턴 수 (무한 루프 방지).
    voice_max_turns: int = Field(
        default_factory=lambda: int(_env("VOICE_MAX_TURNS", "10") or 10)
    )

    # --- MVP-2: Media Streams + GCP STT/TTS ---
    # Twilio Media Streams는 μ-law 8kHz 고정.
    stt_language: str = Field(
        default_factory=lambda: _env("STT_LANGUAGE", "ko-KR") or "ko-KR"
    )
    # 빈 문자열이면 GCP가 언어별 기본 모델 선택. 'phone_call'은 영어 전용이라
    # ko-KR에선 503 으로 거부됨. 한국어는 'latest_long' 추천 (또는 빈 값).
    stt_model: str = Field(
        default_factory=lambda: _env("STT_MODEL", "") or ""
    )
    tts_voice_name: str = Field(
        # Neural2 가 가장 자연스러움. 비용 절감 시 ko-KR-Standard-A 로 변경.
        default_factory=lambda: _env("TTS_VOICE_NAME", "ko-KR-Neural2-A") or "ko-KR-Neural2-A"
    )
    # 첫 인사말. 스트리밍 모드에선 GCP TTS로 합성해서 재생한다.
    voice_greeting: str = Field(
        default_factory=lambda: _env(
            "VOICE_GREETING",
            "안녕하세요. 무엇을 도와드릴까요?",
        ) or "안녕하세요. 무엇을 도와드릴까요?"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """프로세스 단위로 단 한 번만 생성되는 설정 객체."""
    return Settings()
