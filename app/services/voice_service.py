"""Twilio Voice 서비스.

PoC: TwiML `<Say>` + `<Gather input="speech">` 만으로 대화 한 턴씩 굴린다.
- Twilio가 자체 STT/TTS 수행 → 우리 서버는 SpeechResult(텍스트)만 받아서
  기존 ChatService에 흘려보내고, 답변을 다시 TwiML `<Say>`로 돌려준다.
- WebSocket / 실시간 스트리밍은 다음 단계(MVP-2)에서 추가.

Twilio Programmable Voice 레퍼런스:
  https://www.twilio.com/docs/voice/twiml
  https://www.twilio.com/docs/voice/twiml/gather
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urljoin

from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import Gather, VoiceResponse

from app.core.config import Settings, get_settings
from app.models.schemas import OutboundCallResult

logger = logging.getLogger(__name__)


DEFAULT_GREETING = "안녕하세요. FAQ 어시스턴트입니다. 무엇이 궁금하신가요?"
GOODBYE_MESSAGE = "응답이 없어 통화를 종료하겠습니다. 안녕히 계세요."
LIMIT_REACHED_MESSAGE = "오늘 통화는 여기까지 진행하겠습니다. 안녕히 계세요."
ERROR_MESSAGE = "죄송합니다. 처리 중 오류가 발생했습니다."


class VoiceService:
    """Twilio Voice 통화 흐름을 만든다."""

    def __init__(self, settings: Settings | None = None, client: TwilioClient | None = None) -> None:
        self._settings = settings or get_settings()
        self._client_override = client

    # --- Twilio REST: 발신 ---

    def _require_twilio_config(self) -> tuple[str, str, str, str]:
        s = self._settings
        missing = [
            name
            for name, value in [
                ("TWILIO_ACCOUNT_SID", s.twilio_account_sid),
                ("TWILIO_AUTH_TOKEN", s.twilio_auth_token),
                ("TWILIO_FROM_NUMBER", s.twilio_from_number),
                ("PUBLIC_BASE_URL", s.public_base_url),
            ]
            if not value
        ]
        if missing:
            raise RuntimeError(f"필수 환경 변수 누락: {', '.join(missing)}")
        # mypy 위로용 — 위에서 None을 모두 걸렀음.
        return (
            s.twilio_account_sid,  # type: ignore[return-value]
            s.twilio_auth_token,  # type: ignore[return-value]
            s.twilio_from_number,  # type: ignore[return-value]
            s.public_base_url,  # type: ignore[return-value]
        )

    def _client(self) -> TwilioClient:
        if self._client_override is not None:
            return self._client_override
        sid, token, _, _ = self._require_twilio_config()
        return TwilioClient(sid, token)

    def place_outbound_call(
        self,
        session_id: str,
        to_number: str,
        greeting: str | None = None,
    ) -> OutboundCallResult:
        """에이전트가 사용자에게 전화를 건다.

        Twilio는 통화가 응답되면 우리 `/voice/answer/{session_id}` 를 호출해 첫 TwiML을 받는다.
        """
        _, _, from_number, base_url = self._require_twilio_config()
        answer_url = urljoin(base_url.rstrip("/") + "/", f"voice/answer/{session_id}")
        status_url = urljoin(base_url.rstrip("/") + "/", f"voice/status/{session_id}")

        # greeting 은 쿼리스트링으로 넘긴다 (간단; 실서비스에선 세션 스토어에 보관 권장).
        if greeting:
            from urllib.parse import urlencode
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
            "outbound call queued: sid=%s session=%s to=%s", call.sid, session_id, to_number
        )
        return OutboundCallResult(call_sid=call.sid, session_id=session_id, to_number=to_number)

    # --- TwiML 빌더 ---

    def _gather_action_url(self, session_id: str, turn: int) -> str:
        # 상대 경로면 Twilio가 통화 webhook 베이스(설정 URL)에 붙여서 호출한다.
        # 절대 URL이 있으면 그걸 우선 사용.
        if self._settings.public_base_url:
            return urljoin(
                self._settings.public_base_url.rstrip("/") + "/",
                f"voice/gather/{session_id}?turn={turn}",
            )
        return f"/voice/gather/{session_id}?turn={turn}"

    def _attach_gather(self, response: VoiceResponse, session_id: str, turn: int) -> Gather:
        return response.gather(  # type: ignore[no-any-return]
            input="speech",
            language=self._settings.voice_language,
            speech_timeout=self._settings.voice_speech_timeout,
            action=self._gather_action_url(session_id, turn),
            method="POST",
            # 사용자가 말하기 시작하면 Twilio의 자체 침묵 감지가 효율적으로 작동.
            speech_model="phone_call",
        )

    def build_greeting_twiml(self, session_id: str, greeting: Optional[str] = None) -> str:
        """첫 응답: 인사말 + Gather."""
        response = VoiceResponse()
        gather = self._attach_gather(response, session_id, turn=1)
        gather.say(
            greeting or DEFAULT_GREETING,
            voice=self._settings.voice_tts_voice,
            language=self._settings.voice_language,
        )
        # Gather가 무음으로 종료된 경우 다음 노드로 떨어진다 → 작별 인사 후 hangup.
        response.say(
            GOODBYE_MESSAGE,
            voice=self._settings.voice_tts_voice,
            language=self._settings.voice_language,
        )
        response.hangup()
        return str(response)

    def build_turn_twiml(self, session_id: str, answer: str, *, next_turn: int) -> str:
        """이전 사용자 발화에 대한 답변 + 다음 Gather."""
        response = VoiceResponse()
        response.say(
            answer,
            voice=self._settings.voice_tts_voice,
            language=self._settings.voice_language,
        )
        if next_turn > self._settings.voice_max_turns:
            response.say(
                LIMIT_REACHED_MESSAGE,
                voice=self._settings.voice_tts_voice,
                language=self._settings.voice_language,
            )
            response.hangup()
            return str(response)

        gather = self._attach_gather(response, session_id, turn=next_turn)
        # Gather 내부에 빈 prompt를 넣지 않는다 — 이전 답변 Say가 이미 끝났으므로 즉시 듣기 모드.
        del gather  # 객체만 만들면 자동으로 Response 에 attach 됨.

        response.say(
            GOODBYE_MESSAGE,
            voice=self._settings.voice_tts_voice,
            language=self._settings.voice_language,
        )
        response.hangup()
        return str(response)

    def build_error_twiml(self) -> str:
        response = VoiceResponse()
        response.say(
            ERROR_MESSAGE,
            voice=self._settings.voice_tts_voice,
            language=self._settings.voice_language,
        )
        response.hangup()
        return str(response)


# 모듈 단위 싱글톤.
_service: Optional[VoiceService] = None


def get_voice_service() -> VoiceService:
    global _service
    if _service is None:
        _service = VoiceService()
    return _service
