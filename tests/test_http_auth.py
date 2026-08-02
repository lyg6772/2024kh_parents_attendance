"""인증 경계와 토큰 검증 — 이 레포에서 커버리지가 0이던 영역.

고정하는 현행 규칙은 `03-design.md` § 비즈니스 규칙 R-1~R-5 가 소유한다.
요점: **401 이 아니라 307 `/login`** 이다 (`app/main.py` 의 401 예외 핸들러).
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app import config
from app.util.auth import AuthHandler
from tests.conftest import ADMIN_ID, ADMIN_PW

# 실측으로 뽑은 인증 필수 라우트 (2단계 라우트 표). 손으로 세지 않았다.
# `/admin/attendee/export`(무날짜)는 위 `{cal_date}` 가 선점해 이 등록에 도달하지
# 않으므로 제외한다 — 레포에 호출자도 없다 (유일한 링크는 날짜 있는 경로).
AUTH_GET_ROUTES = [
    "/admin/attendee",
    "/admin/attendee/202601",
    "/admin/attendee/export/202601",
]
AUTH_POST_ROUTES = ["/admin/attendee", "/agent/chat", "/agent/confirm"]

# 인증을 걸지 않는 조회 경로. 인가 모델이 **이진**이라는 것의 반대편이다.
PUBLIC_GET_ROUTES = ["/", "/login", "/attendee", "/attendee/202601"]


@pytest.mark.parametrize("path", AUTH_GET_ROUTES)
async def test_no_token_is_redirected_to_login(client, path):
    """R-1: 토큰 없이 인증 라우트 → 307 `/login`. 401 이 아니다."""
    res = await client.get(path)
    assert res.status_code == 307, f"{path}: {res.status_code}"
    assert res.headers["location"] == "/login"


@pytest.mark.parametrize("path", AUTH_POST_ROUTES)
async def test_no_token_post_is_redirected_to_login(client, path):
    res = await client.post(path, json={})
    assert res.status_code == 307, f"{path}: {res.status_code}"
    assert res.headers["location"] == "/login"


@pytest.mark.parametrize("path", AUTH_GET_ROUTES)
async def test_valid_token_reaches_the_route(admin_client, path):
    """R-2: 유효 토큰 → 정상 응답. 리다이렉트로 튕기지 않는다."""
    res = await admin_client.get(path)
    assert res.status_code == 200, f"{path}: {res.status_code} {res.text[:200]}"


@pytest.mark.parametrize("path", PUBLIC_GET_ROUTES)
async def test_public_routes_work_without_a_token(client, path):
    """R-4: 무토큰으로도 조회는 된다.

    이쪽을 안 보면 "토큰 없으면 다 막힌다"는 오독이 테스트로 굳는다 — 이 앱의
    인가 모델은 이진이다(토큰=관리자 / 무토큰=조회 전용).
    """
    res = await client.get(path)
    assert res.status_code == 200, f"{path}: {res.status_code}"


def _expired_token() -> str:
    """앱 API 로는 만료 토큰을 못 만든다 — 직접 서명한다. salt·알고리즘은 앱과 같다."""
    past = datetime.now(tz=UTC) - timedelta(hours=1)
    return jwt.encode(
        {"exp": past, "iat": past - timedelta(hours=1), "sub": ADMIN_ID},
        config.SECRET_SALT,
        algorithm="HS256",
    )


def _forged_token() -> str:
    """서명 salt 만 다르다 — 페이로드는 정상이다."""
    now = datetime.now(tz=UTC)
    return jwt.encode(
        {"exp": now + timedelta(hours=1), "iat": now, "sub": ADMIN_ID},
        config.SECRET_SALT + "-wrong",
        algorithm="HS256",
    )


@pytest.mark.parametrize(
    "token",
    [_expired_token(), _forged_token(), "not-a-jwt", ""],
    ids=["expired", "forged", "garbage", "empty"],
)
async def test_bad_tokens_do_not_reach_the_route(client, token):
    """R-3: 만료·위조·쓰레기·빈 토큰 — HTTP 층에서는 **전부 같게** 관측된다."""
    client.cookies.set("token", token)
    res = await client.get("/admin/attendee")
    assert res.status_code == 307
    assert res.headers["location"] == "/login"


def test_expired_and_forged_are_distinguishable_below_http():
    """HTTP 층이 셋을 뭉개므로, 구별은 `decode_token` 을 직접 불러서 본다.

    이게 없으면 "토큰 검증이 실제로 서명·만료를 보는가"가 검증되지 않는다 —
    `decode_token` 이 무조건 예외를 던져도 위 테스트는 통과한다.
    """
    from fastapi import HTTPException

    handler = AuthHandler()

    with pytest.raises(HTTPException) as expired:
        handler.decode_token(_expired_token())
    assert expired.value.status_code == 401
    assert "expired" in expired.value.detail.lower()

    with pytest.raises(HTTPException) as forged:
        handler.decode_token(_forged_token())
    assert forged.value.status_code == 401
    assert "invalid" in forged.value.detail.lower()

    # 양성 대조: 유효 토큰은 통과하고 sub 를 돌려준다. 이게 없으면 위 두 개는
    # "항상 던진다"로도 초록이다.
    assert handler.decode_token(AuthHandler().encode_token(ADMIN_ID)) == ADMIN_ID


async def test_login_issues_a_working_token(client):
    """R-5 의 발급 쪽: 로그인 성공이 실제로 쓸 수 있는 토큰을 준다.

    폼 POST(python-multipart) + bcrypt 검증(passlib) + JWT 발급(pyjwt)이 한 번에 돈다.
    """
    res = await client.post("/login/request", data={"username": ADMIN_ID, "password": ADMIN_PW})
    assert res.status_code == 200, res.text[:200]
    token = res.json()["token"]
    assert res.cookies.get("token") == token

    client.cookies.set("token", token)
    protected = await client.get("/admin/attendee")
    assert protected.status_code == 200


async def test_wrong_password_is_rejected(client):
    """음성 대조 — 비밀번호 검증이 실제로 도는가. 없으면 위 테스트는
    "아무 비번이나 통과"인 구현에서도 초록이다."""
    res = await client.post("/login/request", data={"username": ADMIN_ID, "password": "wrong"})
    assert res.status_code == 307
    assert res.headers["location"] == "/login"


async def test_login_rejects_a_username_that_does_not_exist(client):
    """음성 대조 — 조회 쿼리가 **사용자명으로 실제로 거르는가**.

    뮤테이션 검증에서 뚫린 자리다 (2026-08-02): `app/dao/functions.py::get_password`
    의 `.where(KyUserL.user_id == user_id)` 를 지워도 27개 테스트가 전부 초록이었다.
    시드가 1명뿐이라, 쿼리가 사용자명을 무시해도 admin 의 해시가 돌아와 우연히 맞는다.

    그래서 **없는 사용자명 + 올바른 비밀번호**로 두드린다. WHERE 가 빠지면 이것이
    200 을 받는다 — 인증 우회다.
    """
    res = await client.post(
        "/login/request", data={"username": "no-such-user", "password": ADMIN_PW}
    )
    assert res.status_code == 307, "없는 사용자명으로 로그인이 성공했다 — 인증 우회"
    assert res.headers["location"] == "/login"


async def test_write_route_accepts_a_valid_token(admin_client):
    """R-2 의 쓰기 쪽. 이 앱의 **유일한 쓰기 라우트**다 — 읽기만 검증하면
    인가 경계가 가장 중요한 곳에서 안 보인다."""
    res = await admin_client.post(
        "/admin/attendee",
        json={"attendee": "kim,lee", "notice": "테스트", "date": "20260115"},
    )
    assert res.status_code == 200, f"{res.status_code} {res.text[:200]}"


async def test_logout_clears_the_token_cookie(admin_client):
    """로그아웃이 쿠키를 실제로 지우는가. 지우지 않으면 '로그아웃'이 이름뿐이다."""
    res = await admin_client.get("/logout")
    assert res.status_code == 307
    assert res.headers["location"] == "/attendee"
    # Set-Cookie 로 token 을 만료시켜야 한다 — 헤더가 아예 없으면 안 지운 것이다.
    set_cookie = res.headers.get("set-cookie", "")
    assert "token=" in set_cookie, f"쿠키 삭제 헤더가 없다: {set_cookie!r}"
