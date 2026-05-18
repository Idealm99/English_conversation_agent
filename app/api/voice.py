"""Twilio Voice webhook + outbound 트리거.

엔드포인트:
  POST /voice/call              — (관리용) 에이전트가 사용자한테 전화를 건다
  POST /voice/answer/{sid}      — Twilio가 통화 응답 직후 호출 → 첫 TwiML (gather)
  POST /voice/answer-stream/{sid} — Media Streams 모드용 TwiML
  POST /voice/gather/{sid}      — Twilio가 사용자 발화(STT 결과) 전달 → 다음 TwiML
  WS   /voice/stream/{sid}      — Media Streams 양방향 오디오
  POST /voice/status/{sid}      — 통화 상태 콜백 (로깅)

TwiML 응답은 Content-Type: application/xml 로 돌려준다.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from twilio.base.exceptions import TwilioRestException

from app.models.schemas import ChatRequest, OutboundCallRequest, OutboundCallResult
from app.services.conversation_service import get_conversation_service
from app.services.protocols import ChatGateway
from app.services.voice_service import (
    OutboundCaller,
    TwiMLBuilder,
    get_outbound_caller,
    get_twiml_builder,
)
from app.services.voice_stream import MediaStreamHandler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


def _twiml(xml: str) -> Response:
    return Response(content=xml, media_type="application/xml")


@router.post("/call", response_model=OutboundCallResult)
def place_call(
    payload: OutboundCallRequest,
    caller: OutboundCaller = Depends(get_outbound_caller),
) -> OutboundCallResult:
    try:
        return caller.place_call(
            session_id=payload.session_id,
            to_number=payload.to_number,
            greeting=payload.greeting,
            mode=payload.mode,
        )
    except RuntimeError as exc:
        # 환경 변수 누락 등 구성 오류.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except TwilioRestException as exc:
        logger.exception("Twilio API rejected the call")
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
    builder: TwiMLBuilder = Depends(get_twiml_builder),
) -> Response:
    """gather 모드: Twilio가 통화 응답 후 첫 TwiML을 요청."""
    xml = builder.build_greeting_twiml(session_id, greeting=greeting)
    return _twiml(xml)


@router.post("/answer-stream/{session_id}")
def answer_stream(
    session_id: str,
    greeting: Optional[str] = Query(default=None),
    builder: TwiMLBuilder = Depends(get_twiml_builder),
) -> Response:
    """stream 모드: Media Streams 연결 TwiML."""
    xml = builder.build_stream_twiml(session_id, greeting=greeting)
    return _twiml(xml)


@router.websocket("/stream/{session_id}")
async def voice_stream(
    websocket: WebSocket,
    session_id: str,
    greeting: Optional[str] = Query(default=None),
) -> None:
    """Twilio Media Streams 의 양방향 WebSocket 핸들러."""
    await websocket.accept()
    chat: ChatGateway = get_conversation_service()
    handler = MediaStreamHandler(
        websocket=websocket,
        session_id=session_id,
        chat=chat,
        greeting=greeting,
    )
    try:
        await handler.run()
    except WebSocketDisconnect:
        logger.info("voice stream disconnected: session=%s", session_id)
    except Exception:
        logger.exception("voice stream crashed: session=%s", session_id)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.post("/gather/{session_id}")
def gather(
    session_id: str,
    turn: int = Query(default=1, ge=1),
    SpeechResult: str = Form(default=""),
    Confidence: Optional[str] = Form(default=None),
    builder: TwiMLBuilder = Depends(get_twiml_builder),
    chat: ChatGateway = Depends(get_conversation_service),
) -> Response:
    """사용자 발화(텍스트) → ChatGateway → 다음 TwiML."""
    transcript = (SpeechResult or "").strip()
    logger.info(
        "voice gather: session=%s turn=%d confidence=%s transcript=%r",
        session_id,
        turn,
        Confidence,
        transcript,
    )

    if not transcript:
        return _twiml(builder.build_greeting_twiml(session_id))

    try:
        result = chat.handle(ChatRequest(session_id=session_id, message=transcript))
        return _twiml(
            builder.build_turn_twiml(session_id, result.answer, next_turn=turn + 1)
        )
    except Exception:
        logger.exception("chat pipeline failed during voice turn")
        return _twiml(builder.build_error_twiml())


@router.post("/status/{session_id}")
def status_callback(
    session_id: str,
    CallSid: str = Form(default=""),
    CallStatus: str = Form(default=""),
    CallDuration: Optional[str] = Form(default=None),
) -> Response:
    """Twilio 통화 상태 콜백. 본문은 의미 없으니 204."""
    logger.info(
        "voice status: session=%s sid=%s status=%s duration=%s",
        session_id,
        CallSid,
        CallStatus,
        CallDuration,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
