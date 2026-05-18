"""푸시 알림 발송 엔드포인트.

PoC 단계에서는 수동 트리거(POST /notifications/send)만 노출한다.
이후 스케줄러(APScheduler 등)를 붙여 정해진 시간에 자동 발송하도록 확장.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.schemas import NotificationRequest, NotificationResult
from app.services.device_store import DeviceStore, get_device_store
from app.services.push_service import PushService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@lru_cache(maxsize=1)
def get_push_service() -> PushService:
    return PushService()


@router.post("/send", response_model=NotificationResult)
def send(
    payload: NotificationRequest,
    store: DeviceStore = Depends(get_device_store),
    push: PushService = Depends(get_push_service),
) -> NotificationResult:
    device = store.get(payload.session_id)
    if device is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"등록된 디바이스 없음: session_id={payload.session_id}",
        )

    try:
        result = push.send(
            tokens=[device.push_token],
            title=payload.title,
            body=payload.body,
            data=payload.data,
        )
    except Exception as exc:
        logger.exception("push send failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "푸시 발송 실패") from exc
    return result
