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


# --- 모바일 푸시 알림 관련 ---

class DeviceRegisterRequest(BaseModel):
    """모바일 앱이 보내는 푸시 토큰 등록 요청."""

    session_id: str = Field(..., description="대화 세션 ID (사용자 식별자로도 사용)")
    push_token: str = Field(..., description="Expo Push Token 또는 FCM/APNs 토큰")
    platform: str = Field(default="expo", description="expo / fcm / apns")
    locale: Optional[str] = Field(default=None, description="앱 언어 (ko-KR 등)")


class DeviceRecord(BaseModel):
    """등록된 디바이스 한 건."""

    session_id: str
    push_token: str
    platform: str
    locale: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class NotificationRequest(BaseModel):
    """단건 푸시 발송 요청 (테스트/수동 트리거용)."""

    session_id: str = Field(..., description="알림 대상 세션 ID")
    title: str = Field(..., max_length=120)
    body: str = Field(..., max_length=500)
    data: dict[str, Any] = Field(default_factory=dict, description="앱이 함께 받을 임의 페이로드")


class NotificationResult(BaseModel):
    """Expo Push 발송 결과 요약."""

    delivered: int
    failed: int
    receipts: list[dict[str, Any]] = Field(default_factory=list)


# --- Twilio Voice 관련 ---

class OutboundCallRequest(BaseModel):
    """에이전트가 사용자에게 거는 outbound 통화 요청."""

    session_id: str = Field(..., description="대화 세션 ID. 통화 중 webhook들이 이 ID로 라우팅됨")
    to_number: str = Field(..., description="수신자 전화번호 (E.164, 예: +821012345678)")
    greeting: str | None = Field(
        default=None,
        description="첫 인사말. 없으면 기본 한국어 인사말 사용",
    )


class OutboundCallResult(BaseModel):
    """Twilio가 큐에 넣은 통화 식별자."""

    call_sid: str
    session_id: str
    to_number: str
