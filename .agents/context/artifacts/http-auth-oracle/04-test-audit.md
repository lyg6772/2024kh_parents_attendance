# [4단계 §4] LOCK 전 독립 검수 — http-auth-oracle

검수자: 테스트 작성에 관여하지 않은 fresh-context 에이전트 (moru 파이프라인 4단계).
대상: `tests/conftest.py`(수정) + `tests/test_http_{auth,pages,agent,env,socket}.py`(신규, 38개).
방법: 추측 없이 실행 — 5개 파일 전부 실행(38 passed), 미커버 후보 2건은 별도 프로브로
동작을 실측했다 (LLM 키 빈 값 강제). 임시 프로브 DB 파일은 삭제했다.

## AC 커버리지 대조

| AC | 대응 테스트 | 판정 |
|---|---|---|
| AC-1 (목 값 관측) | `test_http_env.py::test_config_uses_the_mock_values_not_the_developer_env` — SECRET_SALT·DB_URL·EXPIRE_HOURS 를 `TEST_ENV` 와 직접 대조 | 커버 |
| AC-2 (무토큰 → /login 리다이렉트) | `test_http_auth.py::test_no_token_is_redirected_to_login` (GET 3) + `test_no_token_post_is_redirected_to_login` (POST 3) — 도달 가능한 인증 라우트 6개 전부. 무날짜 export 는 문서화된 죽은 등록이라 제외 타당 | 커버 |
| AC-3 (유효 토큰 → 정상 응답, "상태 코드 + 본문/헤더") | GET 3개는 `test_valid_token_reaches_the_route`(상태) + pages 의 html/엑셀 본문 단언, `/agent/chat`·`/agent/confirm` 은 agent 파일이 본문까지. **`POST /admin/attendee` 만 유효 토큰 양성이 어디에도 없다** | **부분 — 누락 1** |
| AC-4 (만료·위조 거부) | `test_bad_tokens_do_not_reach_the_route` (expired/forged/garbage/empty) + `test_expired_and_forged_are_distinguishable_below_http` (decode 직접 — 양성 대조 포함) | 커버 |
| AC-5 (취약 패키지 실행) | `test_http_env.py` 프레임 관측 (jinja2·starlette·jwt·multipart >0) + `test_http_socket.py` (h11 >0). cryptography 는 2단계 실측(실행 경로 0)으로 구조적 미커버로 하강 — 테스트는 그 판정을 따르고 **음성으로 고정**한다 | 커버 (아래 § 설계 불일치의 문서 정정 1건) |
| AC-6 (2회 동일 결과) | 테스트 파일의 몫이 아니라 §4-2 결정성 게이트 — **아직 미수행, LOCK 전 필수** | 게이트 대기 |
| AC-7 (무토큰 /attendee 정상) | `test_public_routes_work_without_a_token` (`/attendee`, `/attendee/202601` 포함) | 커버 |
| AC-8 (외부 LLM 호출 0) | `test_http_agent.py` 3단 — 키 빈 값 가드 + `get_llm` 예외 + `/agent/chat` `status:"error"`. 어댑터 생성 전에 예외가 나는 구조라 호출 0 이 기전으로 보장된다 | 커버 |
| AC-9 (엑셀 스트림) | `test_excel_export_streams_a_workbook` — content-type + disposition + `PK` zip 매직 | 커버 (강한 단언) |

라우트 스윕 관점 추가: 앱 라우트 13개 중 **`GET /logout` 만 아무 테스트도 안 탄다**
(A-4 "라우트를 전부 훑는다" 위반). 프로브 실측: 307 `Location: /attendee` +
`token` 쿠키 삭제(`Max-Age=0`) — 인증 스토리의 반대편 절반이라 오라클 가치가 있다.

## R 분기 대조

| 규칙 | 양성 | 음성 | 판정 |
|---|---|---|---|
| R-1 무토큰 → 307 | GET 3 + POST 3 ✓ | R-2 유효 → 200 ✓ | 커버 |
| R-2 유효 토큰 → 정상 | GET 3 ✓, `/agent/chat`·`/confirm` ✓ (agent 파일) | R-1/R-3 ✓ | **`POST /admin/attendee` 양성 누락** — 유일한 쓰기 라우트인데 유효 토큰 경로가 0. 프로브 실측: 200 `"OK"` + 저장값이 조회 페이지에 반영됨 |
| R-3 만료·위조 → 307 (HTTP 층 무구별) | 4종 파라미터 ✓ | decode 직접 호출로 만료("expired")·위조("invalid") 구별 + 유효 토큰 왕복 양성 대조 ✓ | 커버 — 양성 대조 덕에 "항상 던지는" 구현이 못 통과한다 |
| R-4 무토큰 /attendee 조회 | 4개 공개 라우트 200 ✓ | R-1 ✓ | 커버 |
| R-5 토큰 = 관리자 자격 | `test_login_issues_a_working_token` (발급 토큰으로 보호 라우트 통과) ✓ | `test_wrong_password_is_rejected` ✓ | 커버. 데이터 불변식(KY_USER_L 관리자 전용)은 설계가 이미 테스트 불가 한계로 명시 |
| R-6 키 없음 → error | chat error + pending None ✓ | 설계가 "음성 없음"을 한계로 명시 (A-5) — 일치 | 커버 |

기전 검증 (실행): `get_current_user`(`app/util/auth.py:40-46`)는 빈/무 토큰도
`decode_token("")` → `InvalidTokenError` → 401 → 307 핸들러로 흐른다. R-1·R-3 이
같게 관측되는 이유가 코드와 일치함을 확인했다.

## 약한 단언

1. **`tests/test_http_env.py:57` `test_the_oracle_actually_executes_the_vulnerable_packages` —
   프로브 요청 3개의 응답 상태를 안 본다.** 로그인 POST 가 401/422 로 굴러도
   starlette·jinja2 프레임은 >0 이라 초록일 수 있다 — "덮인다"가 에러 경로로 덮인
   것일 수 있다. 강화: 세 요청 각각 `assert res.status_code == 200` 한 줄씩 (총 3줄).
   행동 오라클은 다른 파일들이 갖고 있으므로 심각도 minor, 그러나 3줄이면 닫힌다.
2. **`tests/test_http_pages.py:36` `test_form_post_parses_urlencoded_body` —
   `test_http_auth.py::test_login_issues_a_working_token` 과 같은 요청의 약한 판본**
   (200 만 봄, auth 쪽은 토큰·쿠키·보호 라우트 통과까지 봄). taxonomy §2 중복 규칙상
   삭제 제안 — 음성 대조(`test_form_post_rejects_missing_fields`)만 pages 에 남기면 된다.
   유지한다면 "파일 지역성" 사유를 주석 1줄로. minor.
3. `test_valid_token_reaches_the_route` 의 상태-단독 단언은 A-6(무인자 경로는 상태만)
   + pages/agent 파일의 본문 단언이 짝이라 **약한 단언으로 치지 않는다** — 지적 아님.

## 설계 불일치 / 범위 확장

- **문서 층 불일치 (테스트 결함 아님)**: `01-planning.md` AC-5 텍스트가 여전히
  cryptography 를 "실행할 5종"에 포함한다. 2단계 실측(프레임 0, 실행 경로 없음)과
  사람 판정으로 대체됐는데 AC 문구가 미수정 — 테스트는 옳은 쪽(구조적 미커버 고정)을
  따르고 있다. `01-planning.md` AC-5 를 "h11·python-multipart·pyjwt·jinja2·starlette
  (cryptography 는 실행 경로 없음 — 2단계 실측)"로 정정하라.
- **범위 확장 후보 1건 — 채택 판정**: `test_confirm_rejects_unknown_function` 은 설계
  규칙 표에 없는 동작(레지스트리 기각)을 고정한다. 다만 `/agent/confirm` 의 유효 토큰
  양성 대조를 겸하는 유일한 테스트이고 LLM·외부 호출 없는 경로라, 삭제하면 R-2
  커버리지가 줄어든다. 임의 기능 추가가 아니라 R-2 파생으로 판정 — 유지.
- 만료·위조 토큰의 `jwt.encode` 직접 제조는 D-4 가 명시한 설계 그대로다 — 확장 아님.
- `detail` 문자열("expired"/"invalid") 매칭: 두 예외가 모두 401 이라 구별 채널이 detail
  뿐이다. 설계 밖 문자열 결합이지만 대체 수단이 없다 — 허용.

## 자기 기대 검증 점검 (질문 5)

- `test_config_uses_the_mock_values...`·`test_llm_keys_are_empty_in_tests` 는 앱이 아니라
  **하네스를** 검증하지만, AC-1·AC-8 이 명시적으로 요구한 가드다 — 정당.
- `decode_token` 테스트는 유효 토큰 양성 대조를 포함해 "무조건 예외" 구현을 배제한다.
- 유효 토큰을 앱 경로(`AuthHandler.encode_token`)로 만드는 왕복은 D-4 판정 그대로이고,
  만료·위조 토큰이 독립 `jwt.encode` 로 같은 salt·알고리즘을 교차 검증한다.
- **자기 기대만 검증하는 자리: 없음.**

## test_http_env.py 하한 단언 판정 (질문 6)

**하한(`>0`)이 옳다.** 근거:
- 잡으려는 결함이 "import 만 되고 실행 0 인 가짜 초록"이므로 >0 이 정확히 그 결함을
  잡는다. 정확 수치는 라이브러리 버전에 결합돼 업그레이드를 막는다 (A-10, 실측 근거).
- **음성 대조가 짝으로 있다**: `test_known_uncovered_packages_stay_uncovered` 가
  h11·cryptography·pymysql == 0 을 고정해, "COVERED 목록을 늘리기만 하면 초록" 경로를
  막고 커버리지 증가를 신호로 승격시킨다. 하한 단독이면 뚫렸을 자리를 이 짝이 닫는다.
- 실측 확인: 5파일 실행 전부 그린, 소켓 테스트의 h11 >0 단언과 env 의 h11 == 0 단언이
  서로의 반증 가능성을 만든다.
- 남는 구멍은 하한 방식이 아니라 프로브 요청의 상태 미단언 (§ 약한 단언 1) — 3줄 보강.

## taxonomy 채점

| 항목 | 우선 | 판정 |
|---|---|---|
| 요구사항→테스트 | HIGH | FR-1~6 전부 매핑. AC-3 만 부분 (POST /admin/attendee) |
| Positive/Negative | HIGH | R-2 의 POST /admin/attendee 양성 1건 제외하고 전 규칙 양·음 존재 |
| 공통 인증 미들웨어 dedup | — | 준수 — bad-token 4종은 라우트 1개에서만, 스윕은 상태만. 중복 1건은 § 약한 단언 2 (pages 폼 테스트) |
| 인가 정책 per-policy | — | 이진 모델의 양편(AUTH/PUBLIC)을 각각 스윕 — 준수 |
| Null/누락 | HIGH | 폼 필드 누락 422 ✓, 무토큰 ✓ |
| Empty | HIGH | 빈 문자열 토큰 ✓ |
| Length / Range | HIGH | N/A — 설계에 길이·범위 검증 규칙 없음 (앱 무수정 오라클) |
| Duplicate / Unicode / Ordering | MED | N/A — 설계 함의 없음 (chat 바디의 한글 입력은 부수적으로 존재) |
| Invalid Input | HIGH | garbage 토큰 ✓, 폼 422 ✓ |
| Exception | HIGH | 에러 정책 = R-1·R-3·R-6 전부 ✓ |
| Conflict | MED | N/A — 유니크/멱등 설계 없음 |
| Schema / Status / Error Response | HIGH | chat 바디 키 ✓, login JSON+쿠키 ✓, 엑셀 헤더+매직 ✓, 307 Location ✓ |
| Idempotency / Round Trip / Invariant | — | Idempotency N/A, Round Trip ✓ (encode↔decode), Invariant N/A (R-5 데이터 불변식은 테스트 불가로 명시됨) |
| Concurrency / Perf / Golden | — | N/A — 설계 함의 없음 |

## 판정

**LOCK 보류 — 보강 2건 반영 후 LOCK 가능.** 테스트 품질은 전반적으로 높다 (음성 대조
습관, 강한 콘텐츠 단언, dedup 준수, 커버리지의 실행 관측). 잘못된 스펙을 고정하는
테스트는 없다 — 전 단언이 실측 현행 동작과 일치함을 실행으로 확인했다.

LOCK 전 필수 (커버리지 누락 — 잠기면 5~7단계 내내 이 구멍이 계약이 된다):
1. **`POST /admin/attendee` 유효 토큰 양성 테스트 추가** (R-2/AC-3/FR-3). 유일한
   쓰기 라우트다. 실측 기대값: `{"attendee": "...", "notice": "...", "date": "YYYYMMDD"}`
   POST → 200 `"OK"`, 이후 해당 월 조회에 저장값 반영. `test_http_auth.py` 또는
   `test_http_pages.py` 에 1개.
2. **`GET /logout` 테스트 추가** (A-4 라우트 스윕의 마지막 구멍). 실측 기대값:
   307 `Location: /attendee` + `token` 쿠키 삭제(`Max-Age=0`).

권고 (minor — 같은 편집에서 싸게 닫힌다):
3. env 커버리지 테스트의 프로브 요청 3개에 상태 코드 단언 3줄 (§ 약한 단언 1).
4. pages 의 중복 폼 양성 테스트 삭제 또는 사유 주석 (§ 약한 단언 2).

문서 정정 (테스트 아님): `01-planning.md` AC-5 의 cryptography 문구를 2단계 실측
판정으로 갱신.

이후 순서: 보강 반영 → §4-1 뮤테이션 검증 → §4-2 결정성 게이트(2회 실행) → LOCK.
둘 다 아직 미수행이다 — 이 검수는 그것을 대체하지 않는다.
