"""Twilio Voice 서비스 — TwiML 빌더 + outbound 발신.

설계 의도(SRP):
  - `TwiMLBuilder`  : 순수 XML 빌더. Twilio REST 클라이언트와 무관, 부수효과 없음.
  - `OutboundCaller`: Twilio REST API 로 outbound 통화를 거는 어댑터.
  - `VoiceService`  : 두 컴포넌트를 묶은 얇은 파사드 (기존 호출부 호환).

새 코드는 가능하면 직접 `TwiMLBuilder` / `OutboundCaller` 에 의존하길 권장.

Twilio Programmable Voice 레퍼런스:
  https://www.twilio.com/docs/voice/twiml
  https://www.twilio.com/docs/voice/twiml/gather
  https://www.twilio.com/docs/voice/twiml/stream
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlencode, urljoin

from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import Gather, VoiceResponse

from app.core.config import Settings, get_settings
from app.models.schemas import OutboundCallResult

logger = logging.getLogger(__name__)


DEFAULT_GREETING = "안녕하세요. FAQ 어시스턴트입니다. 무엇이 궁금하신가요?"
GOODBYE_MESSAGE = "응답이 없어 통화를 종료하겠습니다. 안녕히 계세요."
LIMIT_REACHED_MESSAGE = "오늘 통화는 여기까지 진행하겠습니다. 안녕히 계세요."
ERROR_MESSAGE = "죄송합니다. 처리 중 오류가 발생했습니다."


# ---------------------------------------------------------------------------
# TwiML 빌더 — 순수 XML 생성.
# ---------------------------------------------------------------------------

class TwiMLBuilder:
    """Twilio 가 우리 webhook에 GET/POST 했을 때 돌려줄 TwiML XML 을 만든다.

    부수효과 없음 (네트워크 호출 없음, 시간 의존성 없음). 그래서 테스트하기 좋다.
    공개 base URL 이 없으면 스트리밍 모드 빌더에서만 실패하고, gather 모드는
    상대 URL로 fallback 한다.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    # --- public ---

    def build_greeting_twiml(
        self, session_id: str, greeting: Optional[str] = None
    ) -> str:
        """gather 모드 첫 응답: 인사말 + 음성 입력 대기."""
        response = VoiceResponse()
        gather = self._attach_gather(response, session_id, turn=1)
        self._say(gather, greeting or DEFAULT_GREETING)
        # Gather 무음 timeout 시 자동으로 다음 노드(작별)로 흐른다.
        self._say(response, GOODBYE_MESSAGE)
        response.hangup()
        return str(response)

    def build_turn_twiml(
        self, session_id: str, answer: str, *, next_turn: int
    ) -> str:
        """gather 모드 후속 응답: 답변 + 다음 사용자 발화 대기."""
        response = VoiceResponse()
        self._say(response, answer)
        if next_turn > self._settings.voice_max_turns:
            self._say(response, LIMIT_REACHED_MESSAGE)
            response.hangup()
            return str(response)
        # gather를 다음 턴 안내용으로 부착. prompt 없이 듣기 모드만.
        self._attach_gather(response, session_id, turn=next_turn)
        self._say(response, GOODBYE_MESSAGE)
        response.hangup()
        return str(response)

    def build_stream_twiml(
        self, session_id: str, greeting: Optional[str] = None
    ) -> str:
        """stream 모드: Media Streams WebSocket으로 연결."""
        response = VoiceResponse()
        connect = response.connect()
        ws_url = self._stream_ws_url(session_id)
        if greeting:
            ws_url = f"{ws_url}?{urlencode({'greeting': greeting})}"
        # 기본 track=inbound_track (caller mic only). echo 위험 없음.
        connect.stream(url=ws_url)
        return str(response)

    def build_error_twiml(self) -> str:
        response = VoiceResponse()
        self._say(response, ERROR_MESSAGE)
        response.hangup()
        return str(response)

    # --- helpers ---

    def _say(self, node, text: str) -> None:
        node.say(
            text,
            voice=self._settings.voice_tts_voice,
            language=self._settings.voice_language,
        )

    def _attach_gather(self, response: VoiceResponse, session_id: str, turn: int) -> Gather:
        return response.gather(  # type: ignore[no-any-return]
            input="speech",
            language=self._settings.voice_language,
            speech_timeout=self._settings.voice_speech_timeout,
            action=self._gather_action_url(session_id, turn),
            method="POST",
            speech_model="phone_call",
        )

    def _gather_action_url(self, session_id: str, turn: int) -> str:
        base = self._settings.public_base_url
        path = f"voice/gather/{session_id}?turn={turn}"
        if base:
            return urljoin(base.rstrip("/") + "/", path)
        return f"/{path}"

    def _stream_ws_url(self, session_id: str) -> str:
        base = self._settings.public_base_url
        if not base:
            raise RuntimeError("PUBLIC_BASE_URL 환경 변수가 필요합니다.")
        base = base.rstrip("/")
        if base.startswith("https://"):
            ws_base = "wss://" + base[len("https://") :]
        elif base.startswith("http://"):
            ws_base = "ws://" + base[len("http://") :]
        else:
            ws_base = base
        return f"{ws_base}/voice/stream/{session_id}"


# ---------------------------------------------------------------------------
# Outbound 발신 — Twilio REST 호출.
# ---------------------------------------------------------------------------

class OutboundCaller:
    """Twilio REST API 로 사용자에게 전화를 건다.

    `place_call()` 만 외부에 노출. Twilio 클라이언트는 lazy-init 하며 테스트에선
    생성자에 mock 을 주입할 수 있다.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        client: TwilioClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client_override = client

    def place_call(
        self,
        session_id: str,
        to_number: str,
        greeting: str | None = None,
        mode: str = "gather",
    ) -> OutboundCallResult:
        """에이전트가 사용자에게 전화를 건다.

        Twilio는 통화가 응답되면 mode에 따라 `/voice/answer*/{sid}` 를 호출한다.
        """
        if mode not in ("gather", "stream"):
            raise ValueError(f"unsupported voice mode: {mode}")
        from_number, base_url = self._require_config()
        answer_path = "voice/answer-stream" if mode == "stream" else "voice/answer"
        answer_url = urljoin(base_url.rstrip("/") + "/", f"{answer_path}/{session_id}")
        status_url = urljoin(base_url.rstrip("/") + "/", f"voice/status/{session_id}")
        if greeting:
            answer_url = f"{answer_url}?{urlencode({'greeting': greeting})}"

        call = self._client().calls.create(
            to=to_number,
            from_=from_number,
            url=answer_url,
            method="POST",
            status_callback=status_url,
            status_callback_event=["initiated", "answered", "completed"],
            status_callback_method="POST",
        )
        logger.info(
            "outbound call queued: sid=%s session=%s to=%s",
            call.sid,
            session_id,
            to_number,
        )
        return OutboundCallResult(
            call_sid=call.sid, session_id=session_id, to_number=to_number
        )

    # --- internals ---

    def _client(self) -> TwilioClient:
        if self._client_override is not None:
            return self._client_override
        sid, token = self._require_credentials()
        return TwilioClient(sid, token)

    def _require_credentials(self) -> tuple[str, str]:
        s = self._settings
        missing = [
            name
            for name, value in (
                ("TWILIO_ACCOUNT_SID", s.twilio_account_sid),
                ("TWILIO_AUTH_TOKEN", s.twilio_auth_token),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"필수 환경 변수 누락: {', '.join(missing)}")
        return s.twilio_account_sid, s.twilio_auth_token  # type: ignore[return-value]

    def _require_config(self) -> tuple[str, str]:
        s = self._settings
        missing = [
            name
            for name, value in (
                ("TWILIO_FROM_NUMBER", s.twilio_from_number),
                ("PUBLIC_BASE_URL", s.public_base_url),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"필수 환경 변수 누락: {', '.join(missing)}")
        # 자격은 _client()에서 확인.
        return s.twilio_from_number, s.public_base_url  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Facade (기존 호출부 호환) + 모듈 싱글톤.
# ---------------------------------------------------------------------------

class VoiceService:
    """기존 코드 호환을 위한 얇은 파사드.

    새 코드는 `TwiMLBuilder` / `OutboundCaller` 를 직접 받아 쓰길 권장.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        client: TwilioClient | None = None,
        twiml_builder: TwiMLBuilder | None = None,
        outbound_caller: OutboundCaller | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._builder = twiml_builder or TwiMLBuilder(self._settings)
        self._caller = outbound_caller or OutboundCaller(self._settings, client=client)

    # 빌더 위임
    def build_greeting_twiml(
        self, session_id: str, greeting: Optional[str] = None
    ) -> str:
        return self._builder.build_greeting_twiml(session_id, greeting)

    def build_turn_twiml(self, session_id: str, answer: str, *, next_turn: int) -> str:
        return self._builder.build_turn_twiml(session_id, answer, next_turn=next_turn)

    def build_stream_twiml(
        self, session_id: str, greeting: Optional[str] = None
    ) -> str:
        return self._builder.build_stream_twiml(session_id, greeting)

    def build_error_twiml(self) -> str:
        return self._builder.build_error_twiml()

    # 발신 위임
    def place_outbound_call(
        self,
        session_id: str,
        to_number: str,
        greeting: str | None = None,
        mode: str = "gather",
    ) -> OutboundCallResult:
        return self._caller.place_call(
            session_id=session_id, to_number=to_number, greeting=greeting, mode=mode
        )


_voice_service: Optional[VoiceService] = None
_twiml_builder: Optional[TwiMLBuilder] = None
_outbound_caller: Optional[OutboundCaller] = None


def get_voice_service() -> VoiceService:
    global _voice_service
    if _voice_service is None:
        _voice_service = VoiceService()
    return _voice_service


def get_twiml_builder() -> TwiMLBuilder:
    global _twiml_builder
    if _twiml_builder is None:
        _twiml_builder = TwiMLBuilder()
    return _twiml_builder


def get_outbound_caller() -> OutboundCaller:
    global _outbound_caller
    if _outbound_caller is None:
        _outbound_caller = OutboundCaller()
    return _outbound_caller
