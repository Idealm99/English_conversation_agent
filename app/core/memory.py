"""세션별 대화 히스토리 메모리.

기본 구현은 프로세스 내 in-memory dict이며, 길이 제한이 있는 슬라이딩 윈도우다.
멀티 프로세스/스케일아웃 환경에서는 Redis 기반 구현으로 교체 가능하도록
add_turn/get_history 두 메서드만 노출한다.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from typing import Deque

from app.core.config import Settings, get_settings


class ConversationMemory:
    """세션 ID 기준 최근 N 턴(사용자+어시스턴트)을 보관."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        # 한 턴 = (user, assistant) → 메시지 두 개. 보관 메시지 수는 max_turns * 2.
        self._max_messages = self._settings.memory_max_turns * 2
        self._store: dict[str, Deque[dict[str, str]]] = defaultdict(
            lambda: deque(maxlen=self._max_messages)
        )
        self._lock = threading.Lock()

    def add_turn(self, session_id: str, user_message: str, assistant_message: str) -> None:
        with self._lock:
            buf = self._store[session_id]
            buf.append({"role": "user", "content": user_message})
            buf.append({"role": "assistant", "content": assistant_message})

    def get_history(self, session_id: str) -> list[dict[str, str]]:
        with self._lock:
            return list(self._store.get(session_id, ()))

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._store.pop(session_id, None)
