# 2024kh_parents_attendance — Project Overview

> **범위·설계를 판단하기 전에 읽는다.** 필요한 갈래를 따라가고, 대화만 보고 추론하지
> 않는다. **Current direction** 은 결정이 날 때마다 갱신한다.
>
> 이건 지도지 영토가 아니다 — 짧게 두고, 자세한 것은 갈래 문서로 민다.

## What this is

학부모 보람교사(급식 도우미) **출석 관리 웹앱**. 관리자가 월 단위 캘린더에서 출석을
기록·조회·엑셀 내보내기 하고, 같은 일을 자연어로도 할 수 있게 LLM 챗봇 에이전트가
붙어 있다.

## Architecture at a glance

FastAPI **SSR** 앱 (Jinja2 서버 렌더링) + 뒤에 붙은 **에이전트 레이어**.

```
브라우저 ──HTTP──▶ app/controller ──▶ app/service ──▶ app/dao ──▶ DB
                                                                (Oracle / SQLite)
브라우저 ──/agent/chat──▶ app/agent/router ──▶ engine ──┬─▶ tools ──▶ service ──▶ dao
                                                       └─▶ llm (Groq → Gemini failover)
```

| 경계 | 내용 |
|---|---|
| 계층 방향 | controller → service → dao. 역방향 import 없음 |
| 인증 | JWT(HS256) → httpOnly 쿠키. `app/util/auth.py`. `/agent/*` 도 같은 `get_current_user` 를 공유 |
| DB | SQLAlchemy 2.x async. 운영 Oracle(oracledb), 로컬 SQLite(aiosqlite). `DB` 는 싱글턴이고 `create_app()` 에서 한 번만 `init_db()` |
| 외부 의존 | Groq(primary) · Gemini(fallback) — `FailoverAdapter` 로 감쌌다 |
| 에이전트 안전장치 | READ 도구는 즉시 실행, WRITE 도구는 confirmation gate 를 거친다 (`engine.confirm()`). MAX_TURNS=5 |

Oracle 대소문자 · Jinja2 경로 · delete→insert 패턴 같은 **함정은
[AGENTS.md](../AGENTS.md) § Critical Quirks** 가 소유한다.

## Branches (detail docs)

| 갈래 | 어디 |
|---|---|
| 결정 기록 (왜) | `docs/adr/README.md` |
| 기능별 결정 로그 | `.agents/context/decisions/<feature>.md` |
| 코드베이스 규약·검증 커맨드·부채 실측 | `.agents/context/codebase-conventions.md` |
| 개발 원칙·레이어 규칙 | `DEVELOPMENT.md` |
| 스택·함정·하네스 규칙 | `AGENTS.md` |
| 파이프라인 스테이지 정의 | `.agents/workflow.md`, `.agents/0*-*.md` |
| 게이트가 읽는 레포별 노브 | `.agents/context/repo-profile.sh` |

## Current direction

*(2026-07-31 — moru 하네스 초기화 시점의 상태다. 결정이 나면 갱신한다.)*

- **하네스가 방금 들어왔고, 파이프라인은 아직 한 번도 돌지 않았다.** 첫 실행이 곧
  하네스 자체에 대한 첫 측정이다.
- **의존성 CVE 가 미해결이다.** 건수와 목록은 `osv-scanner.toml` 이 소유하고 현재
  값은 `osv-scanner --recursive .` 로 잰다 — 린트 부채와 같은 이유로 여기 복제하지
  않는다. 성격만 적으면, 취약점이 몰린 곳이 `pymysql`(DB 드라이버) · `h11`(HTTP
  파서) · `jinja2`(SSR 템플릿) · `pyjwt`(인증)이라 **전부 실사용 경로 위**이고,
  `pyjwt` 에는 상류 수정본이 아직 없는 건도 있다. **의존성 올리기가 다음 작업 후보
  1순위**이며 브랜치는 `chore/` 가 아니라 `feat/` 다 — 의존성 변경은 승인 기록이
  필요하고 그 자리가 파이프라인의 결정 로그이기 때문이다 (`.agents/team-policy.md`).
- **린트·타입 부채가 있다.** 건수는 `.agents/context/codebase-conventions.md` 가
  소유한다 (재측정 명령과 함께) — 움직이는 값이라 여기 복제하지 않는다. 훅에는 비차단으로
  물려 있다 — 기존 코드를 이번에 건드리지 않기로 한 결정이다. 정리는 별도
  `refactor/` 과제.
- **CI 없음.** 검증은 로컬 훅에만 의존한다.
- 다음 기능 과제: 에이전트 **도구 자동 등록** (지금은 `ToolDefinition`·핸들러·
  레지스트리 3곳을 손으로 동기화한다 — `app/agent/tools.py`).

## Maintenance

낡은 개요는 **틀린 맥락을 확신 있게** 만들어 낸다. ADR 이 들어오거나 기능 결정
로그가 확정될 때 **Current direction** 을 갱신한다 — 결정 로그와 같은 규율이다.
