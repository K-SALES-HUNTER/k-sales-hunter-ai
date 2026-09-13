# K-Sales Hunter 팀 온보딩 — 무엇을 읽고, 무엇을 하면 되는가

작성 2026-09-13 · 과업 종료 **2026-10-31 (7주 남음)** · 추석 9/24~26

## 1. 지금 우리 상태 (한 문단)

프론트엔드는 화면이 전부 완성돼 있고 API는 목(mock)입니다. 백엔드(Spring) 레포는 아직 없습니다. AI 레포는 뼈대만 있고 실행이 안 됩니다. 그래서 **남은 7주의 목표는 "FE의 모든 버튼이 실제 데이터로 동작하는 것"** 하나입니다. 문서(기술결정서·제작설계서)는 참고 자료이고, **FE에 구현된 화면이 곧 요구사항**입니다.

## 2. 전체 그림

```
[React FE]  --REST /api/v1/*-->  [Spring BE]  --REST /internal/ai/*-->  [Python AI (FastAPI+LangGraph)]
                                    │  public 스키마 (users, products, reports, sales_infos, detail_pages…)
                                    └──── PostgreSQL(pgvector) + Redis ────┘  ai 스키마 (jobs, llm_call_logs, rag_documents…)
```
- FE는 AI를 직접 부르지 않습니다. 단, **Spring이 생기기 전까지는 AI 레포의 `dev_bff`(개발용 가짜 백엔드)** 가 `/api/v1/*`를 대신 제공합니다. FE는 `.env`의 주소만 바꾸면 됩니다.
- 시간이 오래 걸리는 AI 작업(분석 보고서·상세페이지·이미지)은 **잡(job)** 으로 만들고 FE가 **2초마다 상태를 폴링**합니다. 숫자 계산(마진·배송비)은 즉시 응답하는 동기 API입니다.
- 분석은 **VN·SG·TH 3개국**을 동시에 돌립니다(FE가 3개국 전제).

## 3. 다섯 가지 원칙

1. **FE 타입이 계약이다.** `k-sales-hunter-fe/src/types/*.ts`, `src/mocks/*.ts`의 모양대로 Spring이 응답한다. 필드 이름을 바꾸지 않는다.
2. **숫자는 코드가, 문장은 LLM이.** 마진·배송비·점수는 Python 순수 함수. LLM은 해설·생성만.
3. **근거 없는 판정 금지.** 통관 판정은 출처·기준일이 붙은 문서로만. 없으면 "확인 필요".
4. **작은 단위로 자주 합친다.** `feat/*` → `develop` PR, 1인 리뷰, 하루 1회 이상 머지.
5. **계약(API 스펙) 변경은 문서 먼저.** `docs/API_SPEC_FE기준.md`를 고치는 PR에 FE·BE·AI 담당이 모두 승인.

## 4. 문서 지도 — 누가 무엇을 읽나

| 문서 | 내용 | 꼭 읽을 사람 |
|---|---|---|
| `docs/ONBOARDING.md` (이 문서) | 전체 그림·역할·일정 | 전원 |
| `docs/API_SPEC_FE기준.md` | 화면별 API 목록, 요청/응답 JSON, AI 내부 API, 상태 전이, **FE 수정 목록** | 전원 (FE 담당은 §5, BE 담당은 §2·§4, AI 담당은 §3) |
| `docs/AI_개발계획_v2.md` | AI 서비스 구조, 잡 모델, 파이프라인, 동기 서비스, 데이터 파일, 7주 일정, 1주차 순서 | AI·데이터 담당 전체, BE 담당은 §0·§2 |
| 기술결정서 v1.2 (Notion에 붙여넣은 본문) | 팀 확정 결정. 단 연동 방식·국가 수·일정은 v2가 대체 | AI·BE 담당 |
| 제작설계서 PDF (요구사항정의서·ERD·알고리즘 명세서) | 요구사항 ID, public 테이블 25개, 진입점수 공식, Critic 루프 | BE(ERD), 데이터·문서 담당(알고리즘·산출물) |
| FE 레포 `README.md`, `src/routes/router.tsx`, `src/apis/*.ts` | 화면 라우트와 목 API 함수 | FE 연동하는 사람 |
| AI 레포 `README.md`, `src/app/` | Quick Start, 현재 코드 | AI 담당 |

읽는 순서(30분 코스): 이 문서 → API_SPEC §1 표 → AI_개발계획 §0·§7 → 자기 파트 상세.

## 5. 파트 분배 (4인) — BE+AI를 공평하게, FE 연동 몫은 이동건·강근우

분배 기준: 전체 일감을 대략 사람·일로 셈하면 AI ≈ 56, Spring ≈ 27, FE 연동 ≈ 12, 합계 ≈ 95 → 1인 ≈ 24. 이동건·강근우는 FE 연동을 각 ≈ 6 맡으므로 **BE+AI는 ≈ 18**, 권수현·차은호는 **BE+AI ≈ 24**. 아래 괄호 숫자가 그 추정치입니다. Spring과 AI 둘 다 4명이 나눠 가집니다(한 사람이 한 레포를 통째로 맡지 않음).

| | 이동건 | 강근우 | 권수현 | 차은호 |
|---|---|---|---|---|
| AI | 레포 정상화·contracts·JobRunner(4), LLM 래퍼·FakeLLM·로깅(3), dev_bff(4), copilot tool-calling(4), **report_compose 노드**(진입점수 확정·랭킹·종합 결론)(2) | product_fill(2), sales_suggest+카테고리 JSON(4), content_graph+문화 사전(5), image_gen(3) | pricing 엔진 보강·요율/배송 YAML 3개국·scoring·테스트 벡터(4) | analysis_graph 노드 8개(report_compose 제외)(7), RAG ingest·retriever·gate_rules·정책 문서 수집(7), PARTIAL 재분석(2), evals·산출물 문서(6) |
| Spring | copilot 프록시·chat_messages(2) | detail-page·images·image-jobs(4) | 레포·auth·Flyway·products·uploads(5), analysis 프록시·report 매핑·저장(5), sales-info·shipping·quote·categories(4), dashboard·settings·stores(3), sales-ops 시드·중단·가격·재고(4) | — |
| FE 연동 | 등록→분석 폴링→보고서→AI 패널 (API_SPEC §5의 1·2·4·8) (6) | 이미지 업로드·자동 채우기·판매정보·상세페이지·이미지 생성 (§5의 3·5·6·7·9·10·11) (6) | — | — |
| 합계 | ≈ 25 | ≈ 24 | ≈ 25 | ≈ 22 |

### 🟦 이동건 — AI 기반·dev_bff·코파일럿 + FE 연동(분석/보고서/AI 패널)
- AI: `config`·`errors`·`contracts/v1`·`observability`·`ai.jobs` 마이그레이션·Makefile·CI → **JobRunner**(Semaphore, 상태 갱신, 취소) → **LLM 래퍼**(json_schema·재시도·캐시·`llm_call_logs`·FakeLLM) → `/internal/ai/*` 라우터 + **dev_bff**(auth 목·products·uploads·analysis 폴링·report·copilot) → **copilot**(pricing_quote·search_policy 도구, 추천 프롬프트 12종) → **report_compose 노드**(오케스트레이터 R-000-04: `scoring.profit_score`·`entry_score`로 진입점수 확정, 국가 랭킹·fitGrade, gpt-4o 종합 결론·조사 요약·다음 액션 1회 생성. dev_bff의 report 응답과 직결)
- Spring: `POST /products/{id}/copilot/messages` 프록시 + `chat_messages` 저장 + action → 잡 생성
- FE: 상품 등록 응답 productId, 로딩 오버레이 5단계 폴링·중단, 보고서 202 폴링, AI 패널 API
- 1주차: AI_개발계획 §8의 1·2·3·5·6(배선만)·7. 금요일 "FE 등록→로딩→보고서(목)" 관통.
- 기다림: 권수현의 quote 서비스(1주차 말, 목 YAML), 차은호의 노드 구현(2주차~).

### 🟩 강근우 — AI 생성 서비스·이미지 + Spring 상세페이지 + FE 연동(등록폼/판매정보/상세/이미지)
- AI: **product_fill**(gpt-4o vision, 카테고리 11종) → **sales_suggest** + `data/shopee_categories/{cc}.json` → **content_graph**(usp→draft→문화필터→품질검수→localize) + `data/culture/*.yaml` → **image_gen 잡**(gpt-image-1, 모델 컷 4종, 취소·재생성)
- Spring: detail-page(잡 프록시·content PATCH·재번역), images 업로드/삭제/대표, image-jobs 프록시
- FE: 이미지 업로드 XHR progress, 자동 채우기 인자, 판매정보(quote·카테고리·저장), 상세페이지 폴링·수정·이미지 편집, 이미지 생성 폴링·취소, 세션 스토어 → 서버
- 1주차: product_fill 스키마·프롬프트·FakeLLM fixture, 카테고리 JSON 형식 확정, FE 이미지 업로드 PR. 2주차 product_fill 실 LLM, 3주차 sales_suggest, 4주차 content, 5주차 image + Spring 상세 라우트.
- 기다림: 이동건의 LLM 래퍼·JobRunner(1주차 말), 권수현의 Spring 골격(2주차).

### 🟨 권수현 — Spring 코어 + AI 마진 엔진
- Spring: 레포 생성(Boot 3·JPA·Security/JWT·Flyway) → auth·products·uploads → **analysis 프록시 + report 매핑**(AI result → FE `TotalReport`/`CountryReport`, 표시 문자열 포맷, `reports`·`country_reports`·`price_options` 저장) → sales-info·shipping 저장·quote 프록시·categories → dashboard·settings·stores(목 연동) → sales-ops 시드·판매 중단/재개·가격 변경·재고 추가. `product.countries[]` 상태 계산(API_SPEC §4).
- AI: `core/pricing/` — `fee_schedule.py`·`data/fee_schedules/{VN,SG,TH}.yaml`·`data/shipping_rates/*.yaml`(FE 목 값으로 시작 → 실제 값 조사), `scoring.py`(진입점수·수익성 공식), `engine.py` 보강(수수료 스택·과세기준·3안·민감도), `services/pricing_quote.py`, 테스트 벡터. 잡의 margin 노드와 동기 API가 이 함수를 같이 쓴다.
- 1주차: Spring 레포·auth·products·uploads·Flyway 초기 9테이블 + pricing YAML 3개국(목 값)·quote 서비스·테스트. dev_bff와 응답 비교.
- 기다림: 이동건의 `contracts/v1/*.schema.json`·dev_bff(1주차 말). 차은호의 market_evaluate 결과(priceBand)는 3주차.

### 🟧 차은호 — AI 분석 파이프라인·RAG + 평가·산출물
- AI: **analysis_graph 노드 8개** 실구현(product_understanding, customs_gate, market_research(Tavily), market_evaluate(3축+Critic+부분점수+경쟁가 밴드), market_insight, logistics_estimate, margin(quote 호출+critic+explain), risk_checklist). report_compose는 이동건 담당 — 국가별 결과 스키마(scores·insight·pricing)를 2주차 초에 이동건과 합의 → **RAG**: `data/policies/manifest.yaml`(VN 20~40, SG/TH 5~10), `rag/ingest.py`·`retriever.py`·`gate_rules.py`·`quick_rules/{cc}.yaml`, 문서 번역 검토·VERIFIED 승격 → **PARTIAL 재분석**(`rerun_map.py`) → **evals**(골든 상품 3×3개국, 코파일럿 12건) → 산출물(traceability·알고리즘 명세서·데이터 수집처리 정의서·흐름도·요구사항정의서 비고 수정 요청)
- 1주차: 노드 8개 stub(fixture 반환)로 그래프 관통(이동건 배선 위에), 정책 manifest VN 10건, traceability 표 초안. 2주차 실 LLM 노드, 3주차 RAG·게이트, 5주차 PARTIAL, 6주차 evals·문서.
- 기다림: 이동건의 LLM 래퍼·runtime(1주차 말), 권수현의 pricing_quote(1주차 말).

### 의존 관계 한눈에

```
1주차  이동건(레포·runtime·LLM래퍼·dev_bff) ──▶ 차은호(노드), 강근우(product_fill), 권수현(스펙 확인)
       권수현(pricing_quote·YAML) ──▶ 차은호(margin 노드), 강근우(판매정보 quote), 이동건(copilot 도구)
2주차  차은호(실 LLM 노드) ──▶ 이동건(report_compose 실 LLM) ──▶ 권수현(report 매핑), 이동건(FE 보고서 연동)
3주차  차은호(RAG·게이트) ──▶ 이동건(copilot search_policy)
       강근우(카테고리 JSON·sales_suggest) ──▶ 권수현(sales-info 라우트)
4~5주  권수현(Spring 코어) + 강근우(Spring 상세) + 이동건(Spring copilot) ──▶ dev_bff 대체, FE 주소 전환
6주차  차은호(evals·문서) ◀── 전원(파트별 명세)
```

## 6. 팀 공통 마일스톤

| 주 | 기간 | 팀 데모 기준 |
|---|---|---|
| 1 | 9/14–9/20 | FE에서 상품 등록 → 로딩(실제 단계) → 보고서가 **목 데이터로** 뜬다 (dev_bff) |
| 2 | 9/21–9/27 | 실 LLM 분석 보고서 3개국, AI 자동 채우기 동작 |
| 3 | 9/28–10/4 | 통관 경고에 근거 조항, 판매 정보 입력(추천·저장·마진 즉시 재계산) |
| 4 | 10/5–10/11 | 상세페이지 ko/현지어 생성·수정, AI 패널 실답변 |
| 5 | 10/12–10/18 | 이미지 AI 생성, 상품 수정 재분석, Spring 실연동 시작 |
| 6 | 10/19–10/25 | evals·튜닝, 산출물 문서 초안 3종 |
| 7 | 10/26–10/31 | 통합 QA·리허설·최종 문서 |

## 7. 협업 규칙

- 브랜치 `feat/<파트>-<기능>` → `develop` PR → 1인 리뷰 → 머지. `main`은 데모 태그용.
- 커밋 컨벤션은 FE README 표(Feat/Fix/Design/Docs/Refactor/Chore) 3개 레포 공통.
- **API 스펙 변경**: `docs/API_SPEC_FE기준.md` 수정 PR을 먼저 올리고 FE·BE·AI 담당이 승인한 뒤 코드 변경. 선택 필드 추가는 자유, 이름 변경·삭제는 합의.
- 매일 오전 10분: 어제 머지한 것 / 오늘 할 것 / 막힌 것. 주 1회 데모(금요일)로 마일스톤 확인.
- 비밀키(`.env`)는 커밋 금지. OpenAI 키는 이동건이 발급, 일일 토큰 예산 환경변수로 제한.

## 8. 첫 주 체크리스트

**전원**: 이 문서 + API_SPEC §1 읽기 · 3개 레포 클론 · `docker compose up -d`로 Postgres/Redis 확인
**이동건**: `uv pip install -e ".[dev]"` 성공 · runtime·JobRunner·LLM 래퍼(Fake) · report_compose stub · dev_bff로 FE 등록→보고서(목) 관통 · `contracts/v1/*.json` 공유
**강근우**: product_fill 스키마·프롬프트·fixture PR · 카테고리 JSON 형식 확정 · FE 이미지 업로드 XHR PR
**권수현**: Spring 레포 + Flyway 초기 스키마 + auth/products/uploads · 3개국 fee/shipping YAML(목 값)·`pricing_quote`·테스트 벡터 PR
**차은호**: 노드 8개 stub PR(그래프 END 도달) · policies manifest VN 10건 · traceability 표 초안

## 9. 자주 나올 질문

- **Spring이 없는데 FE 연동을 어떻게 테스트하나?** AI 레포의 `dev_bff`가 같은 API를 제공한다. FE `.env`의 `VITE_API_BASE_URL=http://localhost:8000/api/v1`.
- **국가가 3개면 정책 문서도 3배인가?** VN만 깊게, SG/TH는 금지품목 리스트·세율·Shopee 정책 5~10건이면 된다. 없으면 "확인 필요"로 표시된다.
- **마진 숫자가 FE 목과 다르게 나오면?** 정상. 요율 YAML을 FE 목 값으로 시작하면 비슷하게 나오고, 실제 값으로 바꾸면 달라진다. 근거는 응답의 `feeScheduleVersion`·`calcBasis`.
- **LLM 비용은?** 분석 1건(3개국) 약 $0.3~0.6, 상세페이지 $0.1, 이미지 $0.05~0.2. 개발 중엔 FakeLLM과 캐시를 기본으로.
- **결정서와 다른 게 있는데?** `docs/AI_개발계획_v2.md` §0 표가 변경 목록. 나머지는 결정서대로.
