# QUICKSTART — 첫 기능 한 번 돌리기

파이프라인 전체 규칙은 `workflow.md`. 이 문서는 해피패스 1회분이다.

## 예시: "상품 카탈로그 API 추가"

```bash
# ① 브랜치 생성 = feature-name 확정 (모든 산출물이 이 이름으로 묶인다)
git checkout -b feat/product-catalog
#    → 결정 로그: .agents/context/decisions/product-catalog.md
#    → 산출물:   .agents/context/artifacts/product-catalog/NN-*.md
#    → LOCK:     .agents/context/locks/product-catalog.lock (4단계에서 생성됨 —
#                 브랜치 생성 시점엔 없다. 커밋됨 — CI가 LOCK 윈도우 감사)
#                 lock 1행 = 전체 브랜치명 "feat/product-catalog" (훅 매칭 키)
```

```text
# ② 파이프라인 실행 (개별 스테이지: /discover /plan /analyze /design ...)
/feature-dev "상품 카탈로그 CRUD API. 상품은 이름/가격/재고를 가진다"
```

**③ 중간에 나(사람)한테 오는 것들:**

| 시점     | 뭐가 오나                                                                                                     | 내가 할 일                                             |
| -------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| 1~3단계  | 모호한 요구사항 질문                                                                                          | 답변 (방안 + 추천 형식으로 옴)                         |
| 3단계 끝 | **게이트 브리핑** (API/DB 변경이므로) — 잘못되면 생기는 일, 되돌리기 난이도, 관측·호환·롤아웃, 가정 대장, Devil's Advocate 위험 | 가정 대장을 먼저 읽고 틀린 가정 있으면 지적. 승인/거부 |
| 실패 3회 | 검증 실패 보고 (시도 내역 + 선택지)                                                                           | 방향 결정                                              |
| 7단계 끝 | 리뷰 verdict + **"검증하지 못한 것"**                                                                         | 미검증 범위 확인 후 머지 판단                          |

**④ 커밋이 훅에 막히면:**

| 훅                              | 의미                             | 대처                                                                                |
| ------------------------------- | -------------------------------- | ----------------------------------------------------------------------------------- |
| `test-lock`                     | 테스트가 LOCK 중 (4~7단계)       | 정상 — 구현 코드만 커밋. 사람 승인된 테스트 수정만 `TEST_LOCK_OVERRIDE=1`           |
| `test-lock`인데 파이프라인 끝남 | stale 마커                       | `.agents/context/locks/` 확인 후 삭제 (`/doctor`가 점검)                            |
| 품질 도구 (스택별 — 예: ruff/pyright) | 코드 품질                        | `/doctor` 또는 자동 수정 후 재커밋                                                  |
| gitleaks/semgrep/osv-scanner    | 보안 (시크릿/SAST/의존성 CVE)    | 내용 확인 — 시크릿이면 제거, 오탐이면 `self-heal` 스킬                              |
| `junk-comments`                 | 디버그/임시 주석 잔여물          | 해당 라인 삭제 후 재커밋                                                            |
| pre-push 테스트 (예: `pytest`)  | 테스트 실패                      | 6단계로 — 테스트를 고치지 말 것                                                     |
| pre-push `pr-review-gate`       | LLM이 최종 diff에서 blocker 발견 | 지적마다 판정(효과→부작용→채택/기각) 후 재푸시 — **한 브랜치 3라운드 상한**이고 4번째 **연속** BLOCK 라운드는 게이트가 거부한다(터미널에서 `CONTINUE`, 또는 `PR_REVIEW_ROUND_CONTINUE="<사유>"` — 아래 override 규칙). 상한에 닿으면 미해결 지적과 함께 사람에게 보고한다. WIP 푸시는 `PR_REVIEW_SKIP=1 git push` — 사람이 `SKIP` 직접 입력해야 통과, 에이전트 단독 불가 (사유는 결정 로그에) |

```text
# ⑤ 7단계 PASS 후 → LOCK 자동 해제(마커 삭제됨) 확인 → PR 생성
/ship-pr
```

PR 본문에 설계 산출물(artifacts) 링크 + 검증 결과가 들어간다 (`team-policy.md` 참조).
사람 게이트(산출물 승인 — 코드가 아니라 구현 요약·검증못한것·가정 대장을 판단) + CI 통과 → squash merge.

Override 공통 규칙: `TEST_LOCK_OVERRIDE` / `PR_REVIEW_SKIP` / `PR_REVIEW_ROUND_CONTINUE` /
`audit-exempt`를 쓰면 결정 로그에 `override 사용:` 라인 필수 — CI가 검사하고 `/doctor`가
빈도를 집계한다. `PR_REVIEW_ROUND_CONTINUE="<사유>"`는 상한에 걸린 **한 라운드만** 승인하고
리뷰는 그대로 돈다(사유는 텔레메트리에 남는다). **사람이 지시했을 때만 쓴다** — 에이전트도
설정할 수 있으므로 자기 승인은 `--no-verify` 급 규범 위반이다.

## 버그 수정은 더 짧다

`team-policy.md`의 버그수정 경로: 0 → 4(재현 테스트) → 5 → 6 → 7-축소(verifier 1명).
핫픽스도 동일하되 3단계 최소 설계 + 사람 승인이 항상 필수.

## 막혔을 때

- 에이전트가 맥락을 잃음 (세션 끊김/compaction) → 결정 로그의 "현재 상태"에서 재개
- 상태 꼬임 (red tests, stale lock, CVE) → `/doctor` (기계적) 또는 `self-heal` 스킬 (근본 원인)

