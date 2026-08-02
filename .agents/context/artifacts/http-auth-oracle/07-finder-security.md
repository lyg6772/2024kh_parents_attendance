## [7단계] security+규칙 finder 원출력

렌즈: security + 규칙 (`.agents/07-review.md` §1-1). 대상: `tests/conftest.py`(수정),
`tests/test_http_*.py` 5개(신규), `osv-scanner.toml`(머리말), `codebase-conventions.md`
(§숨은 결합). 앱 코드 변경 0건. coverage-first — 확신 없는 것도 전부 보고.

### Findings (가공 없음, 확신도 포함)

- [낮음] `tests/conftest.py:20` — `_DB_FILE = os.path.join(tempfile.gettempdir(), "moru_oracle_test.db")` 고정 경로. 다중 사용자 Linux 머신에서 `tempfile.gettempdir()`는 보통 world-writable `/tmp`를 반환한다 — 다른 로컬 사용자가 그 경로에 미리 심볼릭 링크를 심어두면 `os.remove` → aiosqlite 재생성 사이에서 TOCTOU로 임의 파일에 쓸 여지가 있다(고전적 `/tmp` 심볼릭 링크 공격 패턴). macOS는 사용자별 tempdir라 실제로는 안전하지만 코드 자체는 플랫폼 비의존적으로 취약하다 — `tempfile.mkdtemp()`/`mkstemp()`로 프로세스별 무작위 서브디렉터리를 쓰면 없어지는 클래스다. — 제안: `tempfile.mkdtemp(prefix="moru_oracle_")` 하위에 고정 파일명을 두는 정도로 충분
- [높음] 확인됨(실행) — `/docs`, `/openapi.json`, `/redoc`이 무인증으로 200을 반환한다(직접 프로브, 아래 "판정 방식" 참조). `test_http_auth.py`의 `AUTH_GET_ROUTES`/`PUBLIC_GET_ROUTES` 어느 목록에도 이 셋이 없다 — 오라클이 이 엔드포인트들을 검증 범위에서 **조용히** 뺐다. vibe-coding 체크리스트 ③에 정확히 해당. 앱 코드가 이걸 노출한 것 자체는 이번 diff의 결함이 아니지만(앱 무수정), 오라클이 "인증 걸린 라우트 전수"를 자처하면서 이 셋을 빠뜨린 것은 이 diff의 커버리지 결함이다.
- [중간] `03-design.md` R-5 / `01-planning.md` "사람 판정 3" — "토큰=관리자" 규칙이 `KY_USER_L`에 관리자만 들어간다는 **데이터 불변식**에 기댄다는 사실이 설계 문서에 명시돼 있고 숨겨져 있지 않다. 다만 `tests/test_http_auth.py`에는 이 불변식이 깨졌을 때(비관리자 행이 그 테이블에 들어갔을 때)를 겨냥한 음성 테스트가 없다 — 지금은 그런 행을 만드는 라우트 자체가 없어(가입 기능 없음) 테스트 불가능하지만, 나중에 가입/초대 기능이 생기면 이 오라클은 "토큰=관리자"를 계속 참으로 고정한 채 그 회귀를 못 잡는다. 지금 당장 고칠 결함은 아니고 한계 표기 대상.
- [높음] 확인됨(코드 읽기 + 실행) — `POST /admin/attendee` (`app/service/admin.py::post_attendee`)는 raw `request.json()`에서 `.get('attendee')`/`.get('notice')`/`.get('date')`만 명시적으로 뽑는다. `role`/`user_id`/`owner` 등 여분 필드를 실어 보내도 무시된다(직접 프로브 확인) — 체크리스트 ② mass assignment는 **해당 없음**, 오탐 아님.
- [높음] 확인됨(코드 읽기) — IDOR(체크리스트 ①)는 이 앱 구조상 **해당 없음**: `KY_USER_L`에 역할·소유자 컬럼이 없고, attendee 캘린더 데이터는 사용자 소유가 아닌 전역 데이터다. `cal_date` 경로 파라미터는 리소스 ID가 아니라 달력 월이라 "다른 사용자의 리소스"라는 개념 자체가 이 앱에 없다. 오라클이 이를 놓친 게 아니라 애초에 프로브 대상이 없다.
- [낮음] 확인됨(실행) — `GET /attendee/{cal_date}`, `GET /admin/attendee/export/{cal_date}`에 `not-a-date` 같은 값을 넣으면 `datetime.strptime` 이 잡히지 않은 `ValueError`를 던져 500이 난다. 실제 배포 형태(uvicorn, `raise_app_exceptions=False`와 동등한 실제 서버 조건)로 직접 재현한 결과 바디는 `Internal Server Error`뿐이었다 — **체크리스트 ④의 내부 정보 누출은 없다.** 다만 이건 correctness 렌즈(#2 에러 경로)의 영역이지 이 lens의 blocker는 아니고, 앱 코드를 안 건드리는 이번 diff 범위 밖이라 오라클에 없는 게 결함은 아니다. 참고용으로만 기록.
- [중간] 로그인 에러 메시지 — `app/service/login.py::login_post`는 "없는 사용자명"과 "틀린 비밀번호" 모두 동일하게 `HTTPException(401, "Login Failure")` → 401 핸들러가 동일한 307 `/login`으로 뭉갠다. 사용자 열거(user enumeration) 취약점 없음을 확인. `test_http_auth.py::test_login_rejects_a_username_that_does_not_exist` + `test_wrong_password_is_rejected`가 이 둘을 각각 음성 대조로 커버한다 — 오라클이 잘 짚었다.
- [낮음] `tests/conftest.py:24-30` `TEST_ENV` — `SECRET_SALT`/`ADMIN_PW` 모두 테스트 전용 더미 값("moru-oracle-test-salt", "admin")이고 실제 시크릿과 섞이지 않는다. `load_dotenv(override=False)` 특성상 conftest가 먼저 세운 값이 개발자 `.env`를 이긴다(주석·문서 모두 명시) — 실측상 안전. 시크릿 커밋 없음.
- [낮음] `tests/test_http_agent.py` — `GROQ_API_KEY`/`GEMINI_API_KEY`를 빈 문자열로 강제하고 `test_llm_keys_are_empty_in_tests`로 그 사실 자체를 가드한다. 이 가드가 없으면 이후 테스트가 실제 유료 호출을 낼 수 있는데, 가드가 먼저 돌아 캐치한다 — 방어 구조 적절.
- [낮음] `tests/test_http_socket.py` — 실소켓 서버가 `127.0.0.1` 고정 바인드 + 커널이 준 포트(0번 포트 바인드 후 조회)라 외부 노출·포트 충돌 위험 없음.
- [정보] `tests/test_http_agent.py::test_confirm_rejects_unknown_function` — `/agent/confirm`의 `kwargs: dict`는 임의 키-값을 받지만 `fn_name`이 레지스트리에 없으면 거부된다. 등록된 함수 내부로 임의 kwargs가 전달될 때의 파라미터 인젝션 여부는 이 오라클의 범위(HTTP 경계) 밖이고 앱의 tool-calling 레이어 자체 검증이 필요한 문제라 이 diff 결함은 아니다. 후속 조사 후보로만 남김.

### 체크리스트 ①~④ 엔드포인트별 순회

| 엔드포인트 | ① 인가/IDOR | ② mass assignment | ③ 디버그/관리 노출 | ④ CORS/rate-limit/에러누출 |
|---|---|---|---|---|
| `GET /login` | 해당 없음 - 공개 페이지, 리소스 ID 없음 | 해당 없음 - 쓰기 없음 | 해당 없음 | 에러 누출 없음 (템플릿 렌더만) |
| `POST /login/request` | 해당 없음 - 인증 경계 자체 | 해당 없음 - username/password 2필드만, role 없음 | 해당 없음 | 사용자 열거 없음(위 finding) — 오라클이 음성 대조 2건으로 커버 |
| `GET /logout` | 해당 없음 - 인증 불필요, 쿠키 삭제만 | 해당 없음 | 해당 없음 | 해당 없음 |
| `GET /attendee`, `/attendee/{cal_date}` | 해당 없음 - 전역 데이터, 소유자 개념 없음(FR-6 이진 모델) | 해당 없음 - 읽기 전용 | 해당 없음 | `{cal_date}` 잘못된 값 → 500 generic(정보 누출 없음, 확인됨) — 오라클 커버 없음(diff 범위 밖) |
| `GET/POST /admin/attendee`, `/admin/attendee/{cal_date}` | 해당 없음(구조상 IDOR 불가, 위 finding) — `get_current_user` 인증은 오라클이 302/307 포함 커버 | **해당 없음, 실행 확인** — 여분 필드 무시됨 | 해당 없음 | 위와 동일 잘못된 날짜 → 500 generic |
| `GET /admin/attendee/export`, `/export/{cal_date}` | 해당 없음(동일 구조) | 해당 없음 - 파라미터 없음 | 해당 없음 | `/export`(무날짜)는 설계상 도달 불가 등록으로 이미 범위 밖 처리(01-planning.md 명시) — 결함 아님 |
| `POST /agent/chat`, `/agent/confirm` | 인증 필요 확인됨(오라클 커버) — 소유자 개념 없음이라 IDOR 해당 없음 | pydantic 스키마 고정 필드만(`message`/`history`, `fn_name`/`kwargs`/`approved`/`queue`) — role/owner 필드 없음, 해당 없음 | 해당 없음 | LLM 미가용 시 200+`status:error`로 고정(R-6, 오라클 커버) — 예외 삼킴 확인됨 |
| `GET /`, `GET /docs`, `GET /openapi.json`, `GET /redoc` | 해당 없음(공개 의도, `/` health-check) | 해당 없음 | **`/docs`·`/openapi.json`·`/redoc` 무인증 노출 확인(실행) — 오라클이 검증 범위에서 뺌 (위 finding, 높음)** | 해당 없음 |

### 판정 방식 (실행 근거)

- `/docs`, `/openapi.json`, `/redoc` 무인증 200: 레포 밖 임시 프로브(`tests/ztmp_probe_test.py`, 판정 후 삭제)를 `client`(무토큰) fixture로 실행 — 3건 모두 200.
- mass assignment 무시: 동일 임시 프로브에서 `admin_client`로 `role`/`user_id`/`owner` 여분 필드를 얹어 `POST /admin/attendee` 호출 — 200, 서버 코드(`app/service/admin.py:75-81`)가 `.get()`으로 3개 필드만 뽑는 것을 코드로 확인.
- 잘못된 `cal_date` → 500 generic: 레포 밖 별도 스크립트(`/tmp/_probe2.py`, 삭제 완료)에서 `httpx.ASGITransport(app, raise_app_exceptions=False)`로 실제 서버 조건 재현 — `status: 500, body: "Internal Server Error"` (스택트레이스·내부 경로 없음).
- 로그인 에러 메시지 무차별: `app/service/login.py` 코드 읽기로 두 분기 모두 동일한 `HTTPException(401, "Login Failure")` 확인.
- IDOR 해당 없음 / mass assignment 해당 없음: `app/dao/tables.py::KyUserL` 스키마(`user_id`/`user_pw`뿐) + 라우트 표(`app/controller/router.py`) 읽기로 소유자·역할 필드 부재 확인.

### 검증하지 못한 것

- `/docs` 등이 실제로 **민감 정보**(내부 스키마·엔드포인트 구조)를 노출하는지 콘텐츠까지는 안 봤다 — 200이라는 것만 확인. 이 앱은 이미 소스가 열람 가능한 내부 도구로 보이므로 스키마 노출 자체의 실질 위험도는 사람 판단 필요.
- 심볼릭 링크 TOCTOU 프로브는 실행하지 않았다(추론 판정) — 실제로 공유 `/tmp` 환경에서 공격을 재현하지는 않았다.
- `/agent/confirm`의 `kwargs` 가 실제 등록된 도구 함수들에 전달됐을 때 파라미터 오염 가능성은 도구 레지스트리(`app/agent/tools.py`) 내부까지는 안 봤다.

### 숨은 결합 발견

없음 — 이미 `codebase-conventions.md` §숨은 결합에 이번 브랜치가 발견한 4건이 등재돼 있고, security 렌즈에서 추가로 찾은 것은 없다.
