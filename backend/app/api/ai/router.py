from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.security import AuthenticatedUser, require_user
from app.config import Settings, get_settings
from app.services.ai import analyst

router = APIRouter(prefix="/ai", tags=["ai"])


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


@router.get("/suggestions")
async def suggestions(
    _user: AuthenticatedUser = Depends(require_user),
) -> list[str]:
    return analyst.SUGGESTIONS


@router.post("/query")
async def query(
    payload: QueryRequest,
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return await analyst.answer(settings, payload.question)
