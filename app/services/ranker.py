"""검색 결과 랭킹.

벡터 거리(cosine distance, 0~2) → 점수(0~1)로 변환하고,
질문/답변 키워드 매칭 보너스를 더해 최종 정렬한다. min_score 미만은 제거.
"""

from __future__ import annotations

import logging
import math
from typing import Sequence

from app.core.config import Settings, get_settings
from app.models.schemas import FAQHit
from app.services.vector_store import VectorSearchResult
from app.utils.text_processing import normalize_query

logger = logging.getLogger(__name__)


def _distance_to_score(distance: float) -> float:
    """Chroma cosine distance(0=동일, 2=정반대) → 0~1 점수."""
    # cosine similarity = 1 - distance/... 가 아닌, cosine distance 자체가 1 - cos_sim.
    # 음수/0 미만으로 떨어지는 경우를 방지하기 위해 clamp.
    similarity = max(0.0, 1.0 - distance)
    return round(similarity, 6)


def _keyword_bonus(query: str, text: str) -> float:
    """간단한 토큰 겹침 비율 보너스 (최대 +0.1)."""
    if not query or not text:
        return 0.0
    q_tokens = {tok for tok in query.split() if len(tok) > 1}
    t_tokens = {tok for tok in text.split() if len(tok) > 1}
    if not q_tokens:
        return 0.0
    overlap = len(q_tokens & t_tokens) / len(q_tokens)
    return round(0.1 * overlap, 6)


class Ranker:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def rerank(
        self,
        query: str,
        candidates: Sequence[VectorSearchResult],
    ) -> list[FAQHit]:
        normalized_query = normalize_query(query)
        scored: list[FAQHit] = []

        for hit in candidates:
            base = _distance_to_score(hit.distance)
            bonus = _keyword_bonus(
                normalized_query,
                normalize_query(f"{hit.question} {hit.answer}"),
            )
            score = min(1.0, base + bonus)
            if math.isnan(score) or score < self._settings.min_score:
                continue
            scored.append(
                FAQHit(
                    faq_id=hit.faq_id,
                    question=hit.question,
                    answer=hit.answer,
                    score=score,
                    distance=hit.distance,
                    metadata=hit.metadata,
                )
            )

        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[: self._settings.rerank_top_k]
