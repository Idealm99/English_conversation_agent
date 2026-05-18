"""Twilio Media Streams ↔ GCP STT/TTS 실시간 양방향 파이프라인.

원래 한 클래스(`MediaStreamHandler`)가 다 처리하던 것을 SRP에 맞게 분리:

  - `TwilioMediaTransport` : WebSocket 메시지 프로토콜만 책임.
        (connected/start/media/stop/clear JSON 인코딩·디코딩)
  - `SpeechRecognitionStream` : GCP STT streaming_recognize 어댑터.
        오디오 청크 → Transcript stream.
  - `SpeechSynthesizer` : GCP TTS 어댑터. text → μ-law 8kHz raw bytes.
  - `MediaStreamHandler` : 위 세 컴포넌트를 묶는 오케스트레이터.
        라이프사이클(인사 → STT 루프 → barge-in → 종료)만 담당.

barge-in 규칙: TTS 재생 중 STT가 interim transcript 를 내놓으면 TTS 태스크를
cancel + transport.send_clear() 로 Twilio 버퍼 비움.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import AsyncIterator, Optional

from fastapi import WebSocket, WebSocketDisconnect
from google.cloud import speech_v1 as speech
from google.cloud import texttospeech_v1 as texttospeech

from app.core.config import Settings, get_settings
from app.models.schemas import ChatRequest
from app.services.protocols import ChatGateway, Transcript

logger = logging.getLogger(__name__)


# Twilio Media Streams: μ-law 8000Hz. 1 byte/sample. 20ms = 160 bytes.
TWILIO_SAMPLE_RATE = 8000
FRAME_BYTES = 160
FRAME_INTERVAL = 0.02  # 20ms

GENERIC_ERROR_TEXT = "죄송합니다. 처리 중 오류가 발생했습니다."


# ---------------------------------------------------------------------------
# Twilio Media WebSocket 프로토콜 어댑터.
# ---------------------------------------------------------------------------

class TwilioMediaTransport:
    """Twilio Media Streams WS의 JSON 프레임을 audio bytes 단위로 추상화."""

    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket
        self._stream_sid: Optional[str] = None
        self._closing = False

    @property
    def stream_sid(self) -> Optional[str]:
        return self._stream_sid

    @property
    def closing(self) -> bool:
        return self._closing

    async def wait_for_start(self) -> str:
        """connected → start 이벤트까지 소비하고 streamSid 반환."""
        while not self._closing:
            try:
                raw = await self._ws.receive_text()
            except WebSocketDisconnect:
                self._closing = True
                raise
            msg = json.loads(raw)
            event = msg.get("event")
            if event == "start":
                self._stream_sid = msg["start"]["streamSid"]
                assert self._stream_sid is not None
                logger.info("stream started: streamSid=%s", self._stream_sid)
                return self._stream_sid
            if event == "stop":
                self._closing = True
                raise WebSocketDisconnect()
            # 'connected' 등 다른 이벤트는 건너뛴다.
        raise WebSocketDisconnect()

    async def iter_inbound_audio(self) -> AsyncIterator[bytes]:
        """media 이벤트의 base64 디코딩된 μ-law 청크를 yield. stop 시 종료."""
        try:
            while not self._closing:
                raw = await self._ws.receive_text()
                msg = json.loads(raw)
                event = msg.get("event")
                if event == "media":
                    yield base64.b64decode(msg["media"]["payload"])
                elif event == "stop":
                    logger.info("stream stop received")
                    self._closing = True
                    return
                # mark/dtmf 등은 무시.
        except WebSocketDisconnect:
            self._closing = True

    async def send_audio_chunk(self, chunk: bytes) -> None:
        if self._closing or not self._stream_sid:
            return
        msg = {
            "event": "media",
            "streamSid": self._stream_sid,
            "media": {"payload": base64.b64encode(chunk).decode("ascii")},
        }
        try:
            await self._ws.send_text(json.dumps(msg))
        except WebSocketDisconnect:
            self._closing = True

    async def send_clear(self) -> None:
        if self._closing or not self._stream_sid:
            return
        try:
            await self._ws.send_text(
                json.dumps({"event": "clear", "streamSid": self._stream_sid})
            )
        except Exception:
            pass

    def mark_closing(self) -> None:
        self._closing = True


# ---------------------------------------------------------------------------
# GCP STT 어댑터.
# ---------------------------------------------------------------------------

class SpeechRecognitionStream:
    """GCP Speech-to-Text streaming_recognize 래퍼.

    transcribe(queue) 가 audio 큐에서 청크를 꺼내며 transcript 를 yield.
    None 청크가 들어오면 sentinel 로 보고 스트림 종료.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = speech.SpeechAsyncClient()

    async def transcribe(
        self, audio_queue: "asyncio.Queue[Optional[bytes]]"
    ) -> AsyncIterator[Transcript]:
        logger.info(
            "STT loop starting: lang=%s model=%s",
            self._settings.stt_language,
            self._settings.stt_model or "(default)",
        )
        config_kwargs: dict = {
            "encoding": speech.RecognitionConfig.AudioEncoding.MULAW,
            "sample_rate_hertz": TWILIO_SAMPLE_RATE,
            "language_code": self._settings.stt_language,
            "enable_automatic_punctuation": True,
        }
        if self._settings.stt_model:
            config_kwargs["model"] = self._settings.stt_model
        config = speech.RecognitionConfig(**config_kwargs)
        streaming_config = speech.StreamingRecognitionConfig(
            config=config, interim_results=True
        )

        # 진단 카운터.
        chunk_count = 0
        response_count = 0

        async def request_iter():
            nonlocal chunk_count
            try:
                yield speech.StreamingRecognizeRequest(streaming_config=streaming_config)
                logger.info("STT config sent, awaiting audio…")
                while True:
                    chunk = await audio_queue.get()
                    if chunk is None:
                        logger.info("STT request_iter received sentinel — closing")
                        return
                    chunk_count += 1
                    if chunk_count == 1:
                        logger.info("STT first audio chunk: %d bytes", len(chunk))
                    elif chunk_count % 100 == 0:
                        logger.info(
                            "STT audio chunks=%d (~%.1fs of audio fed)",
                            chunk_count,
                            chunk_count * FRAME_INTERVAL,
                        )
                    yield speech.StreamingRecognizeRequest(audio_content=chunk)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("STT request_iter crashed")
                raise

        try:
            responses = await self._client.streaming_recognize(requests=request_iter())
            logger.info("STT streaming_recognize returned, iterating responses")
            async for response in responses:
                response_count += 1
                for result in response.results:
                    if not result.alternatives:
                        continue
                    text = result.alternatives[0].transcript.strip()
                    if not text:
                        continue
                    yield Transcript(text=text, is_final=bool(result.is_final))
            logger.info(
                "STT stream ended cleanly (responses=%d, chunks=%d)",
                response_count,
                chunk_count,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "STT crashed (chunks_fed=%d, responses=%d)",
                chunk_count,
                response_count,
            )

    async def aclose(self) -> None:
        try:
            await self._client.transport.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# GCP TTS 어댑터.
# ---------------------------------------------------------------------------

class SpeechSynthesizer:
    """GCP Text-to-Speech 래퍼. text → raw μ-law 8kHz bytes (전화 호환)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = texttospeech.TextToSpeechAsyncClient()

    async def synthesize(self, text: str) -> bytes:
        response = await self._client.synthesize_speech(
            request=texttospeech.SynthesizeSpeechRequest(
                input=texttospeech.SynthesisInput(text=text),
                voice=texttospeech.VoiceSelectionParams(
                    language_code=self._settings.stt_language,
                    name=self._settings.tts_voice_name,
                ),
                audio_config=texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MULAW,
                    sample_rate_hertz=TWILIO_SAMPLE_RATE,
                ),
            )
        )
        return response.audio_content

    async def aclose(self) -> None:
        try:
            await self._client.transport.close()
        except Exception:
            pass


def iter_frames(audio: bytes, frame_bytes: int = FRAME_BYTES):
    """raw 오디오 바이트를 fixed-size 프레임으로 분할."""
    for i in range(0, len(audio), frame_bytes):
        yield audio[i : i + frame_bytes]


# ---------------------------------------------------------------------------
# 오케스트레이터.
# ---------------------------------------------------------------------------

class MediaStreamHandler:
    """단일 통화의 라이프사이클을 조정한다.

    역할:
      1) start 이벤트로 streamSid 확보 후 인사말 TTS 송출 시작
      2) WS 수신 루프(`_receive_loop`)와 STT 루프(`_stt_loop`) 동시 가동
      3) STT final 발화에 대해 ChatGateway.handle(...) 호출 후 답변 TTS 송출
      4) STT interim 이 들어오면 진행 중 TTS를 cancel + transport.send_clear()
    """

    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
        chat: ChatGateway,
        greeting: Optional[str] = None,
        settings: Settings | None = None,
        transport: TwilioMediaTransport | None = None,
        recognizer: SpeechRecognitionStream | None = None,
        synthesizer: SpeechSynthesizer | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._session_id = session_id
        self._chat = chat
        self._greeting = greeting or self._settings.voice_greeting
        self._transport = transport or TwilioMediaTransport(websocket)
        self._recognizer = recognizer or SpeechRecognitionStream(self._settings)
        self._synthesizer = synthesizer or SpeechSynthesizer(self._settings)

        self._audio_in: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        self._tts_task: Optional[asyncio.Task[None]] = None

    # --- entry point -------------------------------------------------------

    async def run(self) -> None:
        try:
            await self._transport.wait_for_start()
        except WebSocketDisconnect:
            return

        # 인사말 비동기 송출.
        self._tts_task = asyncio.create_task(self._speak(self._greeting))

        try:
            await asyncio.gather(self._receive_loop(), self._stt_loop())
        except WebSocketDisconnect:
            logger.info("ws disconnected: session=%s", self._session_id)
        finally:
            await self._cleanup()

    # --- transport / audio plumbing ---------------------------------------

    async def _receive_loop(self) -> None:
        async for chunk in self._transport.iter_inbound_audio():
            await self._audio_in.put(chunk)
        # 스트림 종료 — STT request_iter 종료시키기 위한 sentinel.
        await self._audio_in.put(None)

    async def _stt_loop(self) -> None:
        async for transcript in self._recognizer.transcribe(self._audio_in):
            if self._transport.closing:
                return
            if transcript.is_final:
                logger.info("STT final: %r", transcript.text)
                asyncio.create_task(self._handle_user_turn(transcript.text))
            else:
                # interim — TTS 재생 중이면 barge-in.
                if self._tts_task and not self._tts_task.done():
                    logger.info("STT interim → barge-in: %r", transcript.text[:40])
                    await self._barge_in()

    # --- conversation turn -------------------------------------------------

    async def _handle_user_turn(self, transcript: str) -> None:
        await self._barge_in()
        try:
            response = await asyncio.to_thread(
                self._chat.handle,
                ChatRequest(session_id=self._session_id, message=transcript),
            )
            answer = response.answer or GENERIC_ERROR_TEXT
        except Exception:
            logger.exception("chat pipeline failed")
            answer = GENERIC_ERROR_TEXT
        if self._transport.closing:
            return
        self._tts_task = asyncio.create_task(self._speak(answer))

    # --- tts ---------------------------------------------------------------

    async def _speak(self, text: str) -> None:
        if not text or self._transport.closing:
            return
        try:
            audio = await self._synthesizer.synthesize(text)
            await self._stream_audio(audio)
        except asyncio.CancelledError:
            logger.debug("TTS cancelled (barge-in)")
            raise
        except Exception:
            logger.exception("TTS failed: text=%r", text[:80])

    async def _stream_audio(self, audio: bytes) -> None:
        for frame in iter_frames(audio):
            if self._transport.closing:
                return
            await self._transport.send_audio_chunk(frame)
            # cancel 시 즉시 멈춰서 barge-in 응답 빠르게.
            await asyncio.sleep(FRAME_INTERVAL)

    async def _barge_in(self) -> None:
        task = self._tts_task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._tts_task = None
        await self._transport.send_clear()

    # --- cleanup -----------------------------------------------------------

    async def _cleanup(self) -> None:
        self._transport.mark_closing()
        if self._tts_task and not self._tts_task.done():
            self._tts_task.cancel()
            try:
                await self._tts_task
            except (asyncio.CancelledError, Exception):
                pass
        # STT request_iter 가 종료되도록 sentinel 추가.
        await self._audio_in.put(None)
        await self._recognizer.aclose()
        await self._synthesizer.aclose()
