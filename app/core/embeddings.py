"""Vertex AI 임베딩 래퍼.

google-cloud-aiplatform(vertexai) SDK 사용. 기본 모델은 다국어 임베딩이며
한국어 FAQ에 적합한 'text-multilingual-embedding-002' (768차원).
ADC(Application Default Credentials)로 인증한다.
"""

from __future__ import annotations

import logging
import threading
from typing import Sequence

import vertexai
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


# vertexai.init 은 프로세스 전역 상태를 변경하므로 한 번만 호출.
_init_lock = threading.Lock()
_initialized = False


def _ensure_vertex_initialized(settings: Settings) -> None:
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        if not settings.gcp_project:
            raise RuntimeError(
                "GOOGLE_CLOUD_PROJECT(또는 GCP_PROJECT) 환경 변수가 필요합니다."
            )
        vertexai.init(project=settings.gcp_project, location=settings.gcp_location)
        _initialized = True


class EmbeddingClient:
    """배치 임베딩 생성을 담당하는 얇은 래퍼."""

    # task_type 은 검색 품질에 큰 영향을 주므로 문서/쿼리에 맞게 분리.
    DOC_TASK = "RETRIEVAL_DOCUMENT"
    QUERY_TASK = "RETRIEVAL_QUERY"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        _ensure_vertex_initialized(self._settings)
        self._model = TextEmbeddingModel.from_pretrained(self._settings.embedding_model)

    @property
    def model(self) -> str:
        return self._settings.embedding_model

    def _embed(self, texts: Sequence[str], task_type: str) -> list[list[float]]:
        if not texts:
            return []
        inputs = [
            TextEmbeddingInput(text=t.replace("\n", " ").strip(), task_type=task_type)
            for t in texts
        ]
        result = self._model.get_embeddings(inputs)
        return [emb.values for emb in result]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """여러 FAQ 문서를 한 번에 임베딩한다."""
        return self._embed(texts, self.DOC_TASK)

    def embed_query(self, text: str) -> list[float]:
        """단일 쿼리 임베딩."""
        return self._embed([text], self.QUERY_TASK)[0]
