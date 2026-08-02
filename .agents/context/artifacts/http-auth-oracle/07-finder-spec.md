## finder: spec-일치 (`.agents/07-review.md` §1-1)

### 입력
- 설계: `03-design.md`(R-1~R-6, § 통합 계획, § 가정 대장 A-8~A-10, § 분기 완전성),
  `01-planning.md`(FR-1~FR-6, AC-1~AC-9, § 범위 밖, A-1~A-7), `02-feature-analysis.md`
  (기능 1~11, 라우트 표, 커버리지 실측)
- diff: `tests/conftest.py`(수정), `tests/test_http_{auth,pages,agent,env,socket}.py`(신규),
  `osv-scanner.toml`(머리말 수정), `.agents/context/codebase-conventions.md`(§ 숨은 결합 5줄)
- 참고: `04-test-audit.md`, `04-mutation-check.md` (같은 기능의 4단계 산출물 — 대조용으로 읽음)

### 답변 (요청받은 5개 질문)

**1. FR-1~FR-6·AC-1~AC-9 중 구현 없는 것 — 없음.**
전부 매핑 확인함: FR-1(ASGI 전체 경로)·FR-2(인증 경로)·FR-3(토큰 유무 분기)·
FR-4(`test_config_uses_the_mock_values_not_the_developer_env`)·FR-5(sqlite 강제)·
FR-6(이진 인가) 전부 테스트로 존재. AC-1~AC-5·AC-7~AC-9 전부 대응 테스트 확인.
AC-6(2회 동일 결과)은 이 5개 파일이 아니라 4단계 결정성 게이트의 몫 — 설계도 그렇게
분류했으므로 이 파일들의 누락이 아니다.

**2. 기능 1~11 중 빠진 것 — 없음.**
기능 10(환경 고정 확인) = `test_http_env.py::test_config_uses_the_mock_values...`,
기능 11(h11 스모크) = `test_http_socket.py` 둘 다 존재. 기능 1~9 전부 대응 파일 확인.

**3. 설계에 없는데 임의로 추가된 것 — 코드 자체엔 없음. 단, 워킹트리에 설계 밖 파일 1개.**
`tests/ztmp_probe_test.py` (untracked) — 아래 finding 1 참조. 03-design.md 통합
계획 표에 없는 파일이고 tests/ (LOCK 대상)에 있다. 나머지 § 범위 밖 표 항목
(무날짜 export, `.env` 부재 재현, pymysql 커버리지, 템플릿 경로 수정, cookie
secure=True)은 전부 침범 없음 확인 — 무날짜 export 는 `AUTH_GET_ROUTES` 에서
명시적으로 제외됐고, `app/` diff 는 0건.

**4. 가정 대장(A-1~A-10) 불일치 — 없음.**
A-1(고정 salt)·A-2(override)·A-4(라우트 실측 리스트 그대로 사용)·A-5(LLM 키 빈값)·
A-6(고정 날짜 `202601`)·A-7(teardown clear)·A-8(파일 sqlite)·A-9(admin/admin)·
A-10(하한만 `>0`) 전부 코드와 일치 확인(각각 대응 라인 대조함).

**5. 설계가 "이렇게 한다"고 적은 것과 코드가 실제로 하는 것이 다른 자리 — 2건 (아래 finding 2·3).**
통합 계획의 fixture 아키텍처(session-scope `seeded_admin` 분리, 단일 `tokens` fixture,
실소켓 "1개")가 실제 구현과 구조적으로 다르다. 기능적 결과는 동일하다.

### finding

- [낮음] `tests/ztmp_probe_test.py` (전체, untracked — `git status --short`) — 03-design.md
  § 통합 계획의 파일 목록에 없는 파일이 LOCK 대상 `tests/` 안에 존재한다. 파일 자체
  docstring이 "임시 프로브 — 판정 후 삭제. security+규칙 렌즈 finder 확인용"이라 밝혀
  다른(병렬) finder의 잔여물로 보이나, 커밋되지 않은 채 워킹트리에 남아 있다.
  근거: `git status --short` → `?? tests/ztmp_probe_test.py`. 내용을 읽어 확인함 —
  `/docs` `/openapi.json` 등 디버그 엔드포인트 노출, 에러 상세 누출, mass-assignment
  프로브 3종. 이 finder 범위(spec-일치) 자체의 결함은 아니지만, 이 상태로 커밋되면
  설계에 없는 파일이 diff에 섞인다 — 삭제 여부는 사람/조율 판단.

- [낮음] `tests/test_http_socket.py` 전체 — `03-design.md` § 설계 근거는 "**실소켓은
  1개만 둔다**... 자주 안 도는 오라클은 오라클이 아니다"라고 명시하는데, 실제로는
  `live_server`(function-scope, 매 테스트 uvicorn 재기동) 를 쓰는 테스트가 2개
  (`test_app_serves_over_a_real_socket`, `test_real_socket_path_executes_h11`)라
  실소켓 기동이 2회다. 다만 후자는 h11 프레임 `>0` 을 직접 재 `test_http_env.py`의
  `==0`(ASGITransport) 단언과 짝을 이루는 음성대조용으로 보여, 설계가 반대하는
  "전부 실소켓"과는 다른 성격일 수 있다. 근거: 파일 읽음 + `03-design.md:103-106`
  대조. 확신도를 낮음으로 둔 이유가 그 정황.

- [중간] `tests/conftest.py:76-107` `seeded_app` fixture — `03-design.md` § 통합
  계획은 `fixture: seeded_admin(session)`(bcrypt 비용 때문에 세션 스코프로 분리)과
  `fixture: client(function)`(dependency_overrides 설정)을 **별도 픽스처**로 명시한다.
  실제는 테이블 생성 + admin 시드 + `dependency_overrides` 설정을 **하나의
  function-scope `seeded_app`** 으로 합쳤다. `if existing is None` 가드가 매 테스트
  bcrypt 재해시를 막아 설계가 우려한 비용 문제는 사실상 회피됐지만, 구조 자체는
  설계 문서와 다르게 구현됐다. 근거: `git diff -- tests/conftest.py` + `03-design.md:56-60`
  대조.

- [낮음] `tests/conftest.py` / `tests/test_http_auth.py` — 설계 § 통합 계획의
  `fixture: tokens(function) valid / expired / forged`가 그대로 구현되지 않았다.
  `valid_token` fixture(conftest.py:120-123)만 존재하고, expired/forged 는
  `test_http_auth.py:63-80`의 모듈 레벨 **일반 함수**(`_expired_token`,
  `_forged_token` — fixture 아님, `pytest.mark.parametrize` 인자로 즉시 호출됨)로
  구현됐다. 커버리지는 동등하나(AC-4 전부 대응) 설계가 명시한 fixture 명·구조와
  다르다. 근거: `03-design.md:60` 대 실제 파일 대조.

### 확인했으나 지적 없음 (근거 남김 — coverage 확인용)

- `app/` 변경 0건 — `git diff --stat -- app/` 결과 공백. C-1 준수 확인.
- `pyproject.toml`/`poetry.lock` 변경 0건 — C-2(의존성 추가 금지) 준수 확인.
- 라우트 표(02-feature-analysis.md, 인증 7개 중 도달 가능 6개)와
  `test_http_auth.py::AUTH_GET_ROUTES`/`AUTH_POST_ROUTES` 완전 일치 확인 (무날짜
  export 는 § 범위 밖 표대로 제외).
- `osv-scanner.toml` 의 "`tests/test_http_*.py` 40개" 서술 — `pytest --collect-only`
  로 실측 40개 확인, 문서 숫자와 일치.
- A-1~A-10 전부 코드와 대조 완료, 불일치 없음 (위 답변 4 참조).
- `04-test-audit.md`(LOCK 전 필수 2건: `POST /admin/attendee` 양성, `GET /logout`)와
  `04-mutation-check.md`(#9: `test_unknown_username_is_rejected` 류 보강)가 요구한
  보강이 현재 diff에 전부 반영돼 있음을 확인함 —
  `test_write_route_accepts_a_valid_token`, `test_logout_clears_the_token_cookie`,
  `test_login_rejects_a_username_that_does_not_exist`. 아울러 04-audit의 "약한 단언"
  권고(env 프로브 3건 상태코드 단언, pages 중복 폼 테스트 제거)도 반영됨
  (`test_http_env.py:73-78` 상태 단언 존재, `test_http_pages.py`에 중복 테스트 없음).
  → 이 4단계 이후 보강분은 이 diff의 정상적 일부로 보여 finding 아님, 대조 근거로만 기록.
- `40 passed` — `GROQ_API_KEY="" GEMINI_API_KEY="" poetry run pytest tests/test_http_auth.py
  tests/test_http_pages.py tests/test_http_agent.py tests/test_http_env.py
  tests/test_http_socket.py -q` 실행 확인 (외부 호출 없음, 1.85s).
