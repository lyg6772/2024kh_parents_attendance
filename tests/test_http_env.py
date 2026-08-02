"""이 오라클이 **실제로 무엇을 덮는지**를 실행으로 남긴다 (AC-1, AC-5).

이 파일이 이 작업의 핵심이다. "우리 테스트가 jinja2 를 실행한다"는 **주장**은
검증 없이는 믿을 수 없다 — 실측 2026-08-02: `sys.modules` 로 재면 h11 도 "있음"으로
나오지만 실행 프레임은 **0** 이다. import 는 되는데 실행이 0인 상태가 정확히
`osv-scanner.toml` 이 경고하는 "가짜 초록"이다.

그래서 프레임을 센다. `> 0` 하한만 단언한다 — 정확한 수치를 박으면 라이브러리를
올릴 때 깨지고, **업그레이드를 막는 테스트는 이 오라클의 목적과 정반대다.**
"""

import collections
import sys

import httpx
import pytest

from app import config
from tests.conftest import ADMIN_ID, ADMIN_PW, TEST_ENV

# ASGITransport 로 덮이는 취약 패키지. `osv-scanner.toml` 등재 건수를 함께 적는다.
# h11 은 여기 없다 — ASGI 를 직접 부르면 HTTP 바이트 파싱이 없어 0 프레임이다.
# 그쪽은 `test_http_socket.py` 가 실소켓으로 덮는다.
# 값은 **모듈 디렉터리 이름**이다(배포 이름이 아니다). `python-multipart` 는 0.0.12
# 에서 모듈을 `multipart` → `python_multipart` 로 개명했으므로 둘 다 받는다 — 한쪽만
# 적으면 업그레이드하는 순간 "안 덮인다"로 false red 가 나고, 그건 이 오라클의 목적
# (업그레이드를 가능하게)과 정반대다 (설계 A-10).
COVERED_PACKAGES = ["jinja2", "starlette", "jwt", ("multipart", "python_multipart")]


def test_config_uses_the_mock_values_not_the_developer_env():
    """AC-1: 개발자 `.env` 가 무엇이든 테스트는 목 값을 본다.

    `load_dotenv(override=False)` 라 conftest 가 먼저 세운 값이 이긴다. 이게 깨지면
    JWT 테스트가 머신마다 다른 salt 를 쓰게 되어 실패가 재현되지 않는다.
    """
    assert config.SECRET_SALT == TEST_ENV["SECRET_SALT"]
    assert config.DB_URL == TEST_ENV["DB_URL"]
    assert config.ACCESS_TOKEN_EXPIRE_HOURS == int(TEST_ENV["ACCESS_TOKEN_EXPIRE_HOURS"])
    assert "sqlite" in config.DB_URL, "테스트가 실 DB 로 붙을 수 있는 설정이다"


def _count_frames(packages):
    """각 항목은 모듈 이름 하나 또는 **동의어 튜플**이다 (개명 대응). 계수 키는 첫 이름."""
    counts = collections.Counter()
    watched = [(p[0], tuple(p)) if isinstance(p, tuple) else (p, (p,)) for p in packages]

    def tracer(frame, event, arg):
        if event != "call":
            return
        filename = frame.f_code.co_filename
        for key, aliases in watched:
            if any(
                f"/site-packages/{a}/" in filename or filename.endswith(f"/site-packages/{a}.py")
                for a in aliases
            ):
                counts[key] += 1
                break

    return counts, tracer


async def test_the_oracle_actually_executes_the_vulnerable_packages(seeded_app, valid_token):
    """AC-5: 덮는다고 적은 패키지가 실제로 실행되는가.

    이 단언이 없으면 "오라클이 있다"는 말이 검증되지 않은 산문으로 남고, 그 상태로
    의존성을 올리면 초록이 아무것도 증명하지 않는다.
    """
    counts, tracer = _count_frames(COVERED_PACKAGES)
    transport = httpx.ASGITransport(app=seeded_app)

    sys.setprofile(tracer)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", follow_redirects=False
        ) as anon:
            # 상태를 단언한다: 요청이 에러 경로로 빠져도 프레임은 세어지므로,
            # 안 보면 "정상 경로가 그 패키지를 탄다"가 아니라 "에러 페이지가 탄다"가 된다.
            login_page = await anon.get("/login")  # jinja2
            assert login_page.status_code == 200
            issued = await anon.post(  # multipart + jwt 발급
                "/login/request", data={"username": ADMIN_ID, "password": ADMIN_PW}
            )
            assert issued.status_code == 200
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
            cookies={"token": valid_token},
        ) as admin:
            rendered = await admin.get("/admin/attendee/202601")  # jinja2 + jwt 검증
            assert rendered.status_code == 200
    finally:
        sys.setprofile(None)

    missing = [
        (p[0] if isinstance(p, tuple) else p)
        for p in COVERED_PACKAGES
        if counts[p[0] if isinstance(p, tuple) else p] == 0
    ]
    assert not missing, (
        f"덮는다고 선언한 패키지가 실행되지 않았다: {missing}. "
        f"실측: {dict(counts)}. 선언과 실행이 갈라지면 이 오라클은 가짜다."
    )


@pytest.mark.parametrize("package", ["h11", "cryptography", "pymysql"])
async def test_known_uncovered_packages_stay_uncovered(seeded_app, package):
    """음성 대조 — **못 덮는 것을 못 덮는다고 고정한다.**

    이게 없으면 위 테스트는 "덮는 목록을 늘리기만 하면 초록"이 되어, 무엇이 검증
    범위 밖인지가 조용히 사라진다. 여기가 red 가 되면 그건 결함이 아니라
    **커버리지가 늘었다는 신호**이고, 그때 이 목록과 `osv-scanner.toml` 을 함께 고친다.

    - h11: ASGITransport 는 HTTP 바이트를 파싱하지 않는다 (실소켓 테스트가 따로 덮는다)
    - cryptography: 이 앱에 경로가 없다 — HS256 은 stdlib `hmac`, 비번은 `bcrypt` 패키지
    - pymysql: 테스트는 SQLite 를 쓴다
    """
    counts, tracer = _count_frames([package])
    transport = httpx.ASGITransport(app=seeded_app)

    sys.setprofile(tracer)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", follow_redirects=False
        ) as anon:
            assert (await anon.get("/login")).status_code == 200
            assert (await anon.get("/attendee/202601")).status_code == 200
    finally:
        sys.setprofile(None)

    assert counts[package] == 0, (
        f"{package} 가 이제 실행된다({counts[package]} 프레임). 결함이 아니라 커버리지가 "
        f"늘어난 것이다 — COVERED_PACKAGES 와 osv-scanner.toml 을 함께 갱신하라."
    )
