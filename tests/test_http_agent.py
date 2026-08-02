"""에이전트 라우트가 **외부 유료 호출을 내지 않는지** (AC-8).

실측 2026-08-02: 이 가드를 두기 전, 파이프라인 비평가가 검증 중 `/agent/chat` 을
때렸고 개발자의 실제 `GROQ_API_KEY` 로 Groq 호출이 나갔다. 오라클이 돌 때마다 돈이
나가면 자주 못 돌리고, 자주 안 도는 오라클은 오라클이 아니다.

`conftest.py` 가 키를 빈 값으로 세우고, 여기서 그 결과를 단언한다.
"""

from app import config


def test_llm_keys_are_empty_in_tests():
    """가드 자체를 먼저 본다. 이게 깨지면 아래 테스트가 외부 호출을 낸다."""
    assert config.GROQ_API_KEY == ""
    assert config.GEMINI_API_KEY == ""


def test_get_llm_refuses_without_keys():
    """`get_llm()` 이 키 없이 어댑터를 만들지 않는다.

    `app/agent/llm.py` 의 모듈 전역 캐시(`_llm_instance`)는 최초 결과가 프로세스
    끝까지 산다 — 예외는 캐시되지 않으므로 여기서 잡히는 것이 그 전제를 지킨다.
    (`codebase-conventions.md` § 숨은 결합)
    """
    import pytest

    from app.agent.llm import NoLLMAvailableError, get_llm

    with pytest.raises(NoLLMAvailableError):
        get_llm()


async def test_chat_returns_error_without_calling_out(admin_client):
    """R-6: 키가 없으면 `/agent/chat` 은 200 + `status:"error"` 다.

    500 이 아니라 200 인 것이 현행 동작이다 — 라우트가 예외를 삼키고 구조화된
    에러를 준다. 그것을 고정한다.
    """
    res = await admin_client.post("/agent/chat", json={"message": "안녕", "history": []})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "error"
    assert body["pending"] is None
    assert body["message"]


async def test_confirm_rejects_unknown_function(admin_client):
    """`/agent/confirm` 은 LLM 을 안 타는 경로다 — 레지스트리만 본다."""
    res = await admin_client.post(
        "/agent/confirm",
        json={"fn_name": "no_such_tool", "kwargs": {}, "approved": True, "queue": []},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "error"
