"""Twilio Voice webhook + outbound 트리거.

엔드포인트:
  POST /voice/call          — (관리용) 에이전트가 사용자한테 전화를 건다
  POST /voice/answer/{sid}  — Twilio가 통화 응답 직후 호출 → 첫 TwiML
  POST /voice/gather/{sid}  — Twilio가 사용자 발화(STT 결과) 전달 → 다음 TwiML
  POST /voice/status/{sid}  — 통화 상태 콜백 (로깅)

TwiML 응답은 Content-Type: application/xml 로 돌려준다.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Response, status
from twilio.base.exceptions import TwilioRestException

from app.models.schemas import ChatRequest, OutboundCallRequest, OutboundCallResult
from app.services.chat_service import ChatService, get_chat_service
from app.services.voice_service import VoiceService, get_voice_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


def _twiml(xml: str) -> Response:
    return Response(content=xml, media_type="application/xml")


@router.post("/call", response_model=OutboundCallResult)
def place_call(
    payload: OutboundCallRequest,
    service: VoiceService = Depends(get_voice_service),
) -> OutboundCallResult:
    try:
        return service.place_outbound_call(
            session_id=payload.session_id,
            to_number=payload.to_number,
            greeting=payload.greeting,
        )
    except RuntimeError as exc:
        # 환경 변수 누락 등 구성 오류.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except TwilioRestException as exc:
        logger.exception("Twilio API rejected the call")
        # Twilio가 알려주는 사유를 그대로 노출 (dev 환경에서 디버깅 편하도록).
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Twilio {exc.status} (code {exc.code}): {exc.msg}",
        ) from exc
    except Exception as exc:
        logger.exception("place_call failed")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Twilio 호출 실패: {exc}"
        ) from exc


@router.post("/answer/{session_id}")
def answer(
    session_id: str,
    greeting: Optional[str] = Query(default=None),
    service: VoiceService = Depends(get_voice_service),
) -> Response:
    """Twilio가 통화 응답 후 첫 TwiML을 요청."""
    xml = service.build_greeting_twiml(session_id, greeting=greeting)
    return _twiml(xml)


@router.post("/gather/{session_id}")
def gather(
    session_id: str,
    turn: int = Query(default=1, ge=1),
    SpeechResult: str = Form(default=""),
    Confidence: Optional[str] = Form(default=None),
    voice: VoiceService = Depends(get_voice_service),
    chat: ChatService = Depends(get_chat_service),
) -> Response:
    """사용자 발화(텍스트) → ChatService → 다음 TwiML."""
    transcript = (SpeechResult or "").strip()
    logger.info(
        "voice gather: session=%s turn=%d confidence=%s transcript=%r",
        session_id,
        turn,
        Confidence,
        transcript,
    )

    if not transcript:
        # 빈 발화면 그대로 종료 TwiML (Twilio가 다시 fallback Say + hangup).
        return _twiml(voice.build_greeting_twiml(session_id))

    try:
        result = chat.handle(ChatRequest(session_id=session_id, message=transcript))
        return _twiml(
            voice.build_turn_twiml(session_id, result.answer, next_turn=turn + 1)
        )
    except Exception:
        logger.exception("chat pipeline failed during voice turn")
        return _twiml(voice.build_error_twiml())


@router.post("/status/{session_id}")
def status_callback(
    session_id: str,
    CallSid: str = Form(default=""),
    CallStatus: str = Form(default=""),
    CallDuration: Optional[str] = Form(default=None),
) -> Response:
    """Twilio 통화 상태 콜백. 본문은 의미 없으니 200으로 응답만 준다."""
    logger.info(
        "voice status: session=%s sid=%s status=%s duration=%s",
        session_id,
        CallSid,
        CallStatus,
        CallDuration,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
