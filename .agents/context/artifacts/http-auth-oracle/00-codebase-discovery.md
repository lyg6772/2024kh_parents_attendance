## [0단계] 코드베이스 탐색 산출물

### 입력
- 요구사항: HTTP 엔드포인트와 인증 경로에 통합 테스트를 추가해 **의존성 업그레이드의
  오라클을 만든다.** `osv-scanner.toml` 이 기재한 해소 순서 ①에 해당한다 — 지금은 앱
  테스트가 전부 순수 유닛이라 취약 패키지를 하나도 실행하지 않아, 버전을 올리고 초록을
  봐도 그것이 가짜 초록이다. **이번 범위는 오라클까지이고 업그레이드는 하지 않는다**
  (사람 판정 2026-08-02: 한 PR 에 묶으면 red 가 "내 테스트가 틀렸나 / 업그레이드가
  깼나"로 갈려 지금은 기준선이 없어 구분이 불가능하다).
- 누락 입력: 없음 (0단계는 첫 단계)

codegraph 사용 — 레포 루트에 `.codegraph/` 존재. 구조·호출 관계·커버리지 공백은
`codegraph explore` 로 확인했고, 아래 "커버하는 테스트 없음" 표기는 그 출력이다.

### 프로젝트 현재 상태

- 기존 도메인 모델: `app/dao/tables.py` (`KyUserL` 등, SQLAlchemy `Base`)
- 기존 진입점: `app/controller/router.py` 가 `add_api_route` 로 **9개**,
  `app/agent/router.py` 가 데코레이터로 **2개** — 합 11개.
  `app/main.py` 에 `GET /` 헬스체크와 401 예외 핸들러(→ `/login` 리다이렉트)가 별도로 있다.
- 기존 데이터 접근 계층: `app/dao/{login,admin,attendee,functions}.py`,
  세션 공급은 `app/util/db.py` 의 `get_session` (FastAPI 의존성) 과 `DB` 싱글턴
- 기존 테스트: `tests/` 6개 파일 242개. **전부 순수 유닛** — `TestClient`·`httpx`
  사용 0건, 인증 경로 테스트 0건, Jinja2 렌더링 테스트 0건 (codegraph 가
  `encode_token`·`decode_token`·`get_current_user`·`login_post` 전부
  "no covering tests found" 로 보고)

### 재활용 가능 자산

#### 직접 재활용 (그대로 사용)
| 파일 경로 | 재활용 대상 | 용도 |
|-----------|------------|------|
| `tests/conftest.py` | `db_session` fixture | in-memory SQLite(`sqlite+aiosqlite://`) + `create_all`/`drop_all`. HTTP 테스트의 DB 바닥을 그대로 쓴다 — 새로 만들 이유가 없다 |
| `app/util/db.py` | `get_session` | `dependency_overrides` 의 **키**. 이것을 갈아끼우면 `DB` 싱글턴(실 DB) 을 건드리지 않고 테스트 세션을 주입할 수 있다 |
| `app/util/auth.py` | `AuthHandler.encode_token` | 인증 요청용 유효 토큰 생성. 토큰을 손으로 만들지 않는다 — 만들면 앱이 쓰는 알고리즘·클레임과 갈라진다 |
| `app/main.py` | `create_app` | 모듈 수준 `app` 대신 팩토리를 쓰면 테스트마다 깨끗한 인스턴스를 얻는다 |
| `pyproject.toml` | `asyncio_mode = "auto"` | 이미 켜져 있어 async 테스트에 데코레이터가 필요 없다 |
| (설치됨) | `httpx 0.27.2` | `ASGITransport` 로 네트워크 없이 앱을 탄다. **의존성 추가 불필요** — 확인함 |

#### 확장 재활용 (상속/조합)
| 파일 경로 | 확장 대상 | 확장 방법 |
|-----------|----------|----------|
| `tests/conftest.py` | 모듈 수준 | 앱 import **이전에** 환경변수를 세팅하는 코드가 여기 들어가야 한다 (아래 제약 참조). 기존 `db_session` 은 건드리지 않고 fixture 를 덧붙인다 |

#### 신규 필요
| 대상 | 이유 |
|------|------|
| HTTP 클라이언트 fixture (`httpx.AsyncClient` + `ASGITransport`) | 레포에 ASGI 를 타는 테스트가 하나도 없다 |
| 인증된 클라이언트 fixture (쿠키에 유효 JWT) | 11개 중 6개가 `Depends(get_current_user)` 를 건다 — 인증 없이는 그 경로에 못 들어간다 |
| `get_session` 오버라이드 배선 | 실 DB 싱글턴을 타지 않게 하는 유일한 지점 |

### 영향받는 기존 파일
| 파일 경로 | 변경 내용 |
|-----------|----------|
| `tests/conftest.py` | fixture 추가 + 앱 import 전 환경변수 세팅. 기존 `db_session` 은 유지 |
| `tests/test_http_*.py` (신규) | 이번 단계에서 만들 파일 — 기존 파일 아님 |

**앱 코드(`app/`)는 건드리지 않는다.** 이번 범위는 오라클 생성이고, 앱 수정은 오라클이
생긴 뒤에 판단할 일이다.

### 탐색으로 드러난 제약 (설계를 구속함 — 실행으로 확인)

1. **`app/config.py` 가 import 시점에 죽는다.** `SECRET_SALT` 가 없으면 12행에서
   `RuntimeError`. 그리고 `app/.env` 는 `.gitignore:123` 에 걸려 **커밋되지 않는다** —
   새 클론이나 CI 에는 그 파일이 없다. 실행 확인:
   `env -u SECRET_SALT python -c "import app.config"` → RuntimeError.
   따라서 오라클은 **앱을 import 하기 전에** 환경변수를 세우거나, 그 전제 없이는
   수집조차 안 된다. 지금 로컬이 초록인 것은 개발자 머신에 `.env` 가 있어서다.
2. **`app.main` 은 import 시점에 `DB().init_db()` 를 부른다** (`app = create_app()` 이
   모듈 수준). `DB_URL` 이 비면 Oracle URL 을 조립하므로, 테스트는 sqlite `DB_URL` 을
   함께 세워야 한다. 실행 확인: `SECRET_SALT=x DB_URL=sqlite+aiosqlite:///:memory:` 로
   import 성공, `len(app.routes) == 17`.
3. **Jinja2 템플릿 경로가 상대경로이고 파일마다 다르다** — `app/service/login.py` 는
   `"./app/template"`, `app/controller/{admin,attendee}.py` 는 `"./template"`.
   테스트는 레포 루트에서 돌아야 하고, 렌더링을 실제로 확인하는 케이스는 이 불일치에
   걸릴 수 있다. **이번에 고치지 않는다** (범위 밖) — 2단계 영향 맵에 올린다.
4. **401 은 예외가 아니라 리다이렉트로 관찰된다.** `app/main.py` 의 401 핸들러가
   `/login` 으로 `RedirectResponse` 를 낸다. 즉 인증 실패의 수용 기준은
   "401 을 받는다"가 아니라 "로그인으로 돌려보낸다"이다 — 이것을 잘못 잡으면 테스트가
   앱 동작이 아니라 내 기대를 검증하게 된다.

### 부채 겹침 (§5)

`.agents/context/debt.md` 없음.

다만 `osv-scanner.toml` 이 사실상 같은 역할을 하고 있고, **이번 작업이 정확히 그
원장을 해소하려고 존재한다.** 등재 현황(실측 2026-08-02, `grep -c IgnoredVulns`):
**74행 / 13개 패키지.** 이 중 실사용 경로 위라고 그 파일이 지목한 6개는
pymysql · h11 · jinja2 · pyjwt · python-multipart · cryptography 이고, 이번 오라클이
그 여섯을 전부 실행 경로에 올린다 (HTTP=h11, 폼 로그인=python-multipart,
JWT=pyjwt+cryptography, SSR=jinja2, DAO=pymysql 은 sqlite 대체라 **제외** — 아래 참조).

`pymysql` 만 이번 오라클로 안 덮인다: 테스트는 in-memory SQLite 를 쓰므로 MySQL
드라이버를 타지 않는다. 이것은 이번 설계의 알려진 한계이며 2단계 영향 맵과 7단계
"검증하지 못한 것"에 그대로 올린다.

### 기존 동작 베이스라인 (§6)

기존 동작 변경 없음 — 테스트만 추가한다.

### 종료 조건
- [x] 요구사항 관련 기존 코드를 모두 탐색했다 (codegraph + 원문 확인)
- [x] 재활용 가능 자산을 분류했다
- [x] 영향받는 파일 목록을 작성했다
- [x] 부채 원장 겹침을 확인했다 (`debt.md` 없음, `osv-scanner.toml` 이 대응물)
- [x] 기존 동작을 바꾸지 않으므로 베이스라인 해당 없음
