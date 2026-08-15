# Sales Hunter AI

K-Sales Hunter의 AI 서비스입니다. LangGraph 기반 멀티 에이전트로 상품 분석, 통관 판정, 마진 계산, 현지화 콘텐츠 생성을 담당합니다.

3-tier 구조에서 **추론과 워크플로 실행만** 맡습니다. 인증, 업무 데이터 소유, 상태 확정, 사용자 승인은 Spring Boot에 있습니다.

MVP 범위는 **Shopee 베트남 단일**입니다.

## 빠른 시작

```bash
cp .env.example .env      # OPENAI_API_KEY 등 채우기
make up                   # postgres(pgvector) + redis
make install
make migrate
make dev                  # http://localhost:8000/docs
```

## 아키텍처

```
React  ──REST/SSE──▶  Spring Boot  ──HTTP──▶  Python AI (이 레포)
                           │                       │
                           ├── PostgreSQL public   └── PostgreSQL ai 스키마
                           │   (업무 데이터 정본)       (checkpoint, RAG, 로그)
                           └── Redis app:*             Redis ai:*
```

**진행 상태**는 Redis Pub/Sub `job:{jobId}:events` 로 흘리고 Spring이 SSE로 릴레이합니다.
**최종 결과**는 콜백 REST로 전달하며, 실패하면 `ai.job_results`에 보관해 Spring이 회수합니다.
**취소**는 Spring이 `job:{jobId}:cancel` 플래그를 세우고 Python이 노드 경계에서 확인합니다.

## 디렉토리

```
src/app/
├─ core/              # 엔트리포인트 무관 영역. 코드의 90%
│  ├─ graph/          # LangGraph. 노드 = 요구사항 ID 1:1
│  ├─ agents/         # 프롬프트 + LLM 스키마
│  ├─ pricing/        # 순수 계산. LLM import 금지
│  ├─ rag/            # pgvector 리트리버
│  └─ providers/      # 외부 데이터 어댑터 (Mock 우선)
├─ contracts/         # Spring과의 계약. 자세한 건 contracts/README.md
├─ entrypoints/       # FastAPI. 여기만 교체하면 실행 방식이 바뀐다
├─ infra/             # DB, Redis, LLM, Spring 콜백
└─ observability/     # 로깅, 토큰·비용 계측
```

### 철칙 두 가지

**`core/`에서 FastAPI를 import 하지 않습니다.** 코어는 state를 넣으면 state가 나오는 순수 영역이어야 합니다. 그래야 테스트가 쉽고, Streamlit 시연 환경에서 코어를 그대로 재사용할 수 있으며, 나중에 ARQ 워커로 전환할 때 교체 범위가 `entrypoints/`로 한정됩니다.

**`core/pricing/`에서 LLM을 import 하지 않습니다.** 숫자는 코드가 계산하고 해설만 LLM이 합니다.

## 에이전트와 노드

논리 에이전트 7개를 그래프 3개에 배치합니다.

| 에이전트 | 노드 | 요구사항 |
|---|---|---|
| 0. 오케스트레이터 | fan-out, REPORT_COMPOSE | R-000 |
| 1. 트렌드 헌터 | PRODUCT_UNDERSTANDING, MARKET_RESEARCH, MARKET_SCORE, MARKET_INSIGHT | R-001 |
| 2. 마진 메이커 | MARGIN_CALC, MARGIN_CRITIC, MARGIN_EXPLAIN | R-002 |
| 3. 콘텐츠 아키텍트 | CONTENT_GENERATE, CONTENT_CRITIC | R-003 |
| 4. 크로스보더 가디언 | CUSTOMS_GATE, LOGISTICS_ESTIMATE, RISK_CHECKLIST | R-004 |
| 5. 전략 코파일럿 | classify_intent, answer_query, build_change_plan | R-005 |
| 6. 오토 업로더 | **미구현** (과업 범위 제외) | R-006 |

`CUSTOMS_GATE`가 가장 먼저 실행됩니다. `BLOCKED`면 이후 노드를 돌리지 않습니다. 근거는 state에 남고 Spring이 내부 감사용으로 저장하며, 사용자 화면에서만 제외됩니다.

국가 fan-out은 `Send` 기반으로 구현되어 있지만 MVP 입력은 `["VN"]` 단일입니다. 병렬 구조 자체가 R-000-03 요구사항이고 논문 주제이므로 코드에서 빼지 않습니다.

## 설계 근거 요약

**긴 작업을 `asyncio.create_task` + `Semaphore(3)`로 돌립니다.** 별도 워커 프로세스와 브로커 없이 시작합니다. 프로세스가 재시작되면 실행 중 잡이 사라지지만 LangGraph checkpoint가 남아 있어, Spring이 retry를 걸면 완료된 노드를 재사용하고 이어서 실행됩니다.

**벡터 DB는 pgvector입니다.** 정책 문서 검색에 유효기간 범위 필터(`effective_from <= :as_of AND (effective_to IS NULL OR effective_to > :as_of)`)가 필요한데, 이게 SQL 한 줄이면 되는 것이 결정적이었습니다. 문서 메타데이터와 임베딩이 같은 테이블에 있어 동기화 문제도 없습니다.

**베트남어 원문을 적재 시점에 한국어로 번역한 뒤 임베딩합니다.** 한↔베 교차언어 검색 품질을 튜닝할 시간이 없어서, 한국어끼리 매칭하는 쪽이 안정적입니다. 원문은 출처 대조용으로 함께 보관합니다.

**`ai_service` 계정은 public 스키마 권한이 없습니다.** "AI가 업무 데이터를 건드리지 않는다"를 문서상 약속이 아니라 DB 권한으로 강제합니다. 실수로 `products`에 INSERT 하는 코드를 짜도 그냥 에러가 납니다.

전체 결정 배경은 기술결정서 v1.2를 참고하세요.

## 개발

```bash
make lint       # ruff check + format
make test       # LLM mock. CI에서 도는 것
make test-live  # 실제 LLM 호출. 주 1회 수동
make contracts  # 스키마 수정 후 반드시 실행하고 커밋
```

계약 스키마를 고쳤으면 `make contracts`를 돌려 JSON Schema를 재생성하고 함께 커밋합니다. 백엔드가 그 파일로 DTO를 만듭니다.

## 주의사항

**LLM 캐시 키에 `prompt_version`이 들어갑니다.** 이게 없으면 프롬프트를 고쳤는데 옛날 응답이 계속 나오는 현상으로 하루를 날립니다.

**`llm_call_logs`는 1주차부터 기록합니다.** 나중에 소급이 안 되는데 토큰 비용 관리, 논문 정량 데이터, 알고리즘 명세서 근거, 프롬프트 A/B 비교 네 가지에 전부 쓰입니다.

**`ai` 스키마는 `public` 테이블을 FK로 참조하지 않습니다.** `job_id`는 그냥 숫자 컬럼입니다. Alembic과 Flyway의 배포 순서 의존을 없애기 위함입니다.

**정책 문서 수집이 일정상 가장 오래 걸립니다.** 4주차 작업이지만 문서 확보는 1주차부터 병행합니다.
