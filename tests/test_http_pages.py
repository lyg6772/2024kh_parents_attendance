"""SSR 렌더·폼 파싱·엑셀 스트리밍 — jinja2 / python-multipart / openpyxl 경로.

`03-design.md` § 통합 계획 의 기능 7·8. 깊은 기능 테스트가 아니라 **오라클**이다:
의존성을 올린 뒤에도 이 경로들이 여전히 도는지를 본다.
"""

import pytest

from tests.conftest import ADMIN_ID


async def test_login_page_renders_html(client):
    """jinja2 가 실제로 템플릿을 렌더한다."""
    res = await client.get("/login")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    # 템플릿이 실제로 확장됐는지 — 빈 200 이나 에러 페이지면 아래가 없다.
    assert "<form" in res.text.lower()


@pytest.mark.parametrize("path", ["/attendee", "/attendee/202601"])
async def test_attendee_pages_render_html(client, path):
    res = await client.get(path)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    assert "<html" in res.text.lower()


async def test_admin_page_renders_for_authenticated_user(admin_client):
    res = await admin_client.get("/admin/attendee/202601")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    assert "<html" in res.text.lower()


async def test_form_post_rejects_missing_fields(client):
    """폼 파싱의 음성 대조 — 필드가 빠지면 422.

    양성 경로(정상 폼 → 200)는 `test_http_auth.py::test_login_issues_a_working_token`
    이 이미 본다. 여기서 되풀이하면 같은 요청을 두 곳이 소유하게 된다.
    """
    res = await client.post("/login/request", data={"username": ADMIN_ID})
    assert res.status_code == 422


async def test_excel_export_streams_a_workbook(admin_client):
    """openpyxl + StreamingResponse 경로 (AC-9).

    실사용 경로는 **날짜가 있는 쪽**이다 — 프론트의 유일한 export 링크가
    `/admin/attendee/export/{cal_date}` 다 (`app/template/admin_attendee.html`).
    """
    res = await admin_client.get("/admin/attendee/export/202601")
    assert res.status_code == 200
    assert (
        res.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment" in res.headers["content-disposition"]
    # xlsx 는 zip 컨테이너다. 매직 바이트로 "진짜 워크북인가"를 본다 —
    # 상태 코드만 보면 빈 바디도 통과한다.
    assert res.content[:2] == b"PK", "xlsx zip 시그니처가 아니다"
    assert len(res.content) > 0
