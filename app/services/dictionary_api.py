"""Free Dictionary API (https://dictionaryapi.dev) 어댑터.

무료 + 인증 불필요 + 영영. 단어 1개에 대해 IPA, 품사별 정의, 예문, synonyms 제공.
구문/숙어 등은 404 가 잦으므로 호출부에서 None 폴백 처리 필요.

응답 스키마 (간략):
[
  {
    "word": "...",
    "phonetic": "...",                    # 대표 IPA
    "phonetics": [{"text": "...", "audio": "..."}, ...],
    "meanings": [
      {
        "partOfSpeech": "noun" | "verb" | ...,
        "definitions": [
          {"definition": "...", "example": "...", "synonyms": [...], "antonyms": [...]}
        ],
        "synonyms": [...],
        "antonyms": [...]
      }
    ]
  }
]
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


API_BASE = "https://api.dictionaryapi.dev/api/v2/entries/en"


async def fetch_dictionary_entry(
    word: str, *, client: httpx.AsyncClient | None = None
) -> Optional[dict[str, Any]]:
    """단어 항목을 가져온다. 404/네트워크 오류는 None.

    client 를 주입하면 테스트에서 mock 가능.
    """
    target = word.strip()
    if not target:
        return None

    url = f"{API_BASE}/{quote(target)}"

    async def _do(c: httpx.AsyncClient) -> Optional[dict[str, Any]]:
        try:
            resp = await c.get(url)
        except httpx.HTTPError as exc:
            logger.warning("dictionary api network error: %s", exc)
            return None
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            logger.warning("dictionary api unexpected status: %s", resp.status_code)
            return None
        try:
            data = resp.json()
        except Exception:
            return None
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
        return None

    if client is not None:
        return await _do(client)
    async with httpx.AsyncClient(timeout=5.0) as c:
        return await _do(c)


def format_entry_for_llm(entry: dict[str, Any]) -> str:
    """LLM 그라운디드 프롬프트의 입력으로 넣기 좋은 컴팩트 평문.

    원본 JSON을 통째로 넣으면 토큰만 잡아먹어 핵심만 추출한다 (각 품사당 상위 3 정의).
    """
    lines: list[str] = []
    word = entry.get("word", "")
    lines.append(f"WORD: {word}")

    phonetic = entry.get("phonetic") or _pick_phonetic(entry)
    if phonetic:
        lines.append(f"IPA: {phonetic}")

    for m in entry.get("meanings", []) or []:
        pos = m.get("partOfSpeech") or "?"
        lines.append(f"\n[{pos}]")
        for d in (m.get("definitions") or [])[:3]:
            defn = (d.get("definition") or "").strip()
            if not defn:
                continue
            lines.append(f"- def: {defn}")
            ex = (d.get("example") or "").strip()
            if ex:
                lines.append(f'  e.g. "{ex}"')
        syns = m.get("synonyms") or []
        ants = m.get("antonyms") or []
        if syns:
            lines.append(f"  synonyms: {', '.join(syns[:6])}")
        if ants:
            lines.append(f"  antonyms: {', '.join(ants[:6])}")

    return "\n".join(lines).strip()


def _pick_phonetic(entry: dict[str, Any]) -> str | None:
    for p in entry.get("phonetics", []) or []:
        text = (p or {}).get("text")
        if text:
            return text
    return None
