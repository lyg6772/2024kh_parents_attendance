## [2단계] 기능 목록 & 영향 맵

### 입력
- 1단계 산출물: `01-planning.md` (완결성 비평가 반영본) — 참조함
- 0단계 산출물: `00-codebase-discovery.md` — 참조함. 단, 그 문서의
  "`get_session` 오버라이드로 DB 격리" 판정은 1단계에서 **반박되어 폐기**됐다
- 누락 입력: 없음

### 라우트 표 (실측 — 손으로 세지 않았다)

`app.routes` 를 실행으로 덤프하고 각 엔드포인트 시그니처에서
`Depends(get_current_user)` 여부를 판정했다. **총 17, 그중 FastAPI 자동 문서 4개
(`/openapi.json` `/docs` `/docs/oauth2-redirect` `/redoc`) 를 빼면 앱 라우트 13개,
인증 7개.** 1단계 초안의 11/6 도, 비평가의 12/7 도 틀렸다.

| 인증 | 메서드 | 경로 | 엔드포인트 |
|---|---|---|---|
| — | GET | `/` | `health_check` |
| — | GET | `/login` | `login_template` |
| — | POST | `/login/request` | `login_post` |
| — | GET | `/logout` | `logout` |
| — | GET | `/attendee` | `attendee_get_default` |
| — | GET | `/attendee/{cal_date}` | `attendee_get_year_month` |
| **AUTH** | GET | `/admin/attendee` | `admin_attendee_get_default` |
| **AUTH** | POST | `/admin/attendee` | `admin_attendee_post` |
| **AUTH** | GET | `/admin/attendee/{cal_date}` | `admin_attendee_get_year_month` |
| **AUTH** | GET | `/admin/attendee/export` | 이 등록에 **도달하지 않는다** — 위 `{cal_date}` 가 선점해 `admin_attendee_get_year_month` 가 타고 `ValueError: 'export01'`. 레포에 호출자 없음(유일한 export 링크는 `admin_attendee.html:708` 의 날짜 있는 경로) |
| **AUTH** | GET | `/admin/attendee/export/{cal_date}` | `admin_attendee_export_excel` — 실사용 경로 |
| **AUTH** | POST | `/agent/chat` | `chat` |
| **AUTH** | POST | `/agent/confirm` | `confirm` |

### 기능 목록

| # | 기능 | 설명 | 의존 | 재활용 | 신규 |
|---|------|------|------|--------|------|
| 1 | 테스트 환경 고정 | 앱 import **전에** `SECRET_SALT`·`DB_URL`·`ACCESS_TOKEN_EXPIRE_HOURS`·LLM 키를 목 값으로 세운다 | 없음 (가장 먼저) | 없음 | `tests/conftest.py` 모듈 최상단 블록 |
| 2 | DB 격리 배선 | 라우트가 실 DB 로 안 가게 한다. **의존성 키가 둘이다** — `DB().get_db_session`(DAO 3파일)과 `get_session`(agent 라우터). **둘 다 오버라이드해야** `/agent/*` 가 실 DB 로 안 샌다 | 1 | `tests/conftest.py::db_session` 의 엔진 생성 패턴, `app.dao.tables.Base` | fixture |
| 2b | 테스트 사용자 시드 | `KY_USER_L` 에 bcrypt 해시된 admin 을 넣는다 | 2 | `app.main._seed_admin_user` 의 패턴 | fixture (세션 스코프 — bcrypt 는 비싸다) |
| 3 | ASGI 클라이언트 | 네트워크 없이 앱을 타는 `httpx.AsyncClient` | 1, 2 | `httpx 0.27.2` (설치됨) | fixture |
| 4 | 토큰 제조 | 유효·만료·위조 토큰 | 1 | `app.util.auth.AuthHandler.encode_token` | fixture/헬퍼 |
| 5 | 인증 경계 테스트 | 인증 7개 라우트: 무토큰 거부 / 유효토큰 통과. 무인증 라우트: 토큰 없이 정상 | 2,3,4 | 없음 | `tests/test_http_auth.py` |
| 6 | 토큰 검증 테스트 | 만료·위조 토큰이 각각 거부된다 | 3,4 | 없음 | `tests/test_http_auth.py` |
| 7 | SSR·폼 경로 테스트 | `/login` 렌더, `/login/request` 폼 POST, `/attendee` 렌더 | 2,3 | 없음 | `tests/test_http_pages.py` |
| 8 | 엑셀 스트림 테스트 | `/admin/attendee/export/{yyyymm}` 이 스트림을 반환 (AC-9) | 2,3,4 | 없음 | `tests/test_http_pages.py` |
| 9 | LLM 무력화 확인 | `/agent/chat` 이 외부 호출 없이 `status:"error"` (AC-8) | 1,3,4 | 없음 | `tests/test_http_agent.py` |
| 11 | h11 스모크 (실소켓) | 인프로세스 uvicorn 을 띄워 실제 HTTP 로 한 번 때린다 — ASGITransport 는 h11 을 **0 프레임** 실행한다(실측) | 1,2,2b | `uvicorn 0.29.0` (설치됨 → C-2 안 깸) | `tests/test_http_socket.py` |
| 10 | 환경 고정 확인 | `config` 가 목 값을 들고 있다 (AC-1) | 1 | 없음 | `tests/test_http_env.py` 또는 위 파일 중 하나 |

### 구현 순서

| 순서 | 기능 | 이유 |
|------|------|------|
| 1 | 기능 1 (환경 고정) | 이게 없으면 나머지가 import 조차 안 되거나 개발자 `.env` 를 탄다 |
| 2 | 기능 2 (DB 격리) | 실측된 실패(`no such table`)를 먼저 없애야 라우트가 200 을 낼 수 있다 |
| 3 | 기능 3·4 (클라이언트·토큰) | 모든 테스트의 공통 바닥 |
| 4 | 기능 5·6 (인증) | 요구의 중심. 커버리지 0인 영역 |
| 5 | 기능 7·8·9·10 | 나머지 패키지 커버 |

### 영향 맵

#### 생성할 파일
| 파일 경로 | 목적 |
|-----------|------|
| `tests/test_http_auth.py` | 기능 5·6 — 인증 경계와 토큰 검증 |
| `tests/test_http_pages.py` | 기능 7·8 — SSR·폼·엑셀 |
| `tests/test_http_agent.py` | 기능 9 — LLM 무력화 |
| `tests/test_http_socket.py` | 기능 11 — 실소켓 h11 스모크 |

#### 수정할 파일
| 파일 경로 | 변경 내용 |
|-----------|----------|
| `tests/conftest.py` | 모듈 최상단에 환경 고정(기능 1) + DB 격리·시드·ASGI 클라이언트·토큰 fixture(기능 2·2b·3·4). **기존 `db_session` 은 그대로 둔다** (C-3) |
| `.agents/context/codebase-conventions.md` | § 숨은 결합 에 §5 가 발굴한 5줄 append (자산화 — 다음 기능부터 재발굴 비용 제거) |
| `osv-scanner.toml` | 머리말의 "cryptography(JWT/bcrypt 하부)" 서술이 실측과 다르다(0 프레임). 사람 판정 2026-08-02: **이번에 같이 고친다** — 이 작업이 그 문서에서 파생됐고 실측 숫자를 지금 들고 있다. 오라클이 무엇을 덮고 못 덮는지를 그 파일에 적어 ② 단계가 그대로 쓰게 한다 |

#### 등록할 곳
| 위치 | 내용 |
|------|------|
| 없음 | pytest 가 `tests/` 를 자동 수집한다(`testpaths = ["tests"]`). 신규 테스트 파일에 등록 절차가 없다 |

**앱 코드(`app/`) 수정 0건** — C-1.

### 접근 결정 — 실행으로 확정됨 (§5 비평가 실측)

| # | 결정 | 근거 (실측) |
|---|---|---|
| D-1 | **모듈 `app` 을 쓴다.** `create_app()` 재활용 판정(0단계) 폐기 | 모듈 `app` → 무토큰 요청이 **307 `Location: /login`**. `create_app()` → **401 JSON + `GET /` 가 404**. `@app.get("/")` 와 `@app.exception_handler(401)` 이 팩토리 밖에 붙어 있다 |
| D-2 | **`dependency_overrides` 로 간다. 키는 둘.** | 바인딩 메서드는 `is` 로 다르지만 `==`·`hash` 가 같아 dict 조회가 성공한다(실측). 오버라이드 적용 시 전 라우트 200, 미적용 시 `no such table`. `get_session` 은 **별개 키**라 둘 다 걸어야 `/agent/*` 가 안 샌다 |
| D-3 | **conftest 모듈 최상단.** | `pyproject.toml` 의 pytest `env` 후보는 `pytest-env` 미설치 → C-2 위반이라 탈락 |
| D-4 | 만료·위조 토큰은 만들되, **HTTP 층에서는 구별되지 않는다** | 만료·위조·쓰레기 토큰이 전부 307 `/login` 으로 같게 관측된다(실측). 구별하려면 `decode_token` 을 직접 단언하는 케이스를 따로 둔다 |
| D-5 | **프레임 프로파일로 관측한다.** "산문으로만"은 배제 | 아래 § 커버리지 실측이 그 결과다 |

### 커버리지 실측 — 오라클이 무엇을 덮는가

`sys.setprofile` 로 요청 중 실행 프레임을 셌다 (4개 요청 전부 200 응답 확인).

| 패키지 | ASGITransport 프레임 | CVE 등재 | 판정 |
|---|---|---|---|
| jinja2 | 9,603 | 8 | 덮인다 |
| starlette | 1,143 | **14** | 덮인다 — **AC-5 에 없었다. 추가한다** |
| pyjwt | 19 | 11 | 덮인다 |
| python-multipart | 15 | 16 | 덮인다 |
| openpyxl | 18,561 | 0 | 덤 |
| bcrypt | 1 | 0 | 덤 |
| **h11** | **0** | 2 | ASGITransport 로는 **못 덮는다** → 기능 11(실소켓 스모크)로 덮는다 |
| **cryptography** | **0** | 5 | **이 앱에 실행 경로가 없다.** HS256=stdlib `hmac`, 비번=`bcrypt` 패키지. 구조적 미커버 |
| pymysql·aiomysql | 0 | 4 | SQLite 라 구조적 미커버 |

**덮는 합계: 49/74** (jinja2 8 + starlette 14 + pyjwt 11 + multipart 16), h11 2건은
기능 11 로 추가 → **51/74**. 나머지 23건은 구조적 미커버로 명시한다.

### 영향 맵 검증 (§5)

**지적 8개 전부 반영.** 산출물: `02-impact-critic.md`

1. AC-5 의 h11 이 거짓 → 사람 판정으로 **기능 11(실소켓 스모크 1개)** 추가
2. AC-5 의 cryptography 는 실행 경로 없음 → 구조적 미커버로 하강 + `osv-scanner.toml` 정정
3. AC-5 에 starlette(등재 14건, 2위) 추가
4. 기능 2 에 `get_session` 오버라이드 명시 (키가 둘)
5. 기능 2b(테스트 사용자 시드) 추가 — ASGITransport 는 lifespan 을 안 돌린다(실측)
6. 기능 1 에 `ACCESS_TOKEN_EXPIRE_HOURS` 고정 추가
7. 수정할 파일에 `codebase-conventions.md` 추가 (레지스트리 append)
8. D-1~D-5 를 결정으로 확정 (위 표)

**지적 없음으로 닫힌 관점**: 성능 함정(relationship 정의 자체가 없어 N+1 불가),
기존 테스트 영향(강제 env 로 242개 전원 통과 — 회귀 0), 정책 모순(없음).

**추가 관측(후속 과제 후보)**: `app/agent/llm.py:219-244` 의 `_llm_instance` 모듈 전역
캐시는 최초 `get_llm()` 결과가 프로세스 끝까지 산다. 지금은 키가 비면 예외라 캐시되지
않아 안전하지만, AC-8 이 기대는 성질이므로 4단계가 이 전제를 단언한다.

### 종료 조건
- [x] 모든 기능이 1단계 명세에서 추출되었다 (임의 추가 없음 — 각 기능이 FR/AC 에 대응)
- [x] 재활용 매핑 완료
- [x] 생성/수정/등록 파일 모두 포함
- [x] 독립 검증(§5) 완료 및 지적 8개 전부 반영
- [x] 정책 모순 점검 — 없음
