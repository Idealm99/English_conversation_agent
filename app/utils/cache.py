"""답변 캐시.

Redis가 설정돼 있으면 Redis를, 아니면 in-memory dict를 사용한다.
get/set 시그니처는 동일하므로 호출부에서 분기할 필요가 없다.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Optional

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class _InMemoryCache:
    """TTL을 지원하는 단순 dict 캐시 (테스트/로컬 개발용)."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[str]:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            expires_at, value = entry
            if expires_at < now:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        expires_at = time.time() + ttl_seconds
        with self._lock:
            self._store[key] = (expires_at, value)


class AnswerCache:
    """JSON 직렬화 + TTL을 갖춘 답변 캐시."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._ttl = self._settings.cache_ttl_seconds
        self._backend: Any
        if self._settings.redis_url:
            try:
                import redis  # 지연 import: redis 미사용 시 의존성 회피.

                self._backend = redis.Redis.from_url(
                    self._settings.redis_url, decode_responses=True
                )
                self._backend.ping()
                logger.info("Redis 캐시 백엔드 연결 완료: %s", self._settings.redis_url)
            except Exception as exc:  # 연결 실패 시 in-memory로 폴백.
                logger.warning("Redis 연결 실패, in-memory 캐시로 폴백: %s", exc)
                self._backend = _InMemoryCache()
        else:
            self._backend = _InMemoryCache()

    def get(self, key: str) -> Optional[dict[str, Any]]:
        raw = self._backend.get(key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("캐시 역직렬화 실패, 무효화: key=%s", key)
            return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        # redis.Redis.set(name, value, ex=...) 와 _InMemoryCache.set 둘 다 지원하도록 분기.
        if hasattr(self._backend, "setex"):
            self._backend.setex(key, self._ttl, payload)
        else:
            self._backend.set(key, payload, self._ttl)
