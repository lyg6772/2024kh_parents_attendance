## [7단계] finder — correctness 렌즈 원출력

렌즈 정의: `.agents/07-review.md` §1-1 "correctness" — edge case, 동시성, 트랜잭션
경계, 에러 경로, 명백한 자원 낭비 (#2), 운영 가시성(#8, 이 작업은 N/A — 설계 §3-2
런타임 표면 없음). coverage-first — 확신 없는 것도 전부 보고, 확신도 표기.

### 대상
- `tests/conftest.py` (수정) — env 고정 블록, `http_db`/`seeded_app`/`client`/
  `admin_client`/`valid_token` fixture
- `tests/test_http_auth.py` `test_http_pages.py` `test_http_agent.py`
  `test_http_env.py` `test_http_socket.py` (신규)
- 앱 코드 변경 0건 — 앱 결함은 이 diff 의 대상이 아니므로 배제

### 실행 환경
`GROQ_API_KEY=""` `GEMINI_API_KEY=""` 로 비운 채 실행(개발자 실키 유료 호출 방지).
`poetry run pytest tests/test_http_*.py -q` 베이스라인: **40 passed, 1.6~1.7s**.

---

### Findings (확신도별)

**[높음] fixture 스코프 불일치로 DB 쓰기가 테스트 간 샌다**
`tests/conftest.py:70` `http_db`(session-scope, 물리 파일 1개, 세션 시작/끝에만
삭제) 위에 `tests/conftest.py:79` `seeded_app`(function-scope, 매 테스트 재사용)이
얹혀 있다. 한 pytest 프로세스 안에서는 모든 테스트가 **같은 물리 sqlite 파일**을
공유하므로, 한 테스트의 쓰기가 이후 테스트에 그대로 보인다.
재현: 레포 밖 스크립트로 (a) write 없이 export, (b) `POST /admin/attendee` 실행 후
export 를 같은 앱/DB 에 호출해 길이 비교.
```
BEFORE write: status 200 len 5695
WRITE: status 200
AFTER write: status 200 len 5732
길이가 다르면 = DB 상태가 두 '테스트' 사이로 샌다: True
```
현재는 어떤 assertion 도 정확한 내용/행수를 안 보므로 **지금 당장 깨지는 테스트는
없다** (`tests/test_http_auth.py::test_write_route_accepts_a_valid_token` 이 이미
실제 파일 순서상 `test_http_pages.py::test_excel_export_streams_a_workbook` 보다
먼저 돈다 — 정상 순서/역순/전체 2회 연속 실행 모두 40 passed 로 재현: 실패 없음,
누수만 존재). 그러나 향후 누군가 export 행수·attendee 개수를 단언하는 테스트를
추가하면 **실행 순서에 의존하는 오라클**이 된다 — 조용한 결함이다.

**[높음] 고정 임시 DB 파일 경로 — 동시 pytest 프로세스 충돌 (재현됨)**
`tests/conftest.py:16` `_DB_FILE = os.path.join(tempfile.gettempdir(), "moru_oracle_test.db")`
— PID/uuid 접미사가 없다. 두 pytest 프로세스가 동시에 이 파일을 공유하면 한쪽의
`http_db` 세션 시작(`os.remove` 후 재생성)이 다른 쪽이 이미 만든 테이블을 지운다.
재현: 같은 셸에서 `poetry run pytest tests/test_http_*.py -q` 를 백그라운드 2개
동시 실행:
```
=== A === 39 passed, 1 error  (2회차 실행)
=== B === 40 passed
```
2회차 실행의 에러 상세:
```
ERROR at setup of test_chat_returns_error_without_calling_out
sqlite3.OperationalError: table "KY_ATDC_L" already exists
```
로컬 단독 실행/순차 실행에서는 안 보이지만, CI 매트릭스 병렬 잡이나 두 브랜치를
동시에 로컬에서 돌리는 상황에서 실제로 터진다. **이 리뷰 세션 도중 실제로
관측됨**: 이 프로브를 실행하던 중 별도 백그라운드 전체-스위트 실행 로그에
`tests/ztmp_probe_test.py`(내가 만들지 않은 파일)가 나타났다 사라졌다 — **동일
워킹트리에 다른 프로세스(다른 리뷰 렌즈/에이전트로 추정)가 동시에 프로브를
쓰고 있었다는 방증**이다. 즉 "동시 실행"은 가정이 아니라 이 리뷰 중에 실제로
벌어진 상황이다. 고정 경로는 그 상황에서 바로 깨진다.

**[중간] 실소켓 스모크가 설계 의도("하나만 둔다")와 달리 2개 테스트 각각 서버를 띄운다**
`tests/test_http_socket.py` 는 파일 docstring·`03-design.md` §설계 근거에서
"실소켓은 1개만 둔다"고 명시했으나, `test_app_serves_over_a_real_socket` 과
`test_real_socket_path_executes_h11` 두 함수가 각각 function-scope `live_server`
fixture(`tests/test_http_socket.py:29`)를 새로 만들어 **uvicorn 인스턴스를 2번**
띄우고 내린다. 실측 `--durations=10`:
```
0.27s setup    test_app_serves_over_a_real_socket
0.18s teardown test_real_socket_path_executes_h11
0.17s teardown test_app_serves_over_a_real_socket
2 passed in 0.71s
```
버그는 아니고 절대 비용도 작지만(총 ~0.5s), 체크리스트 #2의 "명백한 자원
낭비"·설계 근거 문서의 자체 원칙("전부 실소켓으로 돌리면 느려지고 flaky
표면 생긴다")과 어긋난다. 두 단언을 한 테스트(하나의 `live_server`)에 합치면
서버 1개로 줄일 수 있었다.

**[낮음] `os.environ.update()` 를 되돌리지 않는다 — 의도된 설계, 재확인만**
`tests/conftest.py:34` 이후 전역 프로세스 env 를 세션 끝까지 되돌리지 않는다.
전체 스위트(기존 242 + 신규) 동시 실행으로 회귀 재확인: `poetry run pytest -q`
(harness 스위트 포함) → **284 passed**, 실패 2건은 위에서 확인한 **무관한
`tests/ztmp_probe_test.py`**(다른 프로세스의 잔재, 이미 삭제됨 — 이 diff 파일이
아님) 뿐이었다. 설계 문서(D-3, `03-design.md`)가 이 트레이드오프를 이미 인지하고
있고 실측으로 회귀 0 을 주장한 것과 일치한다. 새 리스크는 아니고, 다만 "되돌리지
않는다"는 사실 자체는 이 세션에 테스트가 더 추가될 때마다 재검토 없이 계속
누적된다는 점만 기록.

**[낮음] `_free_port()` ↔ 실제 uvicorn 바인드 사이 TOCTOU** (추론 판정 — 재현 안 됨)
`tests/test_http_socket.py:22` 소켓을 열어 포트를 받고 즉시 닫은 뒤, 그 포트 번호로
uvicorn 이 나중에 바인드한다. 그 사이 창에서 다른 프로세스가 같은 포트를 채갈 이론적
가능성이 있다. 로컬 반복 실행(순차 3회, 동시 2회)에서 재현 안 됨 — OS 가 매번 다른
포트를 배정해 실제 충돌 확률은 낮다. 확신 낮음, 기록만.

**[낮음] 만료 토큰의 collection-time 계산 — 확인 결과 버그 아님**
`tests/test_http_auth.py:83` parametrize 가 `_expired_token()`/`_forged_token()`
을 수집 시점에 호출한다. 우려: 실행 시점과 시차가 크면 만료 판정이 흔들리는가.
확인: `_expired_token()` 이 만드는 `exp` 는 **수집 시점 기준으로 이미 과거**(`now - 1h`)
이므로, 시계가 거꾸로 가지 않는 한 실행 시점이 더 지나 있을수록 오히려 더 확실히
만료 상태다 — 스위트가 느려져도 깨지는 방향이 아니다. 실질 버그 아님, 확신 낮음
으로 하강 보고.

**[정보] 단언 정확성 — 표본 점검 결과 전부 앱 실제 동작과 일치**
`app/main.py:49` 401 예외 핸들러가 무조건 `RedirectResponse(url='/login')` 반환 →
307 + `Location: /login` 단언(R-1/R-3) 일치. `app/util/db.py` 오버라이드 키
2개(`DB.get_db_session`, `get_session`) — `grep Depends(` 로 앱 전체를 확인한 결과
이 두 개가 전부이고 `tests/conftest.py:100-101` 이 정확히 이 둘을 건다 (제3의
누락 경로 없음). `app/agent/router.py` 의 `/agent/chat`·`/agent/confirm` 예외
경로가 실제로 `{"status": "error", ...}` 를 200 으로 반환 — 단언과 일치.

---

### 판정 방식 요약
전부 **프로브** — 순수 추론 판정 없음(만료 토큰 건만 추론 확인, 재현 시도 후
버그 아님으로 하강).

### 검증하지 못한 것
- pytest-xdist 등 진짜 워커 병렬 실행 하에서의 거동(현재 미설치, 이 리뷰는 별도
  프로세스 2개로 동시성을 흉내냈을 뿐 xdist 워커 격리 시맨틱과는 다를 수 있음)
- CI 매트릭스(다른 브랜치 동시 실행)에서 임시 파일 경로 충돌의 실제 빈도
