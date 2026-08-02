"""실소켓 스모크 1개 — h11 을 실제로 태우는 유일한 테스트.

`ASGITransport` 는 ASGI 앱을 직접 부르므로 HTTP 바이트를 파싱하지 않는다. 실측
2026-08-02: 그 경로에서 h11 프레임은 **0** 이다. `osv-scanner.toml` 이 h11 을 실사용
경로로 등재했으므로, 오라클이 그것을 하나도 안 타면 h11 업그레이드는 여전히
검증 불가로 남는다.

**하나만 둔다.** 전부 실소켓으로 돌리면 포트·스레드·타이밍이 들어와 느려지고 flaky
표면이 커진다 — 자주 안 도는 오라클은 오라클이 아니다. 나머지는 ASGITransport 다.

uvicorn 은 `pyproject.toml` 에 이미 선언된 의존성이다 (의존성 추가 아님).
"""

import asyncio
import socket

import httpx
import pytest
import uvicorn


def _free_port() -> int:
    """0번 포트로 바인드해 커널이 준 포트를 쓴다 — 하드코딩하면 충돌한다."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
async def live_server(seeded_app):
    """인프로세스 uvicorn. 같은 이벤트 루프에서 서버 태스크로 돌린다."""
    port = _free_port()
    server_config = uvicorn.Config(
        seeded_app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"
    )
    server = uvicorn.Server(server_config)
    task = asyncio.create_task(server.serve())

    for _ in range(200):  # 최대 ~2초
        if server.started:
            break
        await asyncio.sleep(0.01)
    else:
        server.should_exit = True
        await task
        pytest.fail("uvicorn 이 2초 안에 안 떴다")

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


async def test_app_serves_over_a_real_socket(live_server):
    """h11 이 실제 요청·응답을 파싱한다.

    상태 코드만 보는 스모크다 — 응답 내용은 ASGITransport 테스트들이 이미 본다.
    여기서 보는 것은 "실제 HTTP 스택 위에서도 앱이 서빙되는가" 하나다.
    """
    async with httpx.AsyncClient(base_url=live_server, follow_redirects=False) as client:
        res = await client.get("/")
        assert res.status_code == 200
        assert res.json() == {"200": "ok"}

        # 인증 경계도 실 소켓에서 같은가 — 리다이렉트가 ASGI 층 산물이 아님을 본다.
        protected = await client.get("/admin/attendee")
        assert protected.status_code == 307
        assert protected.headers["location"] == "/login"


async def test_real_socket_path_executes_h11(live_server):
    """음성 대조의 반대편 — 이 경로가 정말 h11 을 태우는지 프레임으로 확인한다.

    `test_http_env.py` 는 ASGITransport 에서 h11 이 0 임을 고정한다. 두 단언이
    짝이다: 하나라도 없으면 "h11 을 덮는다"가 검증되지 않는다.
    """
    import collections
    import sys

    counts = collections.Counter()

    def tracer(frame, event, arg):
        if event != "call":
            return
        if "/site-packages/h11/" in frame.f_code.co_filename:
            counts["h11"] += 1

    async with httpx.AsyncClient(base_url=live_server, follow_redirects=False) as client:
        sys.setprofile(tracer)
        try:
            await client.get("/")
        finally:
            sys.setprofile(None)

    assert counts["h11"] > 0, (
        "실소켓 경로에서도 h11 프레임이 0 이다 — 이 테스트가 h11 을 덮는다는 주장이 거짓이다"
    )
