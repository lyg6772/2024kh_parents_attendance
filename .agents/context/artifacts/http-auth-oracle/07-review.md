# [7단계] 리뷰 산출물 — 델타 재리뷰 (http-auth-oracle) · 2026-08-03

역할: `.agents/07-review.md` §1-1 2번(verifier 겸 judge) + §4-1(재리뷰 — 델타).
직전 라운드(2026-08-02) verdict 는 **BLOCK, major 2건**이었다. 이 라운드는 그 2건이
**실제로 해소됐는지**와 **수정이 새로 만든 문제**만 본다.

- 델타 범위: `git diff d398d47..HEAD` — `tests/conftest.py`, `tests/test_http_socket.py`,
  `tests/test_http_env.py`, `tests/test_http_pages.py`, `osv-scanner.toml`,
  결정 로그, LOCK 마커 삭제. **앱 코드 변경 0건** (`git diff --stat origin/master...HEAD -- app/` 공백 재확인).
- 전체 브랜치 diff: `git diff "$(sh scripts/default_branch.sh)"...HEAD` = `origin/master...HEAD`.
- **풀 재리뷰 승격 조건 미해당**으로 판정했다: 델타가 건드린 파일이 전부 직전 리뷰 diff
  안에 있고, 앱 공유 코드(`app/`, deps, core)는 무수정이다. 다만 `tests/conftest.py` 는
  전 스위트가 물고 있으므로 파급을 **전체 스위트 실행으로** 대신 확인했다 (아래 282 passed).
- 게이트 판정: `03-design.md` 가 **비게이트** — 심층 적대 렌즈 미실행, 2차 verifier 미적용
  (§1-1 3번: 비게이트는 1차 PASS 로 확정).
- 베이스라인: `GROQ_API_KEY="" GEMINI_API_KEY="" poetry run pytest tests/test_http_*.py -q`
  → **40 passed in 1.62s**. 전체 `poetry run pytest -q` → **282 passed in 171.49s** (회귀 0).
  결정성: 소켓 파일 5회 연속 동일(2 passed), 파일 역순 40 passed.

---

## 중복 제거 후 finding

직전 라운드에서 넘어온 것 + 이번 델타에서 새로 본 것을 한 표로 합쳤다.
(직전 라운드 렌즈 3개 finding 의 원계열은 아래 §Finder 원출력이 소유한다.)

| # | 계열 | 출처 | 직전 등급 | 이번 상태 |
|---|---|---|---|---|
| M | h11 프레임 계측이 서버가 아니라 httpx 클라이언트를 센다 | 직전 verifier 추가 | major | **해소 확인 (프로브)** |
| A | 고정 임시 DB 경로 → 동시 pytest 프로세스 충돌 (+ 공유 `/tmp` 심링크 TOCTOU) | correctness[높음]+security[낮음] 병합 | major | **해소 확인 (프로브)** |
| P | `COVERED_PACKAGES` 가 모듈 개명(`multipart`→`python_multipart`)에 false red | 게이트 라운드 2 | (신규 수정) | **해소 확인 (프로브)** |
| Q | 생 소켓 응답 읽기(`await reader.read()`)에 타임아웃이 없다 — 서버가 안 닫으면 무한 대기 | 이번 verifier 추가 | — | **확정 minor** |
| N | cryptography 음성 대조가 JWT·bcrypt 를 안 타는 트래픽에서 0 을 잰다 | 직전 verifier 추가 | minor | **미수정 — minor 유지 (2라운드째)** |
| B | 세션 스코프 물리 sqlite 공유로 테스트 간 쓰기가 샌다 | correctness[높음] | minor | **미수정 — minor 유지 (재확인)** |
| D | 실소켓 서버 2회 기동 + 파일 docstring("1개/유일한")이 실제 2개와 어긋남 | spec[낮음]+correctness[중간] | minor | **미수정 — minor 유지 (재확인)** |
| O-1 | `dependency_overrides.clear()` 가 전량 삭제 | 직전 verifier 추가 | minor | **미수정 — minor 유지 (재확인)** |
| O-2 | `len(res.content) > 0` 중복 단언 | 직전 verifier 추가 | minor | **해소 (삭제됨)** |
| O-3 | 프레임 카운터가 두 곳에 중복 구현 | 직전 verifier 추가 | minor | **미수정 — 등급 하강 사유 있음 (아래)** |
| C·F·G·E·H·I·J·K·L | 직전 라운드에서 **기각**된 것들 | 각 렌즈 | 기각 | 델타가 이 판정을 뒤집지 않음 (재확인) |

이번 델타에서 **새 blocker/major 는 나오지 않았다.** 새로 든 후보는 Q 하나이고 minor 로 확정했다.

---

## 반박 검증

모든 판정은 프로브 실행이다. 기각(=버그 없음) 방향 프로브는 **양성 대조를 먼저 통과**시켰다
(일부러 깨뜨린 변형에서 red 가 나는 것을 확인한 뒤 원본에 돌렸다). 프로브 파일은 전부
`$TMPDIR/moru7probe/` 에 만들고 판정 후 삭제했다 (`git status --short` 에 잔재 없음).

### [확정 · 해소] M — h11 프레임 귀속

수정: 요청을 `asyncio.open_connection` 생 소켓으로 바꾸고, `counts["client"] == 0`
(httpx/httpcore 프레임 0)을 함께 단언하며, `uvicorn.Config(..., http="h11")` 로 서버
파서를 못박았다 (`tests/test_http_socket.py:41,103-123`).

직전 라운드가 **못 돌렸던 양성 대조**(httptools 미설치라 드리프트 서버를 못 만들었다)를
이번에 만들었다 — `uvicorn.config.Config.load` 가 `http` 에 **클래스**를 그대로 받으므로
(`if isinstance(self.http, str): ... else: self.http_protocol_class = self.http`),
h11 을 전혀 안 쓰는 커스텀 `asyncio.Protocol` 을 서버 파서로 꽂고 테스트의 측정 블록을
그대로 복제해 돌렸다:

```
$ poetry run python $TMPDIR/moru7probe/probe_h11_drift.py
[현재 코드 그대로 (http='h11')] protocol=<class 'uvicorn.protocols.http.h11_impl.H11Protocol'>
    resp=b'HTTP/1.1 200 OK' h11=249 client=0 -> 테스트 GREEN
[양성 대조: 서버가 h11 미사용]  protocol=<class '__main__.NoH11Protocol'>
    resp=b'HTTP/1.1 200 OK' h11=0   client=0 -> 테스트 RED

판정: 계측 유효 (진짜 초록 / 드리프트 red)
```

직전 라운드의 결함(“h11 안 쓰는 서버에서도 184 프레임”)이 **0 프레임으로 뒤집혔다.**
클라이언트 가드도 발동을 직접 확인했다(변이 = httpx 로 되돌리기):

```
$ poetry run python $TMPDIR/moru7probe/probe_client_guard.py
변이(httpx 클라이언트): h11=428 client=503 -> 가드 assert counts['client']==0 는 RED (발동)
```

(결정 로그가 적은 “503 프레임”과 실측이 일치한다.) → **해소.** `osv-scanner.toml` 이
h11 을 “덮인다”로 되돌린 서술도 이제 근거를 갖는다.

### [확정 · 해소] A — 고정 임시 DB 경로

수정: `tempfile.mkdtemp(prefix="moru_oracle_")` + `atexit` 로 디렉터리째 정리
(`tests/conftest.py:26-30`), `http_db` 의 시작/끝 `os.remove` 제거.

양성 대조를 **수정 전 트리로 직접** 만들었다 (`git archive d398d47` 로 레포 밖에 풀고
같은 venv 로 동시 2프로세스 3라운드):

```
##### 양성 대조: 수정 전 트리 (고정 파일명) #####
old round 1  A exit=1 (36 passed, 2 errors) | B exit=0 (38 passed)
old round 2  A exit=1 (36 passed, 2 errors) | B exit=0 (38 passed)
old round 3  A exit=0 (38 passed)           | B exit=1 (36 passed, 2 errors)

##### 수정 후 트리 (mkdtemp) #####
new round 1  A exit=0 (38 passed) | B exit=0 (38 passed)
new round 2  A exit=0 (38 passed) | B exit=0 (38 passed)
new round 3  A exit=0 (38 passed) | B exit=0 (38 passed)
```

3/3 재현 → 3/3 클린. 심링크 TOCTOU 표면(병합분)도 `mkdtemp` 의 0700 프로세스 전용
디렉터리로 같은 줄에서 닫혔다 — 다만 공격 재현은 이 머신에서 여전히 불가(§검증하지 못한 것 2).

정리 누수도 확인했다: `--collect-only` 실행 + 소켓 테스트 실행 후 `$TMPDIR/moru_oracle_*`
잔여 **0개**. `atexit` 가 fixture 를 안 쓰는 실행까지 덮는다. 하위 프로세스는 `subprocess.run`
(fork 아님)이라 자식이 부모 디렉터리를 지우는 경로도 없다 (`grep -rn "multiprocessing\|os.fork" tests/` → 없음).
→ **해소.**

### [확정 · 해소] P — 모듈 개명 false red

`COVERED_PACKAGES` 가 동의어 튜플을 받게 바뀌었다(`tests/test_http_env.py:28,46,96-100`).
현재 설치본은 `python-multipart 0.0.9`(모듈 `multipart`)라 개명 시나리오를 실행으로 못
만들지만, tracer 가 보는 것은 `frame.f_code.co_filename` 뿐이므로 합성 프레임으로 잰다:

```
$ poetry run python $TMPDIR/moru7probe/probe_alias.py
현재 코드 (동의어 튜플):
  개명 후 경로 → {'multipart': 3}
  개명 전 경로 → {'multipart': 3}
  무관 경로   → {}            (0 = 오탐 없음)
양성 대조 — 수정 전 코드(단일 이름 'multipart'):
  개명 후 경로 → {}           (= 0, false red 재현)
```

수정 전 코드가 개명 경로에서 0 을 재 `missing` 에 올라간다(=업그레이드하는 순간 red)는
주장이 그대로 재현됐고, 수정 후는 양쪽을 센다. 오탐 방향(무관 패키지 계수)도 0. → **해소.**

### [확정 · minor] Q — 생 소켓 읽기에 타임아웃이 없다 (verifier 신규, 자기 지적도 반박 절차 적용)

`tests/test_http_socket.py:113` `raw = await reader.read()` 는 EOF 까지 무한 대기한다.
`pytest-timeout` 미설치이고 `[tool.pytest.ini_options]` 에 전역 타임아웃이 없다.

반박 시도 → 부분 성공(=등급 하강). “서버가 `Connection: close` 를 안 지킬 리가 없다”가
반박이었고, 실제로 `http="h11"` 을 못박은 지금 그 확률은 낮다. 그러나 **이 오라클의 존재
이유가 “h11 을 올릴 때 돌린다”**라, 파서 동작이 바뀌는 바로 그 순간이 이 경로의 위험 구간이다.
그때 얻는 것이 red 가 아니라 **행(hang)** 이면 오라클이 판정을 못 낸다. 재현:

```
$ poetry run python $TMPDIR/moru7probe/probe_hang.py
read() 가 3초 안에 안 끝났다 -> 현재 테스트 코드는 여기서 무한 대기
(pytest 전역 timeout 없음: pytest_timeout 미설치)
```

깨지는 방향이 “조용한 초록”이 아니라 “멈춤”이고 현재 파서가 고정돼 있으므로 **minor**.

- `[minor] tests/test_http_socket.py:113` — 응답 읽기에 상한이 없어, 서버가 연결을 안 닫는
  상황(h11 업그레이드 회귀 등)에서 테스트가 red 대신 무한 대기한다 (3초 프로브로 재현) —
  `raw = await asyncio.wait_for(reader.read(), timeout=5)` 로 감싼다.

### [확정 · minor · 2라운드째] N — cryptography 음성 대조 표본

`tests/test_http_env.py:119-135` 는 여전히 `/login`(GET) + `/attendee/202601` 두 요청에서만
`counts["cryptography"] == 0` 을 잰다 — 둘 다 JWT 발급/검증도 bcrypt 도 안 탄다. 직전 라운드가
“M 과 같은 계열이니 같은 수정 안에서 닫아라”라고 적었으나 닫히지 않았다.

기각 시도 → 실패(주장 자체는 여전히 참, 감지기만 헛돈다). 직전 라운드가 실제 bcrypt+JWT
트래픽에서 cryptography 0 프레임을 실측했으므로 `osv-scanner.toml` 서술은 사실이다.
결함은 “나중에 RS256 으로 바꿔도 이 테스트가 계속 0 을 보고한다”는 회귀 감지 실패뿐이다.
등급을 올릴 근거(지금 깨지는 것)가 없어 **minor 유지**. 다만 **같은 계열 지적이 2라운드째**
라는 사실은 기록한다 — 다음에 또 나오면 라인 패치가 아니라 “양·음 계측을 같은 트래픽 위에서
잰다”는 구조 변경으로 가야 한다.

- `[minor] tests/test_http_env.py:127-128` — 음성 대조 표본이 주장 범위(JWT·bcrypt 경로)를
  안 포함해 cryptography 회귀를 못 잡는다 — 양성 테스트(`:74-92`)와 같은 요청 시퀀스
  (login POST + 토큰 GET)를 쓰게 통일한다.

### [확정 · minor · 재확인] B — 세션 공유 DB 쓰기 누수

`tests/conftest.py:76-82`(session `http_db`) + `:85`(function `seeded_app`) 구조는 그대로다.
`mkdtemp` 수정은 **프로세스 간** 충돌만 없앴고 **프로세스 내** 누수는 설계가 명시적으로 고른
것이다(§통합 계획). 이번 라운드에 정방향/역순/파일 단독/전체 282 를 다시 돌려 순서 의존이
없음을 재확인했다. → minor 유지.

- `[minor] tests/conftest.py:76` — 세션 스코프 물리 sqlite 를 함수 스코프 앱이 공유해 쓰기가
  테스트 간에 남는다 — 지금은 내용 단언이 없어 무해하나, export 행수·attendee 개수를 단언하는
  테스트가 생기면 순서 의존 오라클이 된다. 그때 함수 스코프 롤백으로 감싸거나 이 제약을
  conftest 에 못박는다.

### [확정 · minor · 재확인] D — 실소켓 서버 2회 기동 / docstring 불일치

`tests/test_http_socket.py:1,8` 이 “**실소켓 스모크 1개** … **유일한** 테스트”, “**하나만 둔다**”
라고 적는데 파일에는 테스트가 2개이고 `live_server` 가 function-scope 라 uvicorn 이 2번 뜬다
(`grep -c "^async def test_" → 2`). `03-design.md:66,103` 도 “실소켓 h11 스모크 1개 / 1개만 둔다”다.
비용은 무시할 만하다(파일 전체 0.70s, 5회 재실행 동일). #9(다음 사람이 읽는 문장이 파일과
어긋난다) 축으로만 minor 유지 — 이번 수정이 이 문장을 건드리지 않았으므로 **직전 라운드와
동일 등급**이다.

- `[minor] tests/test_http_socket.py:1,8,29` — docstring·설계의 “1개/유일한/하나만 둔다”가 실제
  테스트 2개·uvicorn 2회 기동과 어긋난다 — 두 단언을 한 테스트로 합치거나(설계대로 1개),
  `live_server` 를 module-scope 로 올리고 문구를 실제에 맞춘다.

### [확정 · minor · 재확인] O-1 — `dependency_overrides.clear()`

`tests/conftest.py:116` 은 여전히 전량 삭제다. 현재 다른 오버라이드 사용처가 없어 무해
(전체 282 passed 로 재확인). → minor 유지.

- `[minor] tests/conftest.py:116` — 전량 `clear()` 라 다른 테스트가 건 오버라이드까지 지운다 —
  `pop(db.get_db_session, None)` / `pop(get_session, None)` 2회가 더 정확하다.

### [기각 · 등급 하강] O-3 — 프레임 카운터 중복 구현

직전 라운드는 `tests/test_http_env.py::_count_frames` 와 소켓 테스트의 인라인 tracer 를
중복(#4 재사용)으로 봤다. 이번 수정 뒤 두 계측기는 **하는 일이 달라졌다** — env 쪽은 동의어
튜플을 다루는 다중 패키지 카운터이고, 소켓 쪽은 “h11 이냐 / 클라이언트 라이브러리냐”를 가르는
`elif` 분기(귀속 판별)다. 한쪽으로 합치면 후자를 위해 전자에 분기 파라미터를 넣어야 해서
**요구에 없는 유연성**(체크리스트 #5)이 늘어난다. 둘 다 10줄 미만이다. → 중복 finding 기각,
현행 유지가 더 싸다.

### [기각 · 재확인] 직전 라운드의 기각 판정들 (C·F·G·E·H·I·J·K·L)

델타가 이 판정들의 전제를 건드리지 않았다: 앱 코드 무수정(C·H·L), 픽스처 구조 미변경(F·G),
`_free_port()` 미변경(I), env 미복원 구조 미변경(J — 전체 282 passed 로 회귀 0 재확인),
만료 토큰 계산 미변경(K), `ztmp_probe_test.py` 부재 재확인(E: `git status --short` 에 없음).
→ 기각 유지.

### [필수] authz 프로브 — 무토큰 + 타인 자격

diff 에 신규/변경 엔드포인트가 없지만(앱 무수정) §1-1 의 **상시 실행** 규정대로 다시 돌렸다.
인증 필수 6라우트(GET 3 + POST 3) × 자격 6종:

```
$ poetry run python $TMPDIR/moru7probe/probe_authz.py
no-token   -> [307]  거부아닌것=none
forged     -> [307]  거부아닌것=none
expired    -> [307]  거부아닌것=none
garbage    -> [307]  거부아닌것=none
empty      -> [307]  거부아닌것=none
AUTHZ VIOLATIONS: NONE (307 = /login 리다이렉트 거부)
```

307 은 401/403/404 가 아니지만 **거부**다 — `app/main.py:49-51` 의 401 핸들러가
`RedirectResponse('/login')` 으로 바꾼 현행 동작이고(R-1), 보호 리소스가 바디에 실리지
않음을 길이로 확인했다.

**타인 자격**(= DB 에 없는 사용자명으로 서명한 유효 토큰)은 직전 라운드와 동일하게 통과한다:

```
other-user(mallory) GET /admin/attendee              -> 200 (51042B)
other-user(mallory) GET /admin/attendee/202601       -> 200 (49517B)
other-user(mallory) GET /admin/attendee/export/202601 -> 200 (5694B)
POST /admin/attendee 도 인증을 통과해 DAO 까지 도달 (빈 바디라 DB 제약에서 500)
```

`app/util/auth.py:40-46 get_current_user` 가 토큰을 디코드만 하고 `KY_USER_L` 조회를 안 한다.
**이 diff 의 결함은 아니다** — 앱 무수정이고, 토큰은 `SECRET_SALT` 를 알아야 만들 수 있으며
발급 경로는 비밀번호를 검증하는 로그인뿐이라 권한 상승·IDOR 이 아니다. 실질 의미는 **토큰
폐기 수단이 없다**(사용자를 지워도 발급된 토큰은 만료까지 산다)는 것이고, 앱 후속 과제로 남긴다.

---

## Finder 원출력

이 라운드는 §4-1 **델타 재리뷰**라 finder 3명을 재실행하지 않았다. 아래는 **직전 라운드
(2026-08-02)** 렌즈 산출물의 finding 목록을 파일 경로와 함께 옮긴 것이다 — 원문은 각 파일이
소유한다.

### spec-일치 — `.agents/context/artifacts/http-auth-oracle/07-finder-spec.md`

- [낮음] `tests/ztmp_probe_test.py`(untracked) — 설계 § 통합 계획 파일 목록에 없는 파일이
  LOCK 대상 `tests/` 에 존재. 다른 finder 의 프로브 잔재로 보임.
- [낮음] `tests/test_http_socket.py` 전체 — 설계가 “실소켓은 1개만 둔다”인데 function-scope
  `live_server` 를 쓰는 테스트가 2개라 uvicorn 기동이 2회다.
- [중간] `tests/conftest.py:76-107 seeded_app` — 설계는 `seeded_admin(session)` + `client(function)`
  **별도 픽스처**인데 실제는 하나의 function-scope `seeded_app` 으로 합쳤다.
- [낮음] `tests/conftest.py` / `tests/test_http_auth.py` — 설계의 `tokens(valid/expired/forged)`
  fixture 가 `valid_token` fixture 1개 + 모듈 레벨 일반 함수 2개로 구현됐다.
- 지적 없음으로 명시 확인한 것: FR-1~FR-6·AC-1~AC-9 누락 없음, 기능 1~11 누락 없음,
  가정 A-1~A-10 불일치 없음, `app/`·`pyproject.toml` 변경 0건, 라우트 표 일치,
  `osv-scanner.toml` “40개” = `--collect-only` 실측 일치, 40 passed.

### correctness — `.agents/context/artifacts/http-auth-oracle/07-finder-correctness.md`

- [높음] `tests/conftest.py:70` fixture 스코프 불일치 — session `http_db` 위에 function
  `seeded_app` 이라 한 프로세스 안 모든 테스트가 같은 물리 sqlite 를 공유, 쓰기가 샌다
  (레포 밖 스크립트로 export 길이 5695→5732 변화 관측). 지금 깨지는 테스트는 없음.
- [높음] `tests/conftest.py:16` 고정 임시 DB 파일 경로 — 동시 2프로세스에서
  `table "KY_ATDC_L" already exists` 재현. 리뷰 세션 중 실제 동시 실행이 관측됐다는 방증 포함.
- [중간] `tests/test_http_socket.py:29` 실소켓 스모크가 설계 의도(“하나만 둔다”)와 달리 2개
  테스트가 각각 uvicorn 을 띄운다 (`--durations` 실측 setup 0.27s + teardown 0.18/0.17s).
- [낮음] `tests/conftest.py:34` `os.environ.update()` 미복원 — 설계 D-3 이 고른 구조, 회귀 0 재확인.
- [낮음] `tests/test_http_socket.py:22` `_free_port()` ↔ uvicorn 바인드 TOCTOU (추론, 재현 안 됨).
- [낮음] `tests/test_http_auth.py:83` 만료 토큰 collection-time 계산 — 확인 결과 버그 아님(자체 하강).
- [정보] 단언 정확성 표본 점검 — 401 핸들러 307, 오버라이드 키 2개 전수, `/agent/*` 200+error 전부 일치.
- 검증하지 못한 것: pytest-xdist 워커 병렬 거동, CI 매트릭스에서의 실제 충돌 빈도.

### security + 규칙 — `.agents/context/artifacts/http-auth-oracle/07-finder-security.md`

- [낮음] `tests/conftest.py:20` 고정 `/tmp` 경로 — 공유 `/tmp` 리눅스에서 심링크 TOCTOU 클래스.
  제안: `tempfile.mkdtemp(prefix="moru_oracle_")`.
- [높음] `/docs`·`/openapi.json`·`/redoc` 무인증 200(실행 확인) — 오라클의 라우트 목록 어디에도 없다.
- [중간] R-5 “토큰=관리자”가 데이터 불변식에 기대는데 음성 테스트가 없다(지금은 작성 불가).
- [높음·확인됨] mass assignment 해당 없음 — `POST /admin/attendee` 는 `.get()` 3필드만 뽑는다(프로브).
- [높음·확인됨] IDOR 해당 없음 — 역할·소유자 컬럼 부재, `cal_date` 는 리소스 ID 가 아니라 달력 월.
- [낮음·확인됨] 잘못된 `cal_date` → 500 이지만 바디는 `Internal Server Error` 뿐(정보 누출 없음).
- [중간·확인됨] 사용자 열거 없음 — 없는 사용자/틀린 비번 모두 동일 401→307.
- [낮음] `TEST_ENV` 시크릿 더미 값, 커밋된 실 시크릿 없음.
- [낮음] LLM 키 빈 문자열 강제 + 가드 테스트 — 방어 구조 적절.
- [낮음] 실소켓 서버 `127.0.0.1` + 커널 배정 포트 — 외부 노출 없음.
- [정보] `/agent/confirm` 의 `kwargs` 파라미터 인젝션은 tool 레지스트리 내부까지 안 봤다.
- 엔드포인트별 ①~④ 순회표 포함(원문 참조). 숨은 결합 추가 발견: 없음.

### 심층 적대 렌즈

**비게이트 — 미실행** (`03-design.md` 게이트 판정). §1-1 의 “비게이트·사소 변경엔 생략” 규정대로다.

---

## 체크리스트 #6 테스트 품질 · #9 유지보수

렌즈 배정이 없어 verifier 가 직접 커버한다 (델타 범위 + 델타가 바꾼 단언).

### #6 테스트 품질

- **약화된 단언 스윕(델타)**: 이번 델타는 단언을 **강화**했다 — 소켓 테스트에
  `raw.startswith(b"HTTP/1.1 200")` 과 `counts["client"] == 0` 이 새로 생겼고, 둘 다 변이에서
  red 가 나는 것을 실행으로 확인했다(위 M). 삭제된 단언은 `len(res.content) > 0` 하나이고
  앞줄 `res.content[:2] == b"PK"` 에 함의되므로 커버리지 손실 0.
- **완화 방향 점검**: `COVERED_PACKAGES` 의 동의어 튜플은 매칭을 **넓히는** 변경이라 “느슨해진
  것 아닌가”를 따로 쟀다 — 무관 패키지 경로에서 계수 0(위 P 프로브)이라 오탐 통로가 아니다.
  넓힌 대상이 같은 배포판의 개명 전/후 두 이름뿐이다.
- **양성/음성 짝 유지**: `test_known_uncovered_packages_stay_uncovered[h11]`(ASGI 0) ↔
  `test_real_socket_path_executes_h11_in_the_server`(실소켓 >0) 짝이 그대로다. 이제 후자가
  서버를 재므로 짝의 의미가 처음으로 성립한다.
- **결정성**: 소켓 파일 5회 연속 동일, 파일 역순 40 passed, 전체 282 passed. flaky 징후 없음.
- **남은 약점**: N(음성 대조 표본)과 Q(무한 대기) — 위 finding.

### #9 유지보수

- 델타의 주석이 “왜”를 소유한다: `mkdtemp` 주석이 실측 재현(3/3)을, `http="h11"` 주석이 우연
  배제 이유를, 소켓 docstring 이 **틀렸던 이력과 무엇이 왜 바뀌었는지**를 적는다. 다음 사람이
  이 계측기를 되돌리지 않게 막는 자산이다.
- `_count_frames` 의 동의어 처리(`(p[0], tuple(p)) if isinstance(p, tuple) else (p, (p,))`)와
  `missing` 계산의 삼항 2회는 읽기 부담이 있으나 함수가 짧고 docstring 이 규칙을 한 줄로
  적어 이해 가능하다. 취향 지적 범위라 finding 으로 세우지 않는다.
- **유일한 #9 결함은 D** — 파일 docstring 과 설계의 “1개/유일한/하나만 둔다”가 실제 2개와
  어긋난 채 두 라운드째 남아 있다.
- 프로세스 관측(코드 결함 아님, 기록만): `.agents/context/locks/http-auth-oracle.lock` 이
  **이 재리뷰 이전에** 삭제되고 PR 이 열렸다. 결정 로그가 “7단계 렌즈·verifier 를 다시 돌리지는
  않았다”고 스스로 적어 두었고 이번 라운드가 그 공백을 메운다. `TEST_LOCK_OVERRIDE=1` 사용도
  사람 승인과 함께 결정 로그에 기록돼 있어 §4 라우팅(테스트 품질 finding → 사람 승인 →
  4단계 수정)과 어긋나지 않는다.

---

## 검증하지 못한 것

1. **실제 `httptools` 설치 환경은 여전히 미확인.** 드리프트 양성 대조는 커스텀 프로토콜
   클래스로 대신했다 — h11 을 안 쓰는 서버에서 계측이 0 이 되는 것은 증명했지만,
   `uvicorn[standard]` 를 실제로 깐 환경에서의 거동은 안 봤다. 다만 `http="h11"` 고정으로
   그 경로 자체가 닫혔다.
2. **공유 `/tmp` 심링크 TOCTOU 는 재현하지 않았다.** macOS 는 `$TMPDIR` 가 사용자별이라 공격
   조건을 못 만든다 — `mkdtemp` 가 그 클래스를 없앤다는 판단은 **추론 판정**이다.
3. **pytest-xdist 워커 병렬은 미확인.** 동시성은 별도 프로세스 2개로만 쟀다(xdist 미설치).
   워커가 같은 프로세스 트리에서 `conftest` 를 어떻게 로드하는지에 따라 결과가 다를 수 있다.
4. **`atexit` 가 안 도는 종료(SIGKILL, `os._exit`)에서는 임시 디렉터리가 남는다.** 실행으로
   확인하지 않았다 — 코드 형태로만 판단했고, 남아도 빈 sqlite 하나라 무해로 봤다.
5. **R-5 “토큰=관리자” 데이터 불변식은 여전히 테스트로 지켜지지 않는다.** 비관리자 행을 만드는
   라우트가 앱에 없어 음성 테스트를 쓸 수 없다. 가입·초대 기능이 생기면 이 오라클은 회귀를 못 잡는다.
6. **토큰 폐기(revocation) 부재는 이 리뷰가 판정하지 않았다.** DB 에 없는 사용자로 서명한 유효
   토큰이 200 을 받는 것은 실행으로 확인했다(위 authz 프로브). 앱 설계 판단이라 사람 몫이다.
7. **`/docs`·`/openapi.json`·`/redoc` 무인증 200 의 실질 위험도는 판정하지 않았다.** 직전 라운드에서
   기각(오라클 범위 밖 + 테스트로 200 을 고정하면 나중에 닫는 것을 막는다)했고 이번 델타가
   그 전제를 바꾸지 않았다. 프로덕션에서 닫을지는 사람 판단.
8. **의존성을 실제로 올려 보지 않았다.** 이 오라클의 최종 증명은 “h11·jinja2 를 올렸을 때 red/green
   이 의미를 갖는가”인데 이번 리뷰도 현재 버전에서의 커버리지만 쟀다. `osv-scanner.toml` 해소 순서
   2단계(업그레이드)는 아직 아무도 실행하지 않았다.
9. **`python-multipart` 개명 시나리오는 합성 프레임으로만 쟀다.** 실제 0.0.12+ 를 설치해 돌리지
   않았다(의존성 변경 금지 C-2). 또한 동의어 매칭은 **다른 배포판이 같은 `multipart` 모듈명을
   쓰는 경우**(PyPI `multipart` vs `python-multipart` 충돌)를 구분하지 못한다 — 락파일에 없어
   실현 경로가 없다고 보고 finding 으로 세우지 않았다.
10. **`function_calling_deck.html`** 이 레포 루트에 untracked 로 남아 있다(커밋에서는 빠졌다).
    이번 기능 산출물이 아니어서 리뷰 대상에서 제외했다 — 삭제·보관은 사람이 판단한다.
11. **`.agents/context/artifacts/http-auth-oracle/06-verification.md` 가 untracked 다.** 6단계
    산출물이 커밋되지 않은 상태라 이 리뷰는 워킹트리 사본을 읽었다.

---

## 숨은 결합 발견

새로 발견한 것 **없음**. 직전 라운드가 올린 “프레임 계측 ↔ 요청을 보내는 클라이언트 자신”
항목이 `.agents/context/codebase-conventions.md:78` 에 등재돼 있음을 확인했다. 그 서술은
**결합 자체**(같은 스레드에 서버와 클라이언트가 있으면 프레임이 섞인다)를 소유하므로 수정
이후에도 유효하다 — 이번 수정은 그 결합을 없앤 것이 아니라 클라이언트 쪽에서 h11 을
제거해 **피한** 것이기 때문이다.

---

## 판정

PASS

근거: 직전 라운드의 major 2건(M·A)이 **양성 대조를 갖춘 프로브로 해소 확인**됐고, 게이트
라운드에서 추가된 수정(P)도 같은 방식으로 확인됐다. 이번 델타가 만든 새 결함은 Q 하나이며
minor 다. 남은 것은 minor 6건(Q·N·B·D·O-1 + 프로세스 관측)뿐이라 §4 라우팅상
**“minor 만 있음 → 결정 로그에 기록 후 통과”**에 해당한다. `03-design.md` 가 비게이트라
§1-1 3번에 따라 2차 verifier 없이 1차 PASS 로 확정한다.

통과 조건으로 결정 로그에 남길 minor (수정 강제 아님, 기록이 처리다):

1. `[minor] tests/test_http_socket.py:113` — 응답 읽기 무한 대기 →
   `asyncio.wait_for(reader.read(), timeout=5)`.
2. `[minor] tests/test_http_env.py:127-128` — cryptography 음성 대조 표본이 주장 범위 밖
   (**2라운드째**). 다음에 또 나오면 라인 패치 금지 — 양·음 계측을 같은 트래픽 위에서 재는
   구조로 바꾼다.
3. `[minor] tests/test_http_socket.py:1,8,29` — docstring·설계의 “1개/유일한”이 실제 2개와 어긋남.
4. `[minor] tests/conftest.py:76` — 세션 공유 sqlite 쓰기 누수 (내용 단언이 생기는 순간 순서 의존).
5. `[minor] tests/conftest.py:116` — `dependency_overrides.clear()` 전량 삭제 → `pop` 2회.

사람 판정이 필요한 것(리뷰어가 결정하지 않음, 전부 **앱 후속 과제** — 이번 diff 에서 건드리지 말 것):
- 토큰 폐기(revocation) 부재 — DB 에 없는 사용자로 서명한 유효 토큰이 관리자 권한을 얻는다.
- `/docs`·`/openapi.json`·`/redoc` 을 프로덕션에서 닫을지.
- 잘못된 `cal_date` → 500 (정보 누출은 없음).

### 종료 조건

- [x] §4-1 델타 재리뷰 — 풀 재리뷰 승격 조건 미해당을 근거와 함께 판정 (앱 공유 코드 무수정,
      conftest 파급은 전체 스위트 282 passed 로 대체 확인)
- [x] 직전 major 2건이 실제로 해소됐는지 **프로브로** 확인 (둘 다 양성 대조 통과)
- [x] 리팩토링이 새로 만든 문제 탐색 — 신규 후보 1건(Q), minor 로 확정
- [x] verifier 자신이 추가한 finding(Q)도 동일한 반박 절차를 거쳐 기록
- [x] 필수 authz 프로브 실행 (무토큰 + 타인 자격, 앱 무수정이지만 상시 규정대로)
- [x] 운영 가시성(#8) — 설계 §3-2 N/A (런타임 표면 없음)
- [x] 체크리스트 #6·#9 를 verifier 가 직접 커버
- [x] Finder 원출력 섹션 첨부 (직전 라운드 3렌즈 + 심층 적대 미실행 사유)
- [x] “검증하지 못한 것” 작성 (11건)
- [x] “숨은 결합 발견” 작성 (없음 — 기존 1건 유효성 재확인)
- [x] 프로브 파일 전량 삭제 (`$TMPDIR/moru7probe` 제거, `git status --short` 잔재 없음)
- [x] blocker/major 없음
