"""Expo Push API 호출 래퍼.

Expo Notifications(앱 쪽)와 짝을 이룬다. 토큰 형식은 'ExponentPushToken[...]'.
나중에 bare React Native + 직접 FCM/APNs로 전환하려면 이 모듈만 교체하면 된다.

레퍼런스: https://docs.expo.dev/push-notifications/sending-notifications/
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

import httpx

from app.core.config import Settings, get_settings
from app.models.schemas import NotificationResult

logger = logging.getLogger(__name__)


class PushService:
    """Expo Push API에 알림을 전송한다."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def _headers(self) -> dict[str, str]:
        headers = {
            "accept": "application/json",
            "accept-encoding": "gzip, deflate",
            "content-type": "application/json",
        }
        if self._settings.expo_access_token:
            headers["authorization"] = f"Bearer {self._settings.expo_access_token}"
        return headers

    def _build_messages(
        self,
        tokens: Iterable[str],
        title: str,
        body: str,
        data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        # Expo 토큰만 필터링 (FCM/APNs 토큰이 섞여 있어도 무시).
        return [
            {
                "to": token,
                "title": title,
                "body": body,
                "data": data,
                "sound": "default",
                "priority": "high",
            }
            for token in tokens
            if token.startswith("ExponentPushToken[") or token.startswith("ExpoPushToken[")
        ]

    def send(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> NotificationResult:
        messages = self._build_messages(tokens, title, body, data or {})
        if not messages:
            logger.info("발송할 Expo 토큰 없음 (tokens=%d)", len(tokens))
            return NotificationResult(delivered=0, failed=0, receipts=[])

        # Expo는 단일/배열 모두 받지만 배열로 통일.
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                self._settings.expo_push_url,
                json=messages,
                headers=self._headers(),
            )
            response.raise_for_status()
            payload = response.json()

        # 응답: { "data": [{"status":"ok","id":"..."} 또는 {"status":"error","message":..} ...] }
        receipts: list[dict[str, Any]] = []
        delivered = 0
        failed = 0
        for ticket in payload.get("data", []):
            receipts.append(ticket)
            if ticket.get("status") == "ok":
                delivered += 1
            else:
                failed += 1
                logger.warning("Expo push 실패: %s", ticket)

        return NotificationResult(delivered=delivered, failed=failed, receipts=receipts)
