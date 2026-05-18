"""캐릭터 목록 조회 — 프론트엔드 홈 화면에서 사용."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.characters import list_characters
from app.models.schemas import CharacterDTO

router = APIRouter(prefix="/characters", tags=["characters"])


@router.get("", response_model=list[CharacterDTO])
def get_characters() -> list[CharacterDTO]:
    return [
        CharacterDTO(
            id=c.id,
            name=c.name,
            emoji=c.emoji,
            tagline=c.tagline,
            description=c.description,
        )
        for c in list_characters()
    ]
