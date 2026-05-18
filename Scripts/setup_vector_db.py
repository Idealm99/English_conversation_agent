"""벡터DB 초기화 스크립트.

사용법:
    python scripts/setup_vector_db.py            # 기본 data/faqs.json 사용
    python scripts/setup_vector_db.py path.json  # 커스텀 경로

환경 변수 OPENAI_API_KEY 가 설정돼 있어야 한다.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# 스크립트를 단독 실행해도 app/* 를 import 할 수 있도록 경로 보정.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.core.embeddings import EmbeddingClient  # noqa: E402
from app.models.schemas import FAQDocument  # noqa: E402
from app.services.vector_store import VectorStore  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("setup_vector_db")


def load_faqs(path: Path) -> list[FAQDocument]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"FAQ 파일은 list여야 합니다: {path}")
    return [FAQDocument(**item) for item in data]


def main(argv: list[str]) -> int:
    settings = get_settings()
    faq_path = Path(argv[1]) if len(argv) > 1 else settings.faq_data_path
    if not faq_path.exists():
        logger.error("FAQ 파일을 찾을 수 없습니다: %s", faq_path)
        return 1

    docs = load_faqs(faq_path)
    logger.info("FAQ %d건 로드 완료 (from %s)", len(docs), faq_path)

    store = VectorStore(settings, embedder=EmbeddingClient(settings))
    n = store.upsert(docs)
    logger.info("벡터DB upsert 완료: %d건, 총 %d건 저장", n, store.count())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
