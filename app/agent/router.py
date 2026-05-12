import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import engine
from app.agent.llm import NoLLMAvailableError, get_llm
from app.agent.tools import build_registry
from app.util.auth import AuthHandler
from app.util.db import get_session

logger = logging.getLogger(__name__)

agent_router = APIRouter(prefix="/agent", tags=["agent"])
auth_handler = AuthHandler()


def _get_current_user(request: Request) -> str:
    token = request.cookies.get("token", "")
    user_id = auth_handler.decode_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    return user_id


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


class ConfirmRequest(BaseModel):
    fn_name: str
    kwargs: dict
    approved: bool
    message: str = ""
    history: list[dict] = []


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
        llm = get_llm() if body.approved else None
    except NoLLMAvailableError:
        llm = None
    try:
        result = await engine.confirm(
            body.fn_name, body.kwargs, body.approved, registry,
            message=body.message, history=body.history, llm=llm,
        )
    except Exception:
        logger.exception("engine.confirm failed")
        return {"status": "error", "message": "작업 처리 중 오류가 발생했습니다.", "pending": None}
    return {"status": result.status, "message": result.message, "pending": result.pending, "redirect": result.redirect}
