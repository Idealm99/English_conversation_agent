"""쿼리/문서 전처리 유틸.

비교적 가벼운 정규화만 수행한다. 한국어 형태소 분석은 별도 패키지가 필요하므로
여기서는 공백/제어문자/대소문자 정규화만 적용한다.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata


_WHITESPACE_RE = re.compile(r"\s+")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]")


def normalize_text(text: str) -> str:
    """공백/제어문자/유니코드 정규화."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def normalize_query(text: str) -> str:
    """검색용 쿼리 정규화 (소문자 변환 포함)."""
    return normalize_text(text).lower()


def hash_key(*parts: str) -> str:
    """캐시 키 생성을 위한 안정적인 SHA-1 해시."""
    raw = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()
