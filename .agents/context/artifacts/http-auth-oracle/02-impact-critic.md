## [2단계 §5] 영향 맵 독립 검증

검증자: fresh-context. 입력은 `02-feature-analysis.md` · `00-codebase-discovery.md` ·
`01-planning.md` · `codebase-conventions.md` 뿐 (대화 이력 없음).
모든 판정은 코드를 열고 **실행해서** 냈다. 프로브는 스크래치패드에서 돌렸고 레포에
파일을 남기지 않았다.

---

## 검증 관점 5종

### 1. 누락된 수정 파일

**지적 3건.**

**(가) `.agents/context/codebase-conventions.md` 가 수정 파일 목록에 없다.**
이 단계의 §5 가 "새로 발견한 간접 결합은 레지스트리에 append (자산화)" 를 **요구한다.**
아래 § 숨은 결합 레지스트리 추가 제안이 5건을 올리므로, 그 파일은 이번 작업이 반드시
건드리는 기존 파일이다. 영향 맵의 "수정할 파일" 표에는 `tests/conftest.py` 한 줄뿐이다.

**(나) 테스트 사용자 시드가 어느 기능에도 없다.**
`app/main.py` 의 lifespan 이 `_seed_admin_user()` 로 `KY_USER_L` 에 admin 을 심지만,
**두 겹으로 실행되지 않는다**:
1. lifespan 조건이 `config.DB_URL and "sqlite" in ... and "local" in ...` 이라
   `sqlite+aiosqlite://` (기존 `db_session` fixture 가 쓰는 URL) 은 통과 못 한다.
2. 통과하더라도 **`httpx.ASGITransport` 는 lifespan 을 돌리지 않는다.** 실측:
   `create_app()` 에 `on_event("startup")` 을 달고 요청 1회 → `startup ran: []`.

따라서 `create_tables()` 도 시드도 테스트가 직접 해야 한다. 기능 2 는 테이블 생성만
말하고 사용자 행은 말하지 않는다. 그런데 기능 7 의 `/login/request` **성공 경로가
FR-2 "토큰 발급" 의 유일한 실경로**다 — 시드가 없으면 그 경로는 영원히 307(로그인
실패 리다이렉트)만 관측한다. 실측으로 확인: 시드 후 `POST /login/request` →
`200 + set-cookie: token`, 시드 없으면 `307 → /login`.

**(다) 기능 1 의 고정 대상에 `ACCESS_TOKEN_EXPIRE_HOURS` 가 빠졌다.**
`app/.env` 는 실제로 그 키를 세운다(키 목록 실측: `ACCESS_TOKEN_EXPIRE_HOURS`,
`DB_URL`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `GROQ_TEST_API_KEY`, `SECRET_SALT`).
`app/config.py` 가 그 값을 읽고 `AuthHandler.encode_token` 의 `exp` 를 만든다.
conftest 가 안 고정하면 **개발자 `.env` 값이 토큰 수명을 결정한다** — FR-4·AC-1 이
금지하는 바로 그것이고, AC-4(만료 토큰 제조, D-4)의 기준선이 머신마다 달라진다.
`GROQ_TEST_API_KEY` 는 레포 전체에서 참조 0건(실측)이라 무해하지만, "conftest 가
`config` 가 읽는 키를 전부 덮는다" 로 규칙을 세우는 편이 안전하다.

**(라) 등록할 곳 — 지적 없음.** `pyproject.toml:41 testpaths = ["tests"]`,
`asyncio_mode = "auto"` 확인. `tests/` 는 `tests/__init__.py` 가 있는 패키지이고 신규
파일에 등록 절차가 없다는 판정은 맞다. `[tool.ruff] exclude` 는 `tests/harness` 만
빼므로 신규 테스트는 ruff 대상이 되지만 ruff 는 비차단이다(conventions).
**단, D-3 의 후보 하나는 여기서 죽는다**: `pyproject.toml` 의 pytest `env` 옵션은
`pytest-env` 플러그인이 필요한데 미설치다 → C-2(의존성 추가 금지) 위반. 남는 후보는
conftest 최상단뿐이다.

### 2. 숨은 커플링

`codebase-conventions.md` § 숨은 결합 = **비어 있음**(순회함). grep 으로 실제 확인한
결과 영향 맵 밖의 결합 5건을 새로 발굴했다 — 전문은 아래 § 레지스트리 추가 제안.
그중 **이번 계획을 직접 깨는 것 1건**:

**`get_session` 과 `DB().get_db_session` 은 서로 다른 오버라이드 키다.**
```
app/dao/{attendee,login,admin}.py:8   def __init__(self, db_session=Depends(DB().get_db_session))
app/agent/router.py:34,53             session: AsyncSession = Depends(get_session)
```
기능 2 는 "라우트가 실 DB 로 안 가게 한다" 라고만 적고 D-2 도 `DB().get_db_session`
하나만 논한다. **하나만 걸면 `/agent/chat`·`/agent/confirm` 두 라우트가 실 DB(설정에
따라 Oracle)로 샌다.** 1단계가 0단계의 "`get_session` 오버라이드로 격리" 를 반박하면서
반대 방향으로 과교정된 자리다 — 정답은 둘 중 하나가 아니라 **둘 다**다.

### 3. 성능 함정

**지적 없음 — 근거:** 기능 목록의 목록 조회는 `/attendee`·`/admin/attendee`·엑셀
export 셋이고, 셋 다 `app/dao/functions.py` 의 `get_attendees`/`get_notices` 를 탄다.
각각 **단일 `select` + Python 딕셔너리 그룹핑**이고 관계(`relationship`) 정의가
`app/dao/tables.py` 에 아예 없어 lazy load 가 발생할 수 없다 → N+1 불가.
범위 조건 `ATDC_DATE >=/<=` 는 `KY_ATDC_L` 복합 PK 의 **선두 컬럼**이라 인덱스 추가
논점도 없다. 페이지당 쿼리 2개로 고정.

### 4. 기존 테스트 영향

**지적 없음(회귀 0) — 근거는 실행이다.** conftest 가 세울 값과 같은 env 를 강제하고
전체 스위트를 돌렸다:
```
SECRET_SALT=probe-salt DB_URL=sqlite+aiosqlite:///:memory: GROQ_API_KEY= GEMINI_API_KEY= \
  poetry run pytest -q
→ 242 passed in 167.32s
```
`tests/harness/` 포함이다(`testpaths = ["tests"]`). C-3 성립. `.env` 는 여전히 로드되지만
`load_dotenv` 기본 `override=False` 라 먼저 세운 값이 이긴다 — A-2 가 맞다(실측:
`config.SECRET_SALT == 'probe-salt'`).
**의도된 동작 변경 0건 / 회귀 0건** — 4단계 갱신 대상 없음.

주의(회귀는 아님): 기존 스위트가 이미 167초다. bcrypt 해시는 1회 ~0.3초이므로 시드
해시는 세션 스코프에서 한 번만 만든다.

### 5. 정책 모순 (기획 vs 기존 정책)

**지적 3건 — 그중 2건은 사람 승격 대상.** 요구 의도(AC-5)와 레포에 이미 있는 정책
문서(`osv-scanner.toml` 머리말)를 실행으로 대조했다.

**(가) [사람 승격] AC-5 의 h11 은 이 접근으로 성립하지 않는다.**
`httpx.ASGITransport` 는 ASGI scope 를 직접 만들어 넣으므로 **HTTP 와이어 파서를
전혀 타지 않는다.** 실측(프로파일러로 `site-packages/h11/` 프레임 카운트):

| 요청 | h11 프레임 |
|---|---|
| ASGITransport `GET /attendee/202401` | **0** |
| ASGITransport `GET /admin/attendee/202401` | **0** |
| ASGITransport `POST /login/request` | **0** |
| ASGITransport `GET /admin/attendee/export/202401` | **0** |
| **실소켓** `GET /` (인프로세스 uvicorn) | **190** |

`osv-scanner.toml` 은 h11 을 "실사용 경로 위" 로 등재하고 해소 순서 ①이 오라클을
만드는 것이라고 적었다. **이 계획대로 하면 h11 은 오라클 없이 남는다** — 그리고 그
사실이 초록에 가려진다(정확히 그 파일이 경고한 "가짜 초록"의 재발).
**대안은 있고 C-2 를 안 깬다**: `uvicorn` 은 이미 의존성이고 `cfg.http_protocol_class`
가 `uvicorn.protocols.http.h11_impl.H11Protocol` 임을 실측했다(httptools·uvloop 미설치).
인프로세스 uvicorn 을 127.0.0.1:0 에 띄우고 **요청 1개만** 실소켓으로 보내면 h11 이
클라이언트·서버 양쪽에서 실행된다. 스위트 전체를 소켓으로 옮길 필요는 없다.

**(나) [사람 승격] AC-5 의 cryptography 는 이 앱에 실행 경로가 아예 없다.**
전 요청에서 `site-packages/cryptography/` 프레임 **0**. 원인은 배선이 아니라 사실이다:
- PyJWT `HS256` 은 `jwt.algorithms.HMACAlgorithm` 이고 **stdlib `hmac`** 을 쓴다
  (실측: `has_crypto=True` 이지만 `HMACAlgorithm` 소스에 `cryptography` 문자열 없음).
  `cryptography` 는 RSA/EC 알고리즘에서만 필요하다.
- 비밀번호는 passlib→**`bcrypt` 패키지**(실측 프레임 1)이지 cryptography 가 아니다.

즉 `osv-scanner.toml` 머리말의 **"cryptography(JWT/bcrypt 하부)" 는 사실이 아니다.**
등재 5건짜리 이 패키지는 어떤 HTTP 테스트로도 못 덮으며, pymysql 과 같은 칸
(구조적 미커버)에 들어가야 한다. **사람 판정 필요**: AC-5 에서 빼고 알려진 한계로
내릴 것인가, 아니면 `osv-scanner.toml` 머리말을 정정할 것인가(후자는 이번 범위 밖의
문서 수정이다).

**(다) AC-5 가 starlette 를 빠뜨렸다 — 공짜로 덮이는데 명세에 없다.**
등재 건수 실측(`osv-scanner.toml`): python-multipart 16 · **starlette 14** · pyjwt 11 ·
jinja2 8 · pyasn1 5 · cryptography 5 · idna 4 · python-dotenv 2 · pytest 2 · pymysql 2 ·
**h11 2** · aiomysql 2 · click 1. starlette 0.36.3 은 2위 등재인데 AC-5 의 5종에 없다.
이 오라클은 라우팅·폼 파싱·응답·템플릿으로 starlette 를 가장 두껍게 실행한다.
AC-5 를 **h11·cryptography 를 빼고 starlette 를 넣는 방향**으로 고치면 명세가 실측과
일치한다.

**(라) 이진 인가 모델(FR-6/AC-7) — 모순 없음.** 코드로 확인: `KY_USER_L` 에 역할 컬럼
없음(`USER_ID`/`USER_PW` 뿐), `/attendee` 계열에 `Depends(get_current_user)` 없음,
`/admin/*`·`/agent/*` 전부 있음. 1단계의 판정과 코드가 일치한다.

**(마) AC-2 의 "/login 리다이렉트" — 모순 없음, 단 D-1 을 한쪽으로 고정한다.** 아래 실행 판정.

---

## 실행 판정

### D-1 — 앱 인스턴스: 모듈 `app` 이어야 한다 (create_app() 은 AC-2 를 깬다)

무토큰 요청, `follow_redirects=False`:

| 인스턴스 | 요청 | 상태 | `Location` |
|---|---|---|---|
| **모듈 `app`** | `GET /admin/attendee` | **307** | **`/login`** |
| 모듈 `app` | `GET /admin/attendee/202401` | 307 | `/login` |
| 모듈 `app` | `POST /agent/chat` | 307 | `/login` |
| `create_app()` | `GET /admin/attendee` | **401** | `None` |
| `create_app()` | `GET /admin/attendee/202401` | 401 | `None` |
| `create_app()` | `POST /agent/chat` | 401 | `None` |

원인은 등록된 예외 핸들러 차이다(실측한 `app.exception_handlers` 키):
- 모듈 `app`: `['401', RequestValidationError, WebSocketRequestValidationError, HTTPException]`
- `create_app()`: `[RequestValidationError, WebSocketRequestValidationError, HTTPException]`

`@app.get("/")` 와 `@app.exception_handler(401)` 이 `create_app()` **밖**, 모듈 수준
`app = create_app()` **뒤**에 있기 때문이다. 부수 효과로 `create_app()` 인스턴스는
`GET /` 가 **404** 다(실측). 모듈 `app` 은 `200 {"200":"ok"}`.

**판정: 모듈 `app` 을 쓴다.** 0단계 재활용 표의 "`create_app` 으로 테스트마다 깨끗한
인스턴스" 항목은 **폐기**한다 — 그걸 쓰면 AC-2 가 검증 불가능해지고 헬스체크 라우트가
사라진다. 대가는 프로세스 전역 인스턴스 공유이고, 그건 A-7(teardown 에서
`dependency_overrides.clear()`)이 이미 처방한 바다.

무토큰/불량 토큰 관측값 전체(모듈 `app`, 실측):

| 요청 | 상태 | Location |
|---|---|---|
| `GET /` | 200 | — |
| `GET /login` | 200 (HTML) | — |
| `GET /logout` | 307 | `/attendee` |
| `GET /attendee`, `GET /attendee/202401` | 200 (HTML) | — |
| `POST /login/request` (form, 정상 자격) | 200 + `set-cookie: token` | — |
| `POST /login/request` (form, 틀린 비번 / 없는 사용자) | 307 | `/login` |
| `POST /login/request` (**JSON 본문**) | 422 | — |
| 만료 토큰 / 위조 salt / 문자열 쓰레기 → `/admin/attendee/202401` | 307 | `/login` |
| 유효 토큰 → `GET /login` | 302 | `/admin/attendee` |

AC-4 의 세 거부 사유가 **전부 같은 307/`/login`** 으로 관측된다(구별 불가) — 4단계가
"만료와 위조를 다르게 관측한다" 로 케이스를 쓰면 그 테스트는 앱 동작이 아니라 기대를
검증하게 된다. 구별하려면 `AuthHandler.decode_token` 을 직접 부르는 유닛 레벨 단언을
따로 둬야 한다.

### D-2 — `dependency_overrides[DB().get_db_session]` 는 **먹힌다**

키 안정성(실측):
```
DB() is DB()                 True     ← SingletonMeta._instances
a = DB().get_db_session; b = DB().get_db_session
a is b                       False    ← 바인딩 메서드는 접근마다 새 객체
a == b                       True     ← __func__ 와 __self__ 가 같으면 동등
hash(a) == hash(b)           True
{a: 1}[b]                    1        ← dict 조회 성공 (FastAPI 가 하는 일이 이것)
```
FastAPI 는 `dependency_overrides.get(dependant.call, ...)` 로 **해시+동등** 조회를
하므로 동일 객체일 필요가 없다. 싱글턴이 `__self__` 를 고정해 주는 것으로 충분하다.

엔드투엔드 실측 (오버라이드가 테스트 엔진 세션을 주입, 유효 토큰):

| 요청 | 결과 |
|---|---|
| `GET /attendee/202401` | 200, HTML 렌더 |
| `GET /admin/attendee/202401` | 200, HTML 렌더 |
| `GET /admin/attendee/export/202401` | 200, `application/vnd.openxmlformats-...sheet` |
| `POST /admin/attendee` (`{attendee,notice,date}`) | 200 `OK`, 재조회에 반영됨 |
| `POST /agent/confirm` | 200 `{"status":"done",...}` |
| `POST /agent/chat` | 200 `{"status":"error","message":"GROQ_API_KEY 또는 ..."}` (외부 호출 0) |

**대조군**: 오버라이드를 걸지 않고 싱글턴이 빈 `:memory:` 를 물면
`sqlite3.OperationalError: no such table: KY_ATDC_L` — 즉 위 200 들은 오버라이드가
실제로 먹혀서 나온 값이다.

**대안(`DB_URL` 을 sqlite 로 두고 싱글턴을 실제로 물리기)도 성립한다**: `DB().init_db()`
후 `await DB().create_tables()` 하면 오버라이드 없이 `GET /attendee/202401` 200,
export 200. in-memory sqlite 엔진의 풀은 **`StaticPool`**(실측 — `sqlite+aiosqlite://`
와 `.../:memory:` 둘 다)이라 커넥션이 하나로 공유되고, "테이블 만든 커넥션과 요청
커넥션이 다르다" 는 함정은 없다.

**추천: 오버라이드 쪽.** 이유 둘 — (1) `/agent/*` 가 쓰는 `get_session` 도 어차피 같은
방식으로 갈아끼워야 하므로 두 경로가 한 메커니즘으로 통일된다, (2) 싱글턴은
프로세스 전역이라 기존 242개와 상태를 공유하고 teardown 이 어렵다. 단
**`get_session` 과 `DB().get_db_session` 을 둘 다 등록**해야 한다(위 § 숨은 커플링).

### 부수 실측 — AC-5 의 실제 커버리지

요청별 `site-packages/<pkg>/` 프레임 카운트(`sys.setprofile`):

| 요청 | jinja2 | jwt | multipart | bcrypt | h11 | cryptography |
|---|---|---|---|---|---|---|
| `GET /attendee/202401` | 9220 | 0 | 0 | 0 | **0** | **0** |
| `GET /admin/attendee/202401` | 9367 | 32 | 0 | 0 | **0** | **0** |
| `POST /login/request` (urlencoded) | 0 | 19 | **15** | 1 | **0** | **0** |
| `POST /login/request` (**multipart**) | 0 | 19 | **199** | 1 | **0** | **0** |
| `GET /admin/attendee/export/202401` | 0 | 32 | 0 | 0 | **0** | **0** |
| 실소켓 `GET /` (uvicorn) | 0 | 0 | 0 | 0 | **190** | **0** |

읽는 법: **jinja2·pyjwt·python-multipart 는 계획대로 덮인다.** urlencoded 폼도
python-multipart 를 타지만(starlette `FormParser` → `QuerystringParser`) `files=` 로
multipart 를 보내면 실행량이 13배가 된다 — 4단계는 **multipart 인코딩으로 보내는
케이스를 최소 1개** 둬야 등재 16건짜리 1위 패키지를 제대로 깨운다.

---

## 숨은 결합 레지스트리 추가 제안

`codebase-conventions.md` § 숨은 결합 에 append 할 5줄 (형식: `무엇 ↔ 무엇` · 왜 안 보이나 · 발견 경위).

| 결합 | 왜 안 보이나 | 발견 경위 |
|---|---|---|
| `app/main.py` 모듈 `app` ↔ `GET /` · 401→`/login` 핸들러 | 둘 다 `create_app()` **밖**·아래에 데코레이터로 붙어 있어 팩토리를 부르면 조용히 사라진다. 인증 실패가 307 이 아니라 401 JSON 이 되고 `/` 는 404 | 2단계 §5 D-1 실측 (양쪽 인스턴스 요청 비교) |
| `app/dao/*.py` `Depends(DB().get_db_session)` ↔ `app/agent/router.py` `Depends(get_session)` | 같은 DB 인데 **의존성 키가 둘**이다. `app/util/db.py` 안에서만 보면 형제로 보여 하나만 갈아끼우기 쉽고, 그러면 `/agent/*` 만 실 DB 로 샌다 | 2단계 §5 grep + D-2 실측 |
| `httpx.ASGITransport` ↔ `app/main.py` lifespan (`create_tables` + `_seed_admin_user`) | ASGITransport 는 lifespan 이벤트를 **안 돌린다**. 게다가 그 lifespan 은 `"local" in DB_URL` 조건부라 이중으로 안 뜬다. 앱을 실기동하면 되던 시드가 테스트에서만 사라진다 | 2단계 §5 실측 (`on_event("startup")` 프로브 → `[]`) |
| `app/config.py` ↔ **cwd** (`os.getcwd()/app/.env`) + `load_dotenv(override=False)` | 환경변수처럼 보이지만 실제 변수는 **작업 디렉터리**다. 다른 cwd 에서 재면 값이 달라진다(1단계가 이 함정에 이미 한 번 빠졌다). `override=False` 라 먼저 세운 값이 이긴다 | 1단계 정정 + 2단계 §5 재확인 (`config.SECRET_SALT` 단언) |
| `app/agent/llm.py::_llm_instance` ↔ 프로세스 수명 | 모듈 전역 캐시라 **최초 `get_llm()` 결과가 프로세스 끝까지 산다.** 키를 나중에 바꿔도 반영 안 되고, 한 번 실어댑터가 잡히면 이후 테스트가 외부 호출을 낸다 (키가 비면 예외라 캐시되지 않아 지금은 안전) | 2단계 §5 코드 확인 (`app/agent/llm.py:219-244`) |

부수 관측(결합 아님, 후속 과제 후보): `GET /admin/attendee/export`(무날짜)는 "도달
불가"라기보다 **`admin_attendee_get_year_month` 로 매칭되어 `ValueError: time data
'export01' does not match format '%Y%m%d'` 를 던진다.** `httpx.ASGITransport` 는 기본
`raise_app_exceptions=True` 라 이걸 500 응답이 아니라 **테스트 프로세스의 예외**로
올린다 — 실수로 이 경로를 때리면 테스트가 assert 실패가 아니라 에러로 죽는다.
1단계가 범위 밖으로 뺀 판단은 유효하다.

---

## 지적 요약

반영해야 할 것 **8개**.

1. **AC-5 의 h11 은 거짓이다** — ASGITransport 요청에서 h11 프레임 0. 실소켓
   인프로세스 uvicorn 요청 1개면 190 프레임(C-2 안 깨짐). 케이스를 넣든 AC-5 에서
   빼든 **사람 판정**이 필요하다 (`osv-scanner.toml` 이 h11 을 실사용 경로로 등재).
2. **AC-5 의 cryptography 는 이 앱에 실행 경로가 없다** — PyJWT HS256=stdlib `hmac`,
   비번=`bcrypt` 패키지. pymysql 과 같은 "구조적 미커버" 칸으로 내리고,
   `osv-scanner.toml` 머리말의 "cryptography(JWT/bcrypt 하부)" 서술과의 모순을
   **사람에게 승격**한다.
3. **AC-5 에 starlette 를 추가한다** — 등재 14건(2위)인데 명세에 없고, 이 오라클이
   이미 가장 두껍게 덮는다.
4. **기능 2 에 `get_session` 오버라이드를 명시한다** — `DB().get_db_session` 만 걸면
   `/agent/chat`·`/agent/confirm` 이 실 DB 로 샌다. 키는 둘이다.
5. **기능 목록에 "테스트 사용자 시드"를 추가한다** — lifespan 이 ASGITransport 에서
   안 도는 것을 실측했다. 시드 없이는 `/login/request` 성공 경로(FR-2 의 유일한 실토큰
   발급 경로)가 관측 불가. bcrypt 해시는 세션 스코프 1회.
6. **기능 1 의 고정 대상에 `ACCESS_TOKEN_EXPIRE_HOURS` 를 추가한다** — `app/.env` 가
   실제로 세우는 키다. 안 고정하면 FR-4·AC-1 위반이고 AC-4 기준선이 흔들린다.
7. **수정할 파일에 `.agents/context/codebase-conventions.md` 를 추가한다** — 위
   레지스트리 5줄 append 는 §5 가 요구하는 산출물이다.
8. **D-1·D-2 를 결정으로 확정한다** — D-1: 모듈 `app`(0단계의 `create_app()` 재활용
   판정 폐기). D-2: 오버라이드 방식(먹힌다, 실측). D-3 의 `pyproject.toml` pytest `env`
   후보는 `pytest-env` 미설치로 C-2 위반이라 탈락 → conftest 최상단만 남는다.
   덧: AC-4 의 만료/위조/쓰레기 토큰은 HTTP 층에서 **전부 307 `/login`** 으로 같게
   관측된다(실측) — 구별이 필요하면 `decode_token` 직접 단언을 따로 둔다.

지적 없음으로 닫은 관점: **성능 함정**(단일 select 2회, relationship 정의 자체가 없어
N+1 불가, 범위 조건이 PK 선두 컬럼), **기존 테스트 영향**(강제 env 로 전체 실행 →
242 passed, `tests/harness` 포함. 의도된 동작 변경 0 / 회귀 0).
