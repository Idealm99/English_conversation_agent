"""API 요청/응답에서 사용하는 Pydantic 스키마 모음."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """클라이언트가 보내는 채팅 요청."""

    session_id: str = Field(..., description="대화 세션 식별자")
    message: str = Field(..., min_length=1, max_length=2000, description="사용자 입력")
    top_k: int = Field(default=4, ge=1, le=20, description="검색할 FAQ 개수")


class FAQHit(BaseModel):
    """검색된 FAQ 항목 (랭킹 결과 포함)."""

    faq_id: str
    question: str
    answer: str
    score: float = Field(..., description="최종 랭킹 점수 (0~1)")
    distance: Optional[float] = Field(default=None, description="원본 벡터 거리")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """LLM이 생성한 답변 + 근거 FAQ."""

    session_id: str
    answer: str
    sources: list[FAQHit] = Field(default_factory=list)
    used_cache: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FAQDocument(BaseModel):
    """벡터DB에 적재되는 FAQ 원본 문서."""

    faq_id: str
    question: str
    answer: str
    category: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
