import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import engine
from app.agent.llm import NoLLMAvailableError, get_llm
from app.agent.tools import build_registry
from app.util.auth import get_current_user as _get_current_user
from app.util.db import get_session

logger = logging.getLogger(__name__)

agent_router = APIRouter(prefix="/agent", tags=["agent"])


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


class ConfirmRequest(BaseModel):
    fn_name: str
    kwargs: dict
    approved: bool
    queue: list[dict] = []


@agent_router.post("/chat")
async def chat(
    body: ChatRequest,
    user: str = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        llm = get_llm()
    except NoLLMAvailableError as e:
        return {"status": "error", "message": str(e), "pending": None}
    registry = build_registry(session)
    try:
        result = await engine.run(body.message, body.history, registry, llm)
    except Exception:
        logger.exception("engine.run failed")
        return {"status": "error", "message": "LLM 요청 중 오류가 발생했습니다.", "pending": None}
    return {"status": result.status, "message": result.message, "pending": result.pending, "redirect": result.redirect}


@agent_router.post("/confirm")
async def confirm(
    body: ConfirmRequest,
    user: str = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
):
    registry = build_registry(session)
    try:
        result = await engine.confirm(
            body.fn_name, body.kwargs, body.approved, registry, queue=body.queue,
        )
    except Exception:
        logger.exception("engine.confirm failed")
        return {"status": "error", "message": "작업 처리 중 오류가 발생했습니다.", "pending": None}
    return {"status": result.status, "message": result.message, "pending": result.pending, "redirect": result.redirect}
