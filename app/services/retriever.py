"""검색 로직.

VectorStore를 호출하고, 쿼리 정규화 / top_k 보정 정도만 담당한다.
랭킹/필터링은 Ranker에 위임한다.
"""

from __future__ import annotations

import logging

from app.core.config import Settings, get_settings
from app.services.vector_store import VectorSearchResult, VectorStore
from app.utils.text_processing import normalize_query

logger = logging.getLogger(__name__)


class Retriever:
    def __init__(
        self,
        vector_store: VectorStore,
        settings: Settings | None = None,
    ) -> None:
        self._store = vector_store
        self._settings = settings or get_settings()

    def search(self, query: str, top_k: int | None = None) -> list[VectorSearchResult]:
        normalized = normalize_query(query)
        if not normalized:
            return []
        k = top_k or self._settings.retrieval_top_k
        hits = self._store.query(normalized, top_k=k)
        logger.debug("retrieval: query=%r → %d hits", normalized, len(hits))
        return hits
