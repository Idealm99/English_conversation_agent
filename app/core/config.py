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

    # 데이터 경로
    faq_data_path: Path = Field(
        default_factory=lambda: Path(_env("FAQ_DATA_PATH", "./data/faqs.json") or "./data/faqs.json")
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """프로세스 단위로 단 한 번만 생성되는 설정 객체."""
    return Settings()
