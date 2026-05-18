"""디바이스(푸시 토큰) 등록/해제 엔드포인트."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.schemas import DeviceRecord, DeviceRegisterRequest
from app.services.device_store import DeviceStore, get_device_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("/register", response_model=DeviceRecord, status_code=status.HTTP_201_CREATED)
def register(
    payload: DeviceRegisterRequest,
    store: DeviceStore = Depends(get_device_store),
) -> DeviceRecord:
    record = DeviceRecord(
        session_id=payload.session_id,
        push_token=payload.push_token,
        platform=payload.platform,
        locale=payload.locale,
        updated_at=datetime.utcnow(),
    )
    store.upsert(record)
    logger.info("device registered: session=%s platform=%s", record.session_id, record.platform)
    return record


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def unregister(
    session_id: str,
    store: DeviceStore = Depends(get_device_store),
) -> None:
    removed = store.delete(session_id)
    if removed == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")
