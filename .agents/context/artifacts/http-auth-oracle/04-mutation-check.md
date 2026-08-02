## [4단계] 뮤테이션 검증 산출물

### 입력
- 3단계 산출물: `03-design.md` (R-1~R-6, 통합 계획, 가정 대장) — 참조함
- 심판 대상: `tests/test_http_auth.py`, `test_http_pages.py`, `test_http_agent.py`,
  `test_http_env.py`, `test_http_socket.py`, `tests/conftest.py`
- 누락 입력: 없음

### 성격 — 이 검증의 특수성

이 브랜치는 테스트만 추가하고 앱은 고치지 않는다. 목적은 "의존성 업그레이드가
앱을 깨뜨렸을 때 red 가 되는 오라클"이다. 따라서 뮤테이션 대상은 테스트가 아니라
**`app/` 코드**다 — "스펙(R-1~R-6)을 위반하도록 앱을 망가뜨렸는데도 테스트가 전부
초록인가?"를 실행으로 확인한다.

## 연산자 순회

`.agents/context/test-taxonomy.md` §7 연산자 5종을 이 도메인에 내린 것:

| 연산자 | 이 도메인에서 무엇인가 | 시도 |
|---|---|---|
| Missing Validation | JWT 만료/서명 검증 생략, `get_current_user` 무토큰 통과, 비밀번호 검증 생략, 인가 Depends 제거, LLM 키 가드 생략, DB 쿼리 WHERE 절 누락 | 시도함 (아래 표 #1·#2·#3·#5·#8·#9) |
| Wrong Branch | 응답 페이로드를 스펙과 다른 것으로 바꿔치기 (엑셀 빈 바이트, 템플릿 빈 200) | 시도함 (#6·#7) |
| Missing Validation (라우트별) | 공유 함수가 아니라 **라우트별로 선언된** Depends 하나만 제거 | 시도함 (#4) |
| Off-by-One | 토큰 만료 경계값(±1초) | **건너뜀** — `jwt` 라이브러리의 `exp` 검사는 `leeway=0` 이 기본이고, 설계 R-1~R-6 중 경계 초 단위를 스펙으로 고정한 규칙이 없다. 물릴 지점이 없다 |
| Incorrect Order | 인증 체크 순서(토큰 파싱 vs 라우트 핸들러 실행) 변경 | **건너뜀** — FastAPI 의존성 해석은 라우트 진입 전에 실행되도록 프레임워크가 고정한다. 앱 코드 레벨에서 순서를 바꿀 지점이 없다 (Depends 자체를 빼는 것은 Missing Validation 으로 이미 커버) |
| Duplicate Processing | 로그인 시 토큰 이중 발급, DB 커밋 중복 | **건너뜀** — R-1~R-6 어느 것도 멱등성·중복 방지를 규정하지 않는다. 중복 발급해도 관측 가능한 스펙 위반이 없다 |

지시받은 7종 시도 + 추가로 §7 연산자를 도메인에 재적용해 2건 더 시도(#8 LLM 가드
우회, #9 DB 쿼리 WHERE 누락) — #9 에서 **뚫렸다** (아래 "뚫린 자리" 참조).

## 뮤테이션 표

| # | 무엇을 망가뜨렸나 | 파일 | red 테스트 | 뚫렸으면 왜 |
|---|---|---|---|---|
| 1 | `decode_token` 이 만료를 안 봄 (`verify_exp: False`) | `app/util/auth.py` | `test_bad_tokens_do_not_reach_the_route[expired]`, `test_expired_and_forged_are_distinguishable_below_http` | — |
| 2 | `decode_token` 이 서명을 안 봄 (`verify_signature: False`) | `app/util/auth.py` | `test_bad_tokens_do_not_reach_the_route[expired,forged]`, `test_expired_and_forged_are_distinguishable_below_http` | — |
| 3 | `get_current_user` 가 토큰 없으면 `"anonymous"` 로 통과 | `app/util/auth.py` | `test_no_token_is_redirected_to_login`(3 라우트), `test_no_token_post_is_redirected_to_login`(3 라우트), `test_bad_tokens_do_not_reach_the_route[empty]` | — |
| 4 | `admin_attendee_get_default` 에서 `Depends(get_current_user)` 제거 | `app/controller/admin.py` | `test_no_token_is_redirected_to_login[/admin/attendee]`, `test_bad_tokens_do_not_reach_the_route`(4종) | — (`router.py` 자체엔 `Depends` 가 없다 — 실제 주입 지점은 각 핸들러 함수 시그니처. 지시문 표현과 실측 위치가 다름을 여기 명시) |
| 5 | `login_post` 가 비밀번호 검증을 건너뜀 (`if True`) | `app/service/login.py` | `test_wrong_password_is_rejected` | — |
| 6 | 엑셀 export 가 빈 바이트(`b""`) 반환 | `app/controller/admin.py` | `test_excel_export_streams_a_workbook` (매직 바이트 `PK` 단언) | — |
| 7 | 로그인 페이지가 템플릿 대신 빈 200 반환 | `app/service/login.py` | `test_login_page_renders_html` (`<form` 단언) | — 단, `test_public_routes_work_without_a_token[/login]` 은 상태코드만 봐서 **못 잡는다** (아래 뚫린 자리 참조 — 이번엔 다른 테스트가 잡아 전체는 안 뚫림) |
| 8 | `get_llm()` 이 키 없어도 예외 대신 더미 어댑터 반환 (R-6 가드 우회, 실제 외부 호출 없음) | `app/agent/llm.py` | `test_get_llm_refuses_without_keys`, `test_chat_returns_error_without_calling_out` | — |
| 9 | `get_password` 쿼리에서 `WHERE user_id == ...` 절 제거 (임의 사용자명으로 로그인 가능해짐) | `app/dao/functions.py` | **없음 — 전부 통과 (27 passed)** | **뚫림.** 시드 사용자가 `admin` 1명뿐이라 `LIMIT 1` 만 남아도 우연히 admin 의 해시가 반환된다. "존재하지 않는 사용자명으로 로그인 시도"를 검증하는 테스트가 없다 |

## 뚫린 자리

**#9 — 사용자명 검증 없는 로그인 (뚫림, 실질적 구멍)**

- **공격 재현**: `app/dao/functions.py::get_password` 에서 `.where(KyUserL.user_id == user_id)` 를
  빼면(예: 의존성 업그레이드로 SQLAlchemy 쿼리 빌더 체이닝이 깨지는 시나리오), 존재하지
  않는 사용자명("nonexistent")으로 로그인해도 시드된 `admin` 해시가 그대로 반환돼
  비밀번호만 맞으면(`admin`) 로그인이 성공한다. **27개 테스트 전부 초록.**
- **왜 안 잡히나**: 현재 스위트의 모든 로그인 테스트가 `ADMIN_ID`("admin")로만
  로그인을 시도한다 (`test_login_issues_a_working_token`, `test_wrong_password_is_rejected`,
  `test_form_post_parses_urlencoded_body`). "다른 사용자명"을 시도하는 테스트가
  전혀 없다 — 시드가 1명뿐이라 쿼리가 사실상 `user_id` 를 무시해도 우연히 통과한다.
- **필요한 테스트**: `tests/test_http_auth.py` 에
  `test_unknown_username_is_rejected(client)` 추가 — `/login/request` 를
  `{"username": "nonexistent-user", "password": ADMIN_PW}` 로 POST 하고
  `307 /login`(또는 401) 을 단언한다. 이게 있었으면 #9 뮤테이션이 즉시 잡힌다.
- **설계 R-5 와의 관계**: `03-design.md` R-5 는 "토큰=관리자 자격, 테이블에 관리자만
  들어간다는 데이터 불변식에 기댄다"고 명시한다. 이번 뮤테이션은 그 불변식과 별개로
  **"쿼리가 요청한 사용자명을 실제로 거르는가"** 라는, R-5 가 명시하지 않은 선행 조건을
  드러낸다 — 사람이 판단할 지점: 이 테스트를 지금 이 브랜치(오라클 추가)에 넣을지,
  후속 과제로 미룰지.

그 외 뚫린 자리 없음. 시도한 8개 뮤테이션(#1~#8)은 전부 잡혔다.

## 트리 청결 확인

시작:
```
 M .agents/context/codebase-conventions.md
 M tests/conftest.py
?? .agents/context/artifacts/http-auth-oracle/
?? .agents/context/decisions/http-auth-oracle.md
?? function_calling_deck.html
?? tests/test_http_agent.py
?? tests/test_http_auth.py
?? tests/test_http_env.py
?? tests/test_http_pages.py
?? tests/test_http_socket.py
```

종료 (동일):
```
 M .agents/context/codebase-conventions.md
 M tests/conftest.py
?? .agents/context/artifacts/http-auth-oracle/
?? .agents/context/decisions/http-auth-oracle.md
?? function_calling_deck.html
?? tests/test_http_agent.py
?? tests/test_http_auth.py
?? tests/test_http_env.py
?? tests/test_http_pages.py
?? tests/test_http_socket.py
```

각 뮤테이션 직후 해당 파일만 `git checkout --` 로 즉시 원복했다 (커밋·`git add` 없음).

### 종료 조건
- [x] 연산자 5종을 도메인에 내려 시도 (해당 없는 2종은 사유 명시)
- [x] 지시된 7개 최소 시도 + 추가 2개(연산자 재적용) = 총 9개 뮤테이션
- [x] 8/9 뚫리지 않음, 1/9(#9) 뚫림 — 구체적 보강 테스트안 제시
- [x] 임시 구현 전부 폐기 확인 (트리 청결 대조 일치)
- [x] 전체 스위트 대신 관련 파일만 실행 (매회 <1.3초)

### 실패 시
- #9 가 뚫렸으므로 04-test-generation.md §4-1 규칙상: 그 위반 경로를 잡는 테스트를
  추가하고 다시 시도해야 한다 (최대 2라운드). **이 산출물은 그 반영 전 상태** — 사람
  판단 대기: R-5 데이터 불변식 문서화로 충분한지, 아니면 위 `test_unknown_username_is_rejected`
  를 추가해 LOCK 할지.
