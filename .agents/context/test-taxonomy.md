# 테스트 taxonomy — 4단계 검수 루브릭

**용도**: 4단계 독립 검수(§4)에서 상위 모델이 테스트 커버리지를 채점하는 체크리스트.
항목을 기계적으로 채우는 폼이 **아니다** — 각 항목의 **적용성은 설계 함의로 판단**한다:
설계·비즈니스 규칙·에러 정책·솔루션 접근(§0-2 파생 요구사항)이 그 항목을 함의하면
"커버 / 미커버"로 채점하고, 함의하지 않으면 **`N/A — 사유 1줄`**로 내린다.
설계에 없는 케이스를 만들라는 지시가 아니라, **설계가 요구하는데 테스트가 빠뜨린 것**을
잡는 그물이다. (drafter는 §3-1로 파생하고, 이 표는 검수가 누락을 잡는다.)

우선순위: HIGH = 게이트 대상이면 미커버 시 blocker 후보. MEDIUM/LOW = 설계 함의 시만.

## 1. 추적성 (Traceability)

| 항목 | 우선 | 확인 |
|---|---|---|
| 요구사항→테스트 | HIGH | 1단계 R# + 설계 R-D# 각각 최소 1개 테스트. 미커버는 사유 명시 |
| Positive/Negative | HIGH | **각 기능 요구사항**에 충족 케이스 + 위반 케이스 둘 다 |

## 2. 행위·중복 규칙 (Behavior / Deduplication) — 핵심

"Duplicate Rule" = **어디까지 재사용하고 어디부터 개별 테스트인가**. anti-bloat 규칙.

| 항목 | 규칙 | 확인 |
|---|---|---|
| 공통 인증 미들웨어 | **Shared — 1회만** | 엔드포인트마다 인증 미들웨어를 재테스트하지 않았는가 (중복 = 삭제 제안) |
| API별 인가 정책 | **Per Policy — 다를 때만** | 정책이 다른 엔드포인트만 각각. 같은 정책은 공유 |
| API별 비즈니스 규칙 | **Per API** | 규칙이 다르면 각각 (설계 §3-1 비즈니스 규칙 표 기준) |

## 3. 경계 (Boundary) — 설계 검증 규칙에서 파생

| 항목 | 우선 | 확인 (해당 검증 규칙이 있을 때) |
|---|---|---|
| Null / 누락 | HIGH | null·필드 누락 입력 |
| Empty | HIGH | 빈 문자열·빈 컬렉션 |
| Length | HIGH | 최소/최대 길이 경계 3종 (경계/초과/미만) |
| Range | HIGH | 숫자 최소/최대 경계 3종 |
| Duplicate | MEDIUM | 중복 데이터 입력 |
| Unicode/특수문자 | MEDIUM | 다국어·이모지·제어문자 (문자열 필드가 있을 때) |
| Ordering | MEDIUM | 정렬·순서 의존성 (순서가 결과에 영향 있을 때) |

## 4. 네거티브 (Negative)

| 항목 | 우선 | 확인 |
|---|---|---|
| Invalid Input | HIGH | 잘못된 형식·타입 불일치 |
| Missing Field | HIGH | 필수 필드 누락 |
| Exception | HIGH | 설계 에러 정책 표의 각 예외 경로 |
| Conflict | MEDIUM | 중복 생성·unique 충돌 (409 등 — 유니크 제약/멱등 설계 시) |

## 5. 계약 (Contract) — 설계 API 표 대비

| 항목 | 우선 | 확인 |
|---|---|---|
| Schema | HIGH | 응답 본문이 설계 Response 스키마와 일치 |
| Status Code | HIGH | HTTP status가 설계 API 표와 일치 |
| Error Response | HIGH | 에러 응답 형식이 에러 정책 표와 일치 |

## 6. 속성 (Property) — 설계 함의 시만 (조건부)

| 항목 | 우선 | 적용 조건 |
|---|---|---|
| Idempotency | HIGH | 설계가 멱등키·재시도를 정한 경우 — 동일 요청 반복 시 결과 동일 |
| Round Trip | MEDIUM | encode/decode·serialize 왕복이 있는 경우 |
| Invariant | MEDIUM | 수학적/도메인 불변식이 명시된 경우 |

## 7. 뮤테이션 연산자 (Mutation) — §4-1 시도 목록

검증이 아니라 §4-1 독립 에이전트가 **체계적으로 시도**할 스펙 위반 유형:

| 연산자 | 우선 | 뚫으려는 것 |
|---|---|---|
| Off-by-One | HIGH | 경계값 ±1로 통과하는가 |
| Missing Validation | HIGH | 검증 한 줄 빼고 통과하는가 |
| Wrong Branch | HIGH | 조건 분기 뒤집고 통과하는가 |
| Incorrect Order | MEDIUM | 처리 순서 바꾸고 통과하는가 |
| Duplicate Processing | MEDIUM | 중복 처리(2회 실행)로 통과하는가 |

## 8. 조건부 — 설계 함의 시만 (일괄 강제 금지)

| 항목 | 적용 조건 |
|---|---|
| Concurrency / Race | 동시 요청 정합성이 설계 관심사인 경우 (낙관적 락·유니크 제약 등) |
| Performance / Large Input | 대용량이 명시적 요구·설계 관심사인 경우 |
| Snapshot / Golden File | JSON/XML 등 출력 계약을 golden으로 고정하는 게 적절한 경우 |
| Branch / Critical Path 커버리지 | 핵심 경로·주요 분기 누락 여부 (요구사항 커버리지와 겹치므로 검수 항목으로만) |
