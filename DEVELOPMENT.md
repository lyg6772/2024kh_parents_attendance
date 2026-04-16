# DEVELOPMENT.md

AI와 vibe coding할 때 따르는 개발 원칙과 협업 규칙.

---

## 1. AI 협업 규칙

### 변경 범위 원칙
- AI는 **요청한 것만** 수정한다. 기회가 있어도 관련 없는 코드 리팩토링 금지.
- 파일 하나를 고치면서 "개선"이라는 명목으로 다른 파일을 같이 바꾸지 않는다.
- 기존 코드 패턴이 이상해 보여도 먼저 물어본다. 임의로 바꾸지 않는다.

### 작업 순서 (TDD)
1. **요구사항 분석** — 구현 전에 어떤 동작이 필요한지 명확히 정리
2. **테스트 코드 작성** — 실패하는 테스트를 먼저 만든다
3. **구현** — 테스트가 통과할 만큼만 코드 작성
4. **테스트 통과 확인** — 기존 테스트 포함 전체 통과 필수
5. **커밋**

> AI가 테스트 없이 구현부터 만들거나, 테스트를 삭제해서 통과시키는 것은 절대 금지.

### 코드 리뷰 체크리스트 (AI에게 요청할 때 포함)
- [ ] 레이어 경계를 지켰는가?
- [ ] Oracle 컬럼명 대소문자 이중 `.get()` 패턴 적용했는가?
- [ ] 기존 테스트가 모두 통과하는가?
- [ ] 변경 범위가 요청 범위 안인가?

---

## 2. 아키텍처 결정 원칙

### 레이어 경계 (절대 규칙)

```
controller  →  service  →  DAO  →  DB
```

| 레이어 | 허용 | 금지 |
|---|---|---|
| `controller/` | HTTP 요청/응답, 인증 체크, Depends 주입 | 비즈니스 로직, DB 직접 접근 |
| `service/` | 비즈니스 로직, 템플릿 렌더링, DAO 조합 | 직접 DB 세션 사용 |
| `dao/` | SQLAlchemy `text()` 쿼리 실행 | 비즈니스 로직, HTTP 응답 |

- controller에서 DAO를 직접 호출하지 않는다.
- service에서 `session.execute()`를 직접 쓰지 않는다.
- 새 기능 = 새 controller 함수 + service 메서드 + (필요 시) DAO 메서드. 기존 레이어에 억지로 끼워 넣지 않는다.

### 새 라우트 추가 시
1. `controller/` 에 핸들러 함수 작성
2. `service/` 에 비즈니스 로직 작성
3. `dao/` 에 쿼리 작성 (필요 시)
4. `controller/router.py` 에 `router.add_api_route(...)` 추가

### Oracle 필수 패턴

**컬럼명 대소문자 — 항상 이중 get**
```python
# Oracle은 컬럼명을 대문자로 반환하지만 환경마다 다를 수 있음
val = row.get('column_name') or row.get('COLUMN_NAME')
```

**집계**
```sql
LISTAGG(col, ',') WITHIN GROUP (ORDER BY col)
```

**행 제한** (LIMIT 대신)
```sql
FETCH FIRST 1 ROWS ONLY
```

**바인딩 변수** (`%s` 아님)
```sql
WHERE col = :param_name
```

**upsert 없음 — delete → insert**
```python
await session.execute(delete_query, data)
await session.execute(insert_query, data)
await session.commit()
```

### 날짜 형식
- URL 파라미터: `YYYYMM` (예: `202604`)
- DB 저장/조회: `YYYYMMDD` 문자열 (예: `20260401`)
- 변환은 service 레이어에서만 한다.

### Jinja2 템플릿 경로
- service에서 렌더링: `Jinja2Templates(directory="./app/template")` ← 이것만 사용
- controller 파일에 `Jinja2Templates` 인스턴스가 남아있지만 실제 렌더링에 사용하지 않음 (혼동 주의)

### 인증
- 관리자 기능은 항상 `Depends(get_current_user)` 붙인다.
- `get_current_user`는 `controller/admin.py`에 정의됨.
- 인증 실패 → 401 → `main.py` exception handler가 `/login`으로 redirect.

---

## 3. 테스트 전략

현재 테스트 없음. 신규 기능부터 아래 기준을 적용한다.

### 테스트 스택 (추가 예정)
```toml
# pyproject.toml에 추가
pytest = "*"
pytest-asyncio = "*"
httpx = "*"          # FastAPI 비동기 테스트용
```

### 테스트 위치
```
tests/
  test_attendee.py   # 공개 출석 조회
  test_admin.py      # 관리자 CRUD
  test_login.py      # 인증
```

### 비동기 엔드포인트 테스트 패턴
```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_attendee_get():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/attendee")
    assert response.status_code == 200
```

### DAO 단위 테스트
- Oracle 연결이 필요한 DAO 테스트는 별도 표시: `@pytest.mark.integration`
- 로컬에서 실행 시 `app/.env` 필요.

---

## 4. 커밋 전략

### 메시지 형식
```
<type>: <요약> (한국어 가능)

# type 목록
feat:     새 기능
fix:      버그 수정
refactor: 동작 변경 없는 코드 개선
test:     테스트 추가/수정
docs:     문서 변경
chore:    설정, 패키지 등 기타
```

예시:
```
feat: 월별 출석 현황 Excel export 기능 추가
fix: 첫 날이 일요일일 때 달력 렌더링 오류 수정
test: AdminAttendeeService post_attendee 단위 테스트 추가
```

### 커밋 단위
- 기능 단위로 커밋. 반쪽짜리 기능은 커밋하지 않는다.
- TDD 흐름: `test: ...` 커밋 → `feat/fix: ...` 커밋
- 리팩토링은 기능 변경과 **같은 커밋에 섞지 않는다**.

---

## 5. LLM 에이전트 통합 설계 방향

### 목표
사용자가 자연어로 지시 → LLM이 의도 파악 → 기존 API 자동 호출.  
현재 SSR 화면은 그대로 두고, LLM 에이전트 인터페이스를 **레이어로 추가**하는 방식.

### 설계 방향

**1단계: JSON API 엔드포인트 정비**

현재 POST `/admin/attendee`는 이미 JSON API. 나머지 GET 엔드포인트들은 HTML을 반환함.  
LLM tool-calling용 JSON API를 별도 prefix로 추가:

```
GET  /api/attendee/{YYYYMM}     → JSON 반환 (출석 현황 조회)
GET  /api/admin/attendee/{YYYYMM} → JSON 반환 (관리자 조회)
POST /api/admin/attendee        → 기존 동일 (이미 JSON)
```

**2단계: 인증 방식 전환 검토**

현재: httpOnly 쿠키 JWT → 브라우저에서만 동작  
LLM agent: API Key 또는 Bearer 토큰 방식이 적합

```python
# 기존 쿠키 인증과 공존 가능한 패턴
async def get_current_user(request: Request):
    # API Key 헤더 우선, 없으면 쿠키 fallback
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return verify_api_key(api_key)
    token = request.cookies.get("token", '')
    return auth_handler.decode_token(token)
```

**3단계: LLM Tool 정의**

에이전트가 호출할 수 있는 tool 목록 (function calling 형식):

```python
tools = [
    {
        "name": "get_attendance",
        "description": "특정 월의 보람교사 출석 현황을 조회한다",
        "parameters": {
            "yyyymm": "조회할 월 (예: 202604)"
        }
    },
    {
        "name": "save_attendance",
        "description": "특정 날짜의 참석자 명단과 특이사항을 저장한다",
        "parameters": {
            "date": "날짜 YYYYMMDD",
            "attendee": "참석자 쉼표 구분 문자열",
            "notice": "특이사항 (선택)"
        }
    },
    {
        "name": "export_excel",
        "description": "특정 월의 출석 현황을 Excel로 다운로드한다",
        "parameters": {
            "yyyymm": "대상 월 (예: 202604)"
        }
    }
]
```

**LLM 날짜 파싱 주의사항**

LLM이 "이번 달", "4월" 등 자연어 날짜를 입력할 수 있음.  
`YYYYMM`/`YYYYMMDD` 변환 로직을 에이전트 레이어에서 처리 (service 레이어 오염 방지).

### 파일 구조 (통합 시 예상)
```
app/
  agent/
    tools.py       # LLM tool 정의 및 실행 라우팅
    router.py      # /agent 엔드포인트
  api/
    attendee.py    # JSON API 핸들러 (SSR과 별개)
```
