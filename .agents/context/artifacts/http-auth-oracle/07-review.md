# [7단계] 리뷰 산출물 — verifier 겸 judge (http-auth-oracle)

역할: `.agents/07-review.md` §1-1 2번 (verifier 겸 judge). finder 3개 렌즈 산출물을
중복 제거 후 적대적으로 반박 검증하고, 실행 가능한 후보는 **프로브로만** 판정했다.
체크리스트 **#6(테스트 품질)·#9(유지보수)** 는 렌즈 배정이 없어 내가 직접 봤다.

- 대상: `tests/conftest.py`(수정) + `tests/test_http_{auth,pages,agent,env,socket}.py`(신규)
  + `osv-scanner.toml`(머리말) + `.agents/context/codebase-conventions.md`(§숨은 결합).
  **앱 코드 변경 0건** (`git diff --stat -- app/` 공백 재확인).
- 게이트 판정: `03-design.md` 가 **비게이트** — 심층 적대 렌즈 미실행, 2차 verifier 미적용.
- 성격: 기능 테스트 스위트가 아니라 **의존성 업그레이드 오라클**. "이 라우트의 로직을
  더 깊이 검증하라"는 범위 밖으로 처리했고, "덮는다고 주장하는데 실제로 안 덮는다"만
  범위 안으로 봤다.
- 베이스라인: `GROQ_API_KEY="" GEMINI_API_KEY="" poetry run pytest tests/test_http_*.py -q`
  → **40 passed in 1.58s**. 전체 스위트 `poetry run pytest -q` → **282 passed in 168.77s**
  (느린 168초는 전부 기존 `tests/harness/*` — 이 diff 무관).

---

## 중복 제거 후 finding

| # | 계열 | 출처 렌즈 | 원 확신도 |
|---|---|---|---|
| A | 고정 임시 DB 경로 (`/tmp` 고정 파일명) — 동시 실행 충돌 + `/tmp` 심볼릭 링크 TOCTOU | correctness [높음] + security [낮음] (**같은 라인·같은 원인 → 1건으로 병합**) | 높음 |
| B | fixture 스코프 누수 — 세션 내내 물리 sqlite 1개를 공유해 테스트 간 쓰기가 샌다 | correctness [높음] | 높음 |
| C | `/docs`·`/openapi.json`·`/redoc` 무토큰 200 을 오라클이 안 본다 | security [높음] | 높음 |
| D | 실소켓 테스트가 2개라 uvicorn 을 2번 띄운다 (설계는 "1개만 둔다") | spec [낮음] + correctness [중간] (**병합**) | 중간 |
| E | `tests/ztmp_probe_test.py` 가 LOCK 대상 `tests/` 에 남아 있다 | spec [낮음] | 낮음 |
| F | `seeded_app` 이 설계의 `seeded_admin`+`client` 두 픽스처를 하나로 합쳤다 | spec [중간] | 중간 |
| G | `tokens(valid/expired/forged)` 픽스처가 fixture 가 아니라 모듈 함수로 구현됐다 | spec [낮음] | 낮음 |
| H | R-5 "토큰=관리자" 데이터 불변식의 음성 테스트가 없다 | security [중간] | 중간 |
| I | `_free_port()` ↔ uvicorn 바인드 TOCTOU | correctness [낮음] | 낮음 |
| J | `os.environ.update()` 를 되돌리지 않는다 | correctness [낮음] | 낮음 |
| K | 만료 토큰의 collection-time 계산 | correctness [낮음] (자체 하강) | 낮음 |
| L | 잘못된 `cal_date` → 500 / mass assignment 없음 / IDOR 없음 / 사용자 열거 없음 | security [정보·확인됨] | — |

**verifier 가 추가한 후보** (finder 미발견, 동일한 반박 절차 적용):

| # | 계열 | 근거 |
|---|---|---|
| M | `test_real_socket_path_executes_h11` 이 세는 h11 프레임이 **서버가 아니라 httpx 클라이언트**의 것이다 — h11 커버리지 주장이 측정으로 뒷받침되지 않는다 | #6 테스트 품질 |
| N | `test_known_uncovered_packages_stay_uncovered[cryptography]` 가 **JWT·bcrypt 를 안 타는 트래픽**에서 0 을 재서, 주장 범위와 표본이 다르다 | #6 테스트 품질 |
| O | `dependency_overrides.clear()` 가 전량 삭제 / `len(res.content) > 0` 중복 단언 / 프레임 카운터 헬퍼 중복 구현 | #4 재사용 · #9 유지보수 |

---

## 반박 검증

### [확정 · major] M — 실소켓 h11 프레임이 서버 것이 아니다
`tests/test_http_socket.py:72-98`. docstring 은 "이 경로가 정말 h11 을 태우는지
프레임으로 확인한다"고 적는데, 계측 스레드에는 uvicorn 서버와 **httpx 클라이언트가
같이** 있다. httpx/httpcore 는 클라이언트 측 HTTP/1.1 파싱에 h11 을 쓴다.

반박 시도 → 실패. **h11 을 전혀 안 쓰는 생 asyncio TCP 서버**에 같은 방식으로 요청해
프레임을 셌다:

```
$ python probe_h11_attrib.py     # $TMPDIR, 판정 후 삭제
바닐라 asyncio 서버(h11 전혀 미사용) 응답: 200 {'200': 'ok'}
그럼에도 관측된 h11 프레임: 184
→ 단언 `counts["h11"] > 0` 은 통과한다 (서버 무관)
```

즉 `assert counts["h11"] > 0` 은 서버가 h11 을 0 프레임 실행해도 초록이다.
현재는 우연히 참이다 — `httptools` 미설치라 `uvicorn.Config(http="auto")` 가 h11 로
떨어진다(실측 `protocol=uvicorn.protocols.http.h11_impl`). 그러나 누군가
`uvicorn[standard]` 를 깔면 서버는 httptools 로 바뀌고 **이 테스트는 그대로 초록**이다.
`osv-scanner.toml` 머리말이 "덮인다 h11 — `tests/test_http_socket.py` 가 이쪽을 맡는다"를
**사실로 박아 두었으므로**, 그때 h11 0.16.0 업그레이드 판단이 검증되지 않은 초록 위에서
내려진다. D-5("커버리지를 프레임으로 잰다 — 산문 주장은 못 믿는다")가 막으려던 바로 그
실패 유형이 계측 안쪽에서 재발한 것이다.

제안 수정도 실행으로 확인했다 — 생 소켓 클라이언트(h11 미경유)로 바꾸면 관측 프레임이
전부 서버 것이 된다:
```
[uvicorn 기본(auto) — 생 소켓 클라이언트] protocol=uvicorn.protocols.http.h11_impl
   resp=b'HTTP/1.1 200 OK' h11frames=215
```
(양성 대조 `http="httptools"` 강제는 **미설치로 실행 불가** — 미확인으로 아래 §검증하지
못한 것에 남긴다.)

- `[major] tests/test_http_socket.py:96` — h11 프레임 단언이 서버가 아닌 httpx 클라이언트의
  h11 도 세므로, 서버가 h11 을 안 써도 초록이다 (생 asyncio 서버에서 184 프레임 실측) —
  `asyncio.open_connection` 으로 생 HTTP 바이트를 보내 클라이언트 측 h11 을 배제하고,
  `uvicorn.Config(..., http="h11")` 로 서버 파서를 못박는다 (둘 다 하면 드리프트까지 닫힌다).

### [확정 · major] A — 고정 임시 DB 경로
`tests/conftest.py:20` `_DB_FILE = os.path.join(tempfile.gettempdir(), "moru_oracle_test.db")`.
PID/난수 접미사가 없어 같은 사용자의 모든 체크아웃·브랜치·에이전트가 같은 파일을 쓴다.
`tests/conftest.py:66-73` `http_db`(session) 가 세션 시작에 그 파일을 `os.remove` 한다.

반박 시도 → 실패. 동시 2 프로세스로 3회 반복, **3/3 재현**:
```
$ pytest tests/test_http_{auth,pages,env,agent}.py -q  (A) & 동일 명령 (B) &
=== round 1 ===  A exit=0 : 38 passed        B exit=1 : 36 passed, 2 errors
=== round 2 ===  A exit=0 : 38 passed        B exit=1 : 36 passed, 2 errors
=== round 3 ===  A exit=0 : 38 passed        B exit=1 : 36 passed, 2 errors

E sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) table "KY_ATDC_L" already exists
E sqlalchemy.exc.IntegrityError: UNIQUE constraint failed: KY_USER_L.USER_ID
```
"가정된 동시성"이 아니다 — 이 리뷰 라운드 동안 렌즈 finder 들이 같은 워킹트리에서
동시에 스위트를 돌린 것이 관측됐다(finding E 참조: 한 finder 의 임시 파일이 다른
finder 의 실행 로그에 나타났다). 즉 이 파이프라인 자체가 충돌 조건을 만든다.

파급 방향은 **false red**(loud error, exit 1)라 조용한 통과는 아니다. 그럼에도 major 로
두는 근거: 이 오라클의 존재 이유가 "의존성 올릴 때마다 자주 돌린다"인데, 자주 도는
환경일수록 동시 실행 확률이 올라간다. 설계 스스로 "자주 안 도는 오라클은 오라클이
아니다"라고 적었고, 이 결함은 그 빈도를 직접 깎는다.

security 렌즈의 `/tmp` 심볼릭 링크 TOCTOU 는 **같은 라인·같은 원인**이라 병합했다.
프로브는 안 돌렸다(공유 `/tmp` 다중 사용자 환경 재현은 이 머신에서 불가 — macOS 는
`$TMPDIR` 가 사용자별). 별도 finding 으로 세지 않는 이유는 아래 한 줄 수정이 두 계열을
동시에 지우기 때문이다.

- `[major] tests/conftest.py:20` — 고정 임시 파일명이라 같은 사용자의 두 pytest 프로세스가
  서로의 DB 를 지운다 (동시 2프로세스 3/3 재현, `table "KY_ATDC_L" already exists`) —
  `tempfile.mkdtemp(prefix="moru_oracle_")` 하위에 파일을 두고 `http_db` teardown 에서
  디렉터리째 지운다 (다중 사용자 `/tmp` 심볼릭 링크 TOCTOU 도 같은 줄에서 닫힌다).

### [확정 · minor] N — cryptography 음성 대조의 표본이 주장 범위와 다르다
`tests/test_http_env.py:98-125` 는 `/login`(GET) 과 `/attendee/202601` 두 요청만 때리고
`counts["cryptography"] == 0` 을 단언한다. 두 경로 모두 **JWT 발급/검증도 bcrypt 도 안 탄다** —
주장("이 앱에 cryptography 실행 경로가 없다. HS256=stdlib `hmac`, 비번=`bcrypt` 패키지")이
가리키는 코드가 표본에 아예 없다.

주장 자체는 참인지 프로브로 확인했다 — 실제 bcrypt+JWT 트래픽에서도 0이다:
```
login=200 admin=200  프레임: {'bcrypt': 1, 'jwt': 19}
→ 실제 bcrypt/JWT 경로에서 cryptography 프레임 = 0
```
따라서 `osv-scanner.toml` 머리말의 서술은 **사실이다**. 결함은 주장이 아니라 그 주장을
지키는 회귀 감지기가 헛돈다는 것 — 나중에 RS256 으로 바꿔도 이 테스트는 계속 0 을 보고한다.

M 과 **같은 계열**이다: 둘 다 "프레임 계측의 귀속·표본이 주장 범위와 어긋난다".
`AGENTS.md` § 리뷰-수정 루프 상한 규칙 4 대로, 라인 패치 2개가 아니라 계열을 없애는
한 가지 구조로 제안한다 — **양·음 계측을 같은 트래픽 위에서, 클라이언트 측 프레임을
배제한 채 잰다.**

- `[minor] tests/test_http_env.py:117-118` — 음성 대조가 JWT·bcrypt 를 안 타는 요청 2개에서만
  0 을 재서 cryptography 주장의 회귀를 못 잡는다 — 양성 테스트(`:73-86`)와 **같은 요청
  시퀀스**(login POST + 토큰 GET)를 쓰게 통일한다.

### [확정 · minor] B — 세션 공유 DB 로 테스트 간 쓰기가 샌다
`tests/conftest.py:66`(session `http_db`) 위에 `:77`(function `seeded_app`)이 얹혀,
한 pytest 프로세스 안에서 모든 테스트가 같은 물리 sqlite 를 공유한다.
레포 밖 pytest 플러그인(`pytest_runtest_teardown` 에서 파일을 read-only 로 열어 행 수 출력)으로
누수를 직접 관측했다:
```
[LEAK] after test_write_route_accepts_a_valid_token: KY_ATDC_L rows = 2
[LEAK] after test_login_page_renders_html:           KY_ATDC_L rows = 2
[LEAK] after test_excel_export_streams_a_workbook:   KY_ATDC_L rows = 2
```
누수는 실재한다. **그러나 지금 깨지는 것은 없다** — 순서 의존을 반박 방향으로 검증했다:
```
정방향 40 passed / 역순 40 passed / 파일 단독 23·6·5·4·2 전부 passed / 전체 282 passed
```
양성 대조 대신 기전으로 확인: `app/dao/functions.py:37-41 save_attendees` 가
delete-then-insert 라 반복 실행이 멱등이고, 내용/행수를 단언하는 테스트가 하나도 없다.
설계도 세션 스코프 DB 를 명시적으로 골랐다(§통합 계획 `_engine(session)`) — **설계 위반이
아니다.** 잠재 함정이므로 minor 로 확정하고 후속.

- `[minor] tests/conftest.py:66` — 세션 스코프 물리 sqlite 를 함수 스코프 앱이 공유해
  쓰기가 테스트 간에 남는다(행 수 실측). 지금은 내용 단언이 없어 무해하나, 나중에 export
  행수·attendee 개수를 단언하면 실행 순서 의존 오라클이 된다 — 그때 함수 스코프 트랜잭션
  롤백으로 감싸거나, 최소한 conftest 에 이 제약을 주석으로 못박는다.

### [확정 · minor] D — 실소켓 서버가 2번 뜬다 / docstring 이 사실과 다르다
`tests/test_http_socket.py:1` 파일 docstring 은 "**실소켓 스모크 1개** — h11 을 실제로
태우는 **유일한** 테스트"라고 적지만 실제로는 테스트가 2개고 `live_server` 가
function-scope 라 uvicorn 이 2번 뜬다. 비용은 무시할 만하다(총 ~0.5s, 실측 setup 0.27s
+ teardown 0.18s/0.17s). 자원 낭비로는 기각하고, **다음 사람이 읽는 문장이 파일 내용과
어긋난다**는 #9 축으로만 minor 확정. M 을 고칠 때 `live_server` 를 module-scope 로
올리면 서술과 구현이 동시에 맞는다.

- `[minor] tests/test_http_socket.py:1,29` — docstring 의 "1개/유일한"이 실제 2개 테스트·
  uvicorn 2회 기동과 어긋난다 — `live_server` 를 module-scope 로 올리고 문구를 맞춘다.

### [확정 · minor] O — 잔재 3건
- `[minor] tests/conftest.py:107` — `dependency_overrides.clear()` 가 **전량** 삭제라, 다른
  테스트가 자기 오버라이드를 걸어 두면 같이 지워진다 — 현재 사용처가 없어 무해하나
  `pop(key, None)` 2회가 더 정확하다.
- `[minor] tests/test_http_pages.py:61` — `assert res.content[:2] == b"PK"` 뒤의
  `assert len(res.content) > 0` 은 앞 단언에 이미 함의된다 — 삭제.
- `[minor] tests/test_http_socket.py:78-87` — `tests/test_http_env.py:39 _count_frames` 와
  같은 프레임 카운터를 인라인으로 다시 구현했다(체크리스트 #4) — M 수정 시 한쪽으로 모은다.

### [기각] C — `/docs`·`/openapi.json`·`/redoc` 을 오라클이 안 본다
노출 자체는 실행으로 재확인했다: 무토큰 `GET /docs` → **200 (939B)**,
`/openapi.json` → **200 (6082B)**, `/redoc` → **200 (891B)**.

기각 근거 3가지:
1. **주장의 전제가 거짓이다.** finder 는 "오라클이 *인증 걸린 라우트 전수*를 자처한다"고
   했지만, `tests/test_http_auth.py:16-24` 는 2단계 라우트 표(= `app/controller/router.py` 에
   등록된 앱 라우트)에서 뽑은 목록이라고 명시한다. `/docs`·`/openapi.json`·`/redoc` 는
   FastAPI 내장 자동 라우트이고 **인증이 걸려 있지 않다** — "인증 필수 라우트"에 애초에
   속하지 않으므로 목록 누락이 아니다. `PUBLIC_GET_ROUTES` 도 전수를 자처하지 않는다.
2. **이 diff 의 결함이 아니다.** 노출한 것은 앱 코드이고 이번 변경은 `app/` 무수정(C-1)이다.
3. **테스트로 고정하는 것이 오히려 해롭다.** 이 오라클의 목적은 업그레이드를 **막지 않는**
   것이다(A-10 이 프레임 수를 하한만 재는 이유와 같다). `/docs` 200 을 단언으로 박으면
   나중에 `FastAPI(docs_url=None)` 로 닫을 때 이 테스트가 red 로 그것을 막는다 —
   같은 브랜치가 `/admin/attendee/export`(무날짜) 건에서 이미 겪은 함정이다.

→ 이번 diff 의 finding 아님. **앱 후속 과제**로만 남긴다: 프로덕션에서 `/docs`·`/redoc`·
`/openapi.json` 을 닫을지 사람이 판단한다(내부 도구라 실질 위험도는 사람 판단 영역).

### [기각] F, G — 설계의 픽스처 구조와 다르게 구현됐다
설계 §통합 계획이 `seeded_admin(session)` / `client(function)` / `tokens(function)` 세
픽스처를 적었는데 실제는 `seeded_app`(function) 하나 + `valid_token` + 모듈 함수 2개다.

기각 근거: 설계가 `seeded_admin` 을 **세션 스코프로 분리한 이유가 "bcrypt 는 비싸다"** 라고
명시돼 있다(§통합 계획 주석). 그 목적이 달성됐는지를 런타임으로 확인했다 — 40 테스트가
**1.58s** 에 끝난다. bcrypt cost 12 해시가 테스트마다 돌면 40 × ~0.25s ≈ 10s 여야 한다.
`tests/conftest.py:82 if existing is None` 가드 + 세션 지속 DB 조합으로 해시는 세션당 1회다.
설계 의도가 충족됐고 기능도 동등하므로 구조 차이만으로 finding 을 세우지 않는다
(§Rules "취향 지적 금지"). G 도 같다 — fixture 냐 모듈 함수냐는 커버리지에 영향이 없고,
`04-test-audit.md` 가 AC-4 커버를 이미 확인했다.

### [기각] E — `tests/ztmp_probe_test.py`
현재 존재하지 않는다: `git status --short` 에 없고 `ls tests/ | grep -i ztmp` 무결과.
security 렌즈 finder 가 자기 프로브로 만들었다가 지운 파일이다(security 산출물 §판정 방식이
"판정 후 삭제"라고 자백한다). 이 diff 의 결함 아님 → **무효**.

**다만 사실 자체는 기록할 값어치가 있다** — spec finder 가 그 파일을 목격했고 correctness
finder 의 전체 스위트 로그에도 나타났다 사라졌다. 즉 **렌즈 finder 3명이 같은 워킹트리에서
동시에 pytest 를 돌렸다는 실행 증거**이고, 그것이 finding A(고정 임시 DB 경로)가 가정이
아니라 이 파이프라인의 상시 조건임을 뒷받침한다. 부수 교훈: finder 프로브도 레포 밖에
만들어야 한다(`.agents/07-review.md` §1-1 이 verifier 에게만 그렇게 지시하고 finder 에게는
안 한다 — 스테이지 파일 후속 후보).

### [기각] H — R-5 "토큰=관리자" 불변식의 음성 테스트 없음
`KY_USER_L` 에 비관리자 행을 넣는 라우트가 앱에 없다(가입·초대 기능 부재, `app/controller/router.py`
13개 등록 전수 확인). 지금 쓸 수 있는 음성 테스트가 존재하지 않는다. 설계가 R-5 각주로
이미 "이 규칙은 데이터 불변식에 기댄다"를 명시했고 security finder 자신도 "지금 당장 고칠
결함은 아니다"라고 적었다. → 한계 표기로 충분, finding 아님 (아래 §검증하지 못한 것 이관).

### [기각] I — `_free_port()` TOCTOU (추론 판정)
`tests/test_http_socket.py:22-26` 이 포트를 받아 닫고 uvicorn 이 나중에 바인드한다.
실행 불가 판정 사유: 커널 포트 재할당 타이밍을 결정적으로 강제할 수단이 이 스택에 없다
(양성 대조를 만들 수 없어 프로브가 무효가 된다). 순차 3회 + 동시 2회 실행에서 재현 0.
`bind(0)` 후 즉시 재바인드는 표준 관행이고 대안(소켓을 열어 둔 채 uvicorn 에 fd 를 넘기기)은
uvicorn 재기동 경로를 복잡하게 만든다 — 비용이 이득을 넘는다. → 기각, 기록만.

### [기각] J, K, L
- **J** `os.environ` 미복원: 설계 D-3 이 선택한 구조 그 자체다. 전체 스위트 **282 passed**
  로 회귀 0 을 직접 확인했다(기존 242개 포함). 결함 아님.
- **K** 만료 토큰 collection-time 계산: finder 스스로 하강했고 나도 동의한다 —
  `exp = now - 1h` 라 실행이 늦어질수록 **더 확실히** 만료다. 깨지는 방향이 아니다.
- **L** security 렌즈의 "확인됨/해당 없음" 항목들(IDOR 없음, mass assignment 없음, 사용자
  열거 없음, 500 응답에 내부 정보 없음): 아래 authz 프로브로 독립 재확인했다. finding 아님.

### [필수] authz 프로브 — 무토큰 + 타인 자격
diff 에 신규/변경 엔드포인트는 없지만(앱 무수정) `.agents/07-review.md` §1-1 의 상시 실행
규정대로 돌렸다. 인증 필수 6개 라우트 × 자격 6종:

```
no-token   / forged / expired / garbage / empty   × {GET,POST} 인증 6라우트
  → 36/36 전부 307 Location: /login  (보호 리소스 바디 0)
AUTHZ VIOLATIONS: NONE
```
307 은 `401/403/404` 가 아니지만 **거부**다: `app/main.py:49-51` 의 401 핸들러가
`RedirectResponse(url='/login')` 로 바꾼 결과이고(R-1, 설계가 고정한 현행 동작),
응답에 보호 리소스가 실리지 않음을 바디 길이로 확인했다. blocker 아님.

한 가지 관측을 기록한다 — **DB 에 없는 사용자명으로 서명한 유효 토큰은 관리자 권한을 얻는다**:
```
ghost-user(valid sig)  GET/POST 인증 6라우트 → 전부 200
```
`app/util/auth.py:40-46 get_current_user` 는 토큰을 디코드만 하고 `KY_USER_L` 존재 여부를
조회하지 않는다. 다만 토큰은 `SECRET_SALT` 를 알아야 만들 수 있고 발급 경로는 비밀번호를
검증하는 로그인뿐이라 **IDOR 도 권한 상승도 아니다** — 이 앱의 무상태 JWT 설계(R-5 이진
모델)의 귀결이다. 앱 무수정 diff 의 결함이 아니므로 finding 아님. 실질 의미는
**토큰 폐기(revocation) 수단이 없다**는 것 — 사용자를 지워도 발급된 토큰은 만료까지 산다.
앱 후속 과제로만 남긴다.

---

## 체크리스트 #6 테스트 품질 · #9 유지보수 (렌즈 배정 없음 — verifier 직접)

### #6 테스트 품질
- **약화된 assertion 스윕**: `04-test-audit.md` 가 지적한 2건(env 프로브 상태 미단언,
  pages 중복 폼 테스트)은 현재 코드에 반영돼 있다(`test_http_env.py:74·78·86` 상태 단언 존재,
  pages 에 중복 없음). 새로 찾은 약화 단언은 위 M·N·O 뿐이다.
- **자기 기대만 검증하는 테스트**: `test_config_uses_the_mock_values...`,
  `test_llm_keys_are_empty_in_tests` 는 앱이 아니라 하네스를 검증한다. 그러나 AC-1·AC-8 이
  명시적으로 요구한 가드이고, 후자는 **없으면 뒤 테스트가 실제 유료 호출을 낸다**(이 브랜치
  실측 사고). 정당 — finding 아님.
- **양성/음성 짝**: 잘 잡혀 있다. `test_expired_and_forged_are_distinguishable_below_http`
  가 유효 토큰 왕복 양성 대조를 포함해 "`decode_token` 이 항상 던지는" 구현을 배제한다.
  `test_login_rejects_a_username_that_does_not_exist` 는 4단계 뮤테이션에서 실제로
  뚫렸던 자리(`get_password` 의 WHERE 삭제)를 정확히 겨냥한다 — 뮤테이션 근거가 주석에
  남아 있어 다음 사람이 이 테스트를 지우지 않는다. 좋은 자산이다.
- **상호 대조 구조**: `test_known_uncovered_packages_stay_uncovered[h11]`(ASGI 에서 0)과
  `test_real_socket_path_executes_h11`(실소켓에서 >0)이 짝이라, 프레임 매칭 패턴
  (`/site-packages/{pkg}/`)이 어떤 설치 레이아웃에서 통째로 안 맞으면 최소 한쪽이 red 가 된다 —
  공허한 초록으로 무너지지 않는다. 의도된 설계로 판단, finding 아님.
- **결정성**: 정방향·역순·파일 단독·전체 스위트 전부 재실행해 동일 결과 확인.

### #9 유지보수
- 파일 5개 총 518줄, 최장 178줄. 테스트 함수는 전부 10줄 내외 — 읽기 난이도 문제 없음.
- 네이밍이 문장형(`test_no_token_is_redirected_to_login`)이라 실패 출력만 보고 뜻이 읽힌다.
  번호 약어 없음.
- **docstring 이 "왜"를 소유한다** — 307 인 이유, `:memory:` 를 안 쓰는 이유, 하한만 재는
  이유, 키를 비우는 이유가 전부 코드 옆에 있고 근거 문서를 지목한다. 이 레포에서 다음 사람이
  가장 헤맬 자리들이 정확히 커버됐다.
- 유일한 유지보수 결함이 위 D — **docstring 이 파일 내용과 어긋나는 한 곳**이다.
  나머지는 문서와 코드가 일치한다(`osv-scanner.toml` "40개" ↔ `pytest --collect-only` 40 실측).

---

## 숨은 결합 발견

새로 발견한 것 1건 (`.agents/context/codebase-conventions.md` § 숨은 결합에 append 대상 —
리뷰어는 파일을 수정하지 않으므로 메인 에이전트가 올린다):

| 결합 | 왜 안 보이나 | 발견 경위 |
|---|---|---|
| `tests/test_http_socket.py` 의 h11 프레임 계측 ↔ **httpx/httpcore 자신의 h11 사용** | 계측 스레드에 서버와 클라이언트가 같이 있어, 프레임이 어느 쪽 것인지 파일만 보면 구분되지 않는다. 게다가 `uvicorn.Config(http="auto")` 는 `httptools` 가 깔리면 조용히 서버 파서를 바꾼다 — 클라이언트 h11 이 남아 단언은 계속 초록이다 | 2026-08-02 7단계 verifier 프로브 (h11 미사용 생 asyncio 서버에 요청 → 184 프레임 관측) |

기존 5건(`codebase-conventions.md` 에 이번 브랜치가 등재한 것)은 전부 코드와 대조해 정확함을
확인했다 — 특히 `app/main.py` 모듈 `app` ↔ 팩토리 밖 데코레이터는 `app/main.py:41-51` 로 재확인.

---

## 검증하지 못한 것 (필수)

1. **`httptools` 설치 시나리오의 양성 대조를 못 돌렸다.** finding M 의 "uvicorn 이 h11 을
   안 쓰게 되어도 테스트가 초록"은 `http="httptools"` 강제로 확인하려 했으나 패키지 미설치로
   서버가 안 떴다. 클라이언트 측 h11 이 184 프레임을 낸다는 것은 직접 관측했으므로 결론은
   유지되지만, **드리프트 시나리오 자체는 실행으로 못 봤다.**
2. **`/tmp` 심볼릭 링크 TOCTOU 를 재현하지 않았다** (finding A 병합분). macOS 는 `$TMPDIR` 가
   사용자별이라 이 머신에서 공격 조건을 못 만든다. 공유 `/tmp` 리눅스에서의 실제 악용
   가능성은 코드 형태로만 판단했다 — 추론 판정.
3. **진짜 워커 병렬(pytest-xdist) 거동 미확인.** finding A 는 별도 프로세스 2개로 쟀다.
   xdist 는 미설치이고 워커 격리 시맨틱이 다를 수 있다.
4. **R-5 "토큰=관리자"의 데이터 불변식은 테스트로 지켜지지 않는다** (finding H). 나중에
   가입·초대 기능이 생기면 `KY_USER_L` 에 비관리자 행이 들어갈 수 있고, 그때 이 오라클은
   "토큰=관리자"를 참으로 고정한 채 회귀를 못 잡는다. 지금은 그런 라우트가 없어 테스트 불가.
5. **토큰 폐기 부재는 이 리뷰가 판정하지 않았다.** DB 에 없는 사용자로 서명한 유효 토큰이
   200 을 받는 것은 실행으로 확인했다(위 authz 프로브). 앱 설계 판단이라 사람 몫으로 남긴다.
6. **`/docs`·`/openapi.json` 노출의 실질 위험도는 판정하지 않았다.** 200 과 바디 크기만
   확인했고(6082B openapi), 내부 스키마 노출이 이 내부 도구에서 허용 가능한지는 사람 판단이다.
7. **의존성을 실제로 올려 보지 않았다.** 이 오라클의 최종 증명은 "h11·jinja2 등을 올렸을 때
   red/green 이 의미를 갖는가"인데, 이번 리뷰는 현재 버전에서의 커버리지만 쟀다.
   `osv-scanner.toml` 해소 순서 2단계(업그레이드)는 아직 아무도 실행하지 않았다.
8. **`function_calling_deck.html`** 이 레포 루트에 untracked 로 있다. 이번 기능의 산출물
   목록에 없어 리뷰 대상에서 제외했다 — 커밋에 섞이지 않도록 사람이 확인해야 한다.
9. **잘못된 `cal_date`(예: `not-a-date`) → 500** 은 security finder 가 실측했고 나도 범위 밖으로
   동의했다(앱 무수정). 이 오라클은 그 경로를 안 덮는다.

---

## verdict

**BLOCK** — major 2건. 둘 다 `tests/` 안이고 앱은 무관하다.

`.agents/07-review.md` §4 라우팅상 **5단계(리팩토링)로 보내지 않는다** — 구현이 문제가
아니라 테스트가 문제다. 규정 경로는 **사람 승인 → 4단계에서 `TEST_LOCK_OVERRIDE=1` 로 수정
→ 6단계 재검증 → 7단계 델타 재리뷰**다.

고쳐야 할 것 (둘 다 `tests/` 이므로 한 번의 unlock 으로 함께 처리한다):

1. `[major] tests/test_http_socket.py:96` — h11 프레임 단언이 서버가 아니라 httpx 클라이언트의
   h11 을 센다 (h11 미사용 서버에서 184 프레임 실측) → 그 테스트의 요청을
   `asyncio.open_connection` 생 소켓으로 바꾸고, `uvicorn.Config` 에 `http="h11"` 를 명시한다.
   같은 계열인 `[minor] tests/test_http_env.py:117-118`(cryptography 음성 대조 표본)도
   **같은 수정 안에서** 양·음 계측 트래픽을 통일해 함께 닫는다 — 라인 패치 2개로 나누면
   계열이 남는다.
2. `[major] tests/conftest.py:20` — 고정 임시 DB 파일명이라 동시 pytest 프로세스가 서로를
   깬다 (3/3 재현) → `tempfile.mkdtemp(prefix="moru_oracle_")` + teardown 에서 디렉터리째 삭제.
   `/tmp` 심볼릭 링크 TOCTOU 도 같은 줄에서 닫힌다.

minor 5건(B / D / O 3건)은 결정 로그에 기록 후 통과 가능하다. 다만 D 와 O 의 프레임 카운터
중복은 위 1번을 고치는 김에 사실상 같이 닫히므로, 그때 함께 정리하는 것이 싸다.

사람 판정이 필요한 것 (리뷰어가 결정하지 않음):
- `/docs`·`/openapi.json`·`/redoc` 을 프로덕션에서 닫을지 — **이번 diff 에서는 건드리지 말 것**
  (테스트로 200 을 고정하면 나중에 닫는 것을 막는다). 앱 후속 과제.
- 토큰 폐기(revocation) 부재 — 앱 설계 판단.

### 종료 조건
- [x] 렌즈 3개 finder 원출력을 전부 읽었다 (비게이트 — 심층 적대 렌즈 미실행이 규정대로)
- [x] blocker/major 후보가 전부 반박 검증을 거쳤다 (실행 가능한 것은 전부 프로브)
- [x] verifier 자신이 추가한 major(M)도 동일한 반박 절차를 거쳐 기록했다
- [x] 필수 authz 프로브 실행 (무토큰 + 타인 자격 6종 × 6라우트)
- [x] 운영 가시성(#8) — 설계 §3-2 가 N/A (런타임 표면 없음)
- [x] 체크리스트 #6·#9 를 verifier 가 직접 커버
- [x] "검증하지 못한 것" 작성 (9건)
- [x] "숨은 결합 발견" 작성 (신규 1건)
- [x] 프로브 파일 전량 삭제 — `git status --short` 에 프로브 잔재 없음 확인
- [ ] blocker/major 없음 → **미충족 (major 2건)**
