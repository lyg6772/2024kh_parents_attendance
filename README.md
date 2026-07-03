# 2024kh_parents_attendance

## 보람교사(급식 도우미) 출석 관리 웹앱

학부모 보람교사의 출석 현황을 관리하는 웹 애플리케이션.  
관리자(admin) 로그인 시 **챗봇을 통해 자연어로 출석 조회, 저장, 엑셀 다운로드 등 주요 기능을 제어**할 수 있다.

### 주요 기능

- 월별 출석 캘린더 조회 / 날짜별 참석자 및 특이사항 관리
- LLM 챗봇 (Groq + Gemini failover) 을 통한 자연어 기반 기능 실행
- 출석부 Excel 다운로드
- 기존 UI와 챗봇이 공존 — LLM 장애 시 기존 화면으로 업무 가능

### 기술 스택

Python 3.12+ / FastAPI / Jinja2 SSR / async SQLAlchemy / Oracle DB (로컬: SQLite)

### 로컬 실행

```bash
# 1. 의존성 설치
pip install poetry
poetry install

# 2. 환경변수 설정
cp app/.env_example app/.env
```

`app/.env` 를 열고 아래 항목을 채운다:

```
DB_URL=sqlite+aiosqlite:///app/local.db
SECRET_SALT=아무-문자열-입력
GROQ_API_KEY=            # https://console.groq.com 에서 발급 (무료)
GEMINI_API_KEY=           # https://aistudio.google.com 에서 발급 (무료)
```

> 챗봇 없이 기본 UI만 사용하려면 `GROQ_API_KEY`, `GEMINI_API_KEY`는 비워둬도 된다.

```bash
# 3. 서버 실행
python run_app.py
```

`http://localhost:8000` 접속 → 로그인: `admin` / `admin`  
(최초 실행 시 SQLite DB와 admin 계정이 자동 생성된다)