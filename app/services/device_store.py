"""TinyDB 기반 디바이스 저장소.

세션 ID 하나당 푸시 토큰 1개를 유지한다 (같은 사용자가 앱을 재설치하면 토큰 갱신).
멀티 디바이스 지원이 필요하면 (session_id, push_token) 복합키로 확장 가능.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Optional

from tinydb import Query, TinyDB

from app.core.config import Settings, get_settings
from app.models.schemas import DeviceRecord

logger = logging.getLogger(__name__)


class DeviceStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._settings.device_db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = TinyDB(str(self._settings.device_db_path), encoding="utf-8")
        self._lock = threading.Lock()

    def upsert(self, record: DeviceRecord) -> None:
        Device = Query()
        payload = record.model_dump(mode="json")
        payload["updated_at"] = datetime.utcnow().isoformat()
        with self._lock:
            self._db.upsert(payload, Device.session_id == record.session_id)

    def get(self, session_id: str) -> Optional[DeviceRecord]:
        Device = Query()
        with self._lock:
            found = self._db.get(Device.session_id == session_id)
        return DeviceRecord(**found) if found else None

    def all(self) -> list[DeviceRecord]:
        with self._lock:
            rows = list(self._db)
        return [DeviceRecord(**row) for row in rows]

    def delete(self, session_id: str) -> int:
        Device = Query()
        with self._lock:
            removed = self._db.remove(Device.session_id == session_id)
        return len(removed)


# 모듈 단위 싱글톤.
_store: Optional[DeviceStore] = None


def get_device_store() -> DeviceStore:
    global _store
    if _store is None:
        _store = DeviceStore()
    return _store
