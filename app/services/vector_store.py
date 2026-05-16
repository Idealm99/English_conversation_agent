"""Chroma 벡터 저장소 래퍼.

PersistentClient를 사용해 디스크에 저장하며, 컬렉션이 없으면 생성한다.
임베딩 함수는 외부에서 주입(EmbeddingClient)하여 모델 교체를 쉽게 한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import Settings, get_settings
from app.core.embeddings import EmbeddingClient
from app.models.schemas import FAQDocument

logger = logging.getLogger(__name__)


@dataclass
class VectorSearchResult:
    """벡터 검색 단일 결과."""

    faq_id: str
    question: str
    answer: str
    distance: float
    metadata: dict


class VectorStore:
    """Chroma 컬렉션에 대한 얇은 추상화 (upsert / query)."""

    def __init__(
        self,
        settings: Settings | None = None,
        embedder: EmbeddingClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._embedder = embedder or EmbeddingClient(self._settings)
        self._settings.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(self._settings.chroma_persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self._settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, documents: Sequence[FAQDocument]) -> int:
        """FAQ 문서들을 임베딩 후 컬렉션에 적재."""
        if not documents:
            return 0
        # 검색 품질을 위해 question + answer를 함께 임베딩한다.
        texts = [f"질문: {doc.question}\n답변: {doc.answer}" for doc in documents]
        embeddings = self._embedder.embed_documents(texts)

        self._collection.upsert(
            ids=[doc.faq_id for doc in documents],
            embeddings=embeddings,
            documents=texts,
            metadatas=[
                {
                    "faq_id": doc.faq_id,
                    "question": doc.question,
                    "answer": doc.answer,
                    "category": doc.category or "",
                    # Chroma 메타데이터는 스칼라만 허용하므로 태그는 콤마 join.
                    "tags": ",".join(doc.tags),
                }
                for doc in documents
            ],
        )
        return len(documents)

    def query(self, query_text: str, top_k: int) -> list[VectorSearchResult]:
        """쿼리 텍스트로 유사 FAQ를 검색."""
        embedding = self._embedder.embed_query(query_text)
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            include=["metadatas", "documents", "distances"],
        )

        # Chroma는 배치 쿼리를 가정해 결과를 2차원 list로 반환한다. 첫 배치만 사용.
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        ids = (result.get("ids") or [[]])[0]

        hits: list[VectorSearchResult] = []
        for faq_id, meta, dist in zip(ids, metadatas, distances):
            meta = meta or {}
            hits.append(
                VectorSearchResult(
                    faq_id=str(meta.get("faq_id") or faq_id),
                    question=str(meta.get("question", "")),
                    answer=str(meta.get("answer", "")),
                    distance=float(dist),
                    metadata=dict(meta),
                )
            )
        return hits

    def count(self) -> int:
        return self._collection.count()
