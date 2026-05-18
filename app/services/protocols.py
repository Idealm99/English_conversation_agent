"""서비스 레이어 인터페이스(Protocol).

DI 시 구체 타입(ChatService/ConversationService) 대신 이 Protocol에 의존하면
교체가 자유롭고 단위 테스트도 mock 클래스로 쉽게 가능하다.
런타임 isinstance() 체크용이 아니라 정적 분석/가독성 목적.

레이어:
  - Chat 계열  : 사용자 발화 → 답변 (RAG 든 conversation 이든 같은 모양)
  - Voice 계열 : TwiML 빌더, outbound caller
  - 오디오 파이프 : STT / TTS / Twilio Media WS
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Protocol, runtime_checkable

from app.models.schemas import ChatRequest, ChatResponse


# --- Chat ---

@runtime_checkable
class ChatGateway(Protocol):
    """채팅 진입점 — 모든 모드(RAG, conversation, stub)가 공통으로 따른다."""

    def handle(self, request: ChatRequest) -> ChatResponse: ...
    def reset_session(self, session_id: str) -> None: ...


@runtime_checkable
class StreamingChatGateway(ChatGateway, Protocol):
    """스트리밍 응답을 추가로 지원하는 채팅 진입점."""

    def handle_stream(self, request: ChatRequest) -> AsyncIterator[str]: ...


# --- Voice 오디오 파이프 ---

@dataclass(frozen=True)
class Transcript:
    """STT가 내보내는 한 조각의 결과."""

    text: str
    is_final: bool


@runtime_checkable
class SpeechToText(Protocol):
    """오디오 청크 스트림을 받아 transcript 스트림을 yield 한다."""

    def transcribe(
        self, audio_chunks: AsyncIterator[bytes]
    ) -> AsyncIterator[Transcript]: ...


@runtime_checkable
class TextToSpeech(Protocol):
    """텍스트를 raw 오디오 바이트로 합성 (전화 채널 호환 인코딩)."""

    async def synthesize(self, text: str) -> bytes: ...


@runtime_checkable
class TwilioMediaTransport(Protocol):
    """Twilio Media Streams WebSocket 의 메시지 레벨 추상화.

    오디오 송수신 + barge-in clear 만 노출하고, JSON 프로토콜 세부는 감춘다.
    """

    @property
    def stream_sid(self) -> str | None: ...

    async def wait_for_start(self) -> str: ...
    async def iter_inbound_audio(self) -> AsyncIterator[bytes]: ...
    async def send_audio_chunk(self, chunk: bytes) -> None: ...
    async def send_clear(self) -> None: ...
