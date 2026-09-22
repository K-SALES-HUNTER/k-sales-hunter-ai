# K-Sales Hunter 팀 온보딩 — 무엇을 읽고, 무엇을 하면 되는가

작성 2026-09-13 · 갱신 2026-09-22 (파트 분배를 에이전트 담당 기준으로 정정) · 과업 종료 **2026-10-31 (6주 남음)** · 추석 9/24~26

## 1. 지금 우리 상태 (한 문단)

프론트엔드는 화면이 전부 완성돼 있고 API는 목(mock)입니다. AI 레포는 서버가 뜨고 등록에서 보고서까지 관통하지만, 노드 대부분이 stub 이라 **실제 LLM 을 부르는 곳은 아직 한 군데뿐**입니다. 백엔드(Spring) 레포는 아직 없고, 그때까지는 AI 레포의 `dev_bff` 가 대신합니다.

**남은 6주의 목표는 "프론트의 모든 버튼이 실제 데이터로 동작하는 것"** 하나입니다. 문서(기술결정서·제작설계서)는 참고 자료이고, **프론트에 구현된 화면이 곧 요구사항**입니다. 완성이 우선이라 데이터 수집처럼 무거운 부분은 고정값으로 처리하고, LLM 은 글을 쓰는 곳에만 실제로 붙입니다.

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
| `docs/AI_개발계획_v2.md` | AI 서비스 구조, 잡 모델, 파이프라인, 동기 서비스, 데이터 파일, 일정 | AI 담당 전체, BE 담당은 §0·§2 |
| `docs/TRACEABILITY.md` | 요구사항 ID ↔ 기능 ↔ 화면 ↔ 구현 파일 ↔ 테스트 ↔ 담당 | 전원. 자기 요구사항 행을 직접 갱신 |
| `docs/CONVENTION.md` | 브랜치·커밋·PR 규칙 | 전원 |
| 기술결정서 v1.2 (Notion에 붙여넣은 본문) | 팀 확정 결정. 단 연동 방식·국가 수·일정은 v2가 대체 | AI·BE 담당 |
| 제작설계서 PDF (요구사항정의서·ERD·알고리즘 명세서) | 요구사항 ID, public 테이블 25개, 진입점수 공식, Critic 루프 | BE(ERD), 데이터·문서 담당(알고리즘·산출물) |
| FE 레포 `README.md`, `src/routes/router.tsx`, `src/apis/*.ts` | 화면 라우트와 목 API 함수 | FE 연동하는 사람 |
| AI 레포 `README.md`, `src/app/` | Quick Start, 현재 코드 | AI 담당 |

읽는 순서(30분 코스): 이 문서 → API_SPEC §1 표 → AI_개발계획 §0·§7 → 자기 파트 상세.

## 5. 파트 분배 (4인)

**배정 기준은 에이전트 담당입니다.** 개발보고서의 7개 에이전트를 네 명이 나눠 맡기로 한 원래 합의를 따릅니다.

| 사람 | 담당 에이전트 | 맡은 화면 (프론트 UI) |
|---|---|---|
| 이동건 | 마진 메이커 (R-002) | 마켓설정 · 판매관리 |
| 강근우 | 비서 AI 오케스트레이터 (R-000) · 콘텐츠 아키텍트 (R-003) | 상품등록 · 보고서 · 상세페이지 |
| 차은호 | 트렌드 헌터 (R-001) | 로그인 · 회원가입 · 분석보고서 |
| 권수현 | 크로스보더 통관 (R-004) | 대시보드 · 판매정보 |

원칙 셋을 지켰습니다. AI와 스프링을 네 명이 모두 나눠 갖습니다. 스프링 라우트는 자기가 맡은 화면의 것을 가져갑니다. 프론트 API 연결은 이동건과 강근우가 합니다.

### 이미 한 것

| 사람 | 한 일 |
|---|---|
| 권수현 | **AI 레포 초기 세팅.** docker-compose, `scripts/init_db.sql` DB 권한 격리, Alembic 설정과 초기 마이그레이션, ORM 모델, `core/pricing/engine.py` 골격, LangGraph state 정의, README |
| 이동건 | **AI 레포 실행 정상화.** 계약 스키마 v1, 잡 실행기와 `ai.jobs`, 노드 런타임 데코레이터, LLM 래퍼와 FakeLLM, dev_bff 골격, 그래프 배선(국가 서브그래프), report_compose, 테스트 28건. 팀 문서 4종(온보딩·API 스펙·개발계획 v2·컨벤션) |
| 차은호 | **정책 문서 manifest VN 11건**, 요구사항 추적표 초안, **3개국 소액 면세 폐지 조사와 문서 정정**(마진 과대 계산을 막은 발견) |
| 전원 | **프론트 UI 전체.** 위 표의 화면 담당대로 |

### 남은 일

숫자는 사람·일 추정입니다.

| | 이동건 (마진) | 강근우 (비서AI·상세) | 차은호 (트렌드헌터) | 권수현 (통관) |
|---|---|---|---|---|
| **AI** | margin 노드 critic·explain, engine 보강(수수료 스택·과세기준·3안·민감도), scoring 하위 5지표, `fee_schedules` 3개국, 코파일럿 R-005, report_compose 실 LLM 마무리 **11** | R-000 잔여(부분 재실행), content_graph, sales_suggest·카테고리 JSON, image_gen, 문화 사전 **14** | product_understanding, market_research·프로바이더, market_evaluate(3축·Critic·경쟁가 밴드), market_insight, product_fill **12** | customs_gate, logistics_estimate·배송요율, risk_checklist, RAG 적재·검색 **11** |
| **공통** | dev_bff 보강(uploads 서빙, 대시보드·설정 라우트) **3** | — | — | — |
| **Spring** | settings·stores, 코파일럿 프록시 **4** | detail-page·images·image-jobs **4** | 레포 골격, auth, products·uploads, analysis 프록시·보고서 매핑 **13** | dashboard, sales-info·quote·categories, sales-ops **11** |
| **FE 연결** | 공통 axios·JWT, 로그인, 대시보드, 마켓설정, 판매관리, 분석보고서, AI 패널 **7** | 상품등록·이미지업로드·자동채우기, 로딩 폴링, 판매정보, 상세페이지, 이미지생성 **6** | — | — |
| **산출물 문서** | 마진메이커 명세서 **2** | 상세페이지 명세서 **2** | 시장분석 명세서 **2** | 오케스트레이션 · 데이터 수집처리 정의서 · 배송통관 명세서 **6** |
| **합계** | **27** | **26** | **27** | **28** |

권수현이 가장 많습니다. 산출물 문서 세 개를 맡아서입니다. 데이터 수집처리 정의서를 차은호에게 넘기거나 sales-ops 를 이동건이 가져가면 맞춰집니다. 진행하면서 조정합니다.

### 🟦 이동건 — 마진 메이커
- AI: `nodes/margin.py` 의 critic·explain, `core/pricing/` 의 engine 보강과 scoring 하위 5지표, `data/fee_schedules/{VN,SG,TH}.yaml`, 코파일럿 `core/services/copilot.py`, report_compose 실 LLM 마무리
- 공통: dev_bff 보강. `uploads` 파일 서빙 라우트 누락 버그와 대시보드·설정 라우트
- Spring: settings·stores, 코파일럿 프록시와 `chat_messages`
- FE: 공통 axios·JWT 인터셉터, 로그인, 대시보드, 마켓설정, 판매관리, 분석보고서 폴링, AI 패널
- 문서: 마진메이커 알고리즘 명세서
- 기다림: 권수현의 관세·VAT 값(요율 YAML 채우는 데 필요)

### 🟩 강근우 — 비서 AI 오케스트레이터 · 콘텐츠 아키텍트
- AI: 부분 재실행 `core/graph/rerun_map.py`, `core/graph/content.py`(초안·문화필터·품질검수·현지어), `core/services/sales_suggest.py` 와 `data/shopee_categories/*.json`, `core/services/image_gen.py`, `data/culture/*.yaml`
- Spring: detail-page, images, image-jobs
- FE: 상품등록과 이미지 업로드 진행률, 자동 채우기, 로딩 오버레이 폴링, 판매정보, 상세페이지, 이미지 생성
- 문서: 상세페이지 알고리즘 명세서
- 참고: 오케스트레이터 기반(그래프 배선·러너·report_compose)은 이동건이 이미 만들었습니다. 그 위에서 부분 재실행만 얹으면 됩니다.

### 🟧 차은호 — 트렌드 헌터
- AI: `nodes/product_understanding.py`, `nodes/market_research.py` 와 Tavily 프로바이더, `nodes/market_evaluate.py`(3축 평가·Critic 루프·경쟁가 밴드), `nodes/market_insight.py`, `core/services/product_fill.py`
- Spring: 레포 골격, auth, products·uploads, analysis 프록시와 보고서 매핑
- 문서: 시장분석 알고리즘 명세서
- 인계: 이미 만든 `data/policies/manifest.yaml` 은 통관 담당인 권수현에게 넘깁니다. 목록은 완성됐고 적재·검색 구현만 남았습니다.

### 🟨 권수현 — 크로스보더 통관
- AI: `nodes/customs_gate.py`, `nodes/logistics_estimate.py` 와 `data/shipping_rates/*.yaml`, `nodes/risk_checklist.py`, `core/rag/` 적재·검색·게이트 규칙
- Spring: dashboard, sales-info·quote·categories, sales-ops
- 문서: AI 오케스트레이션 명세서, 데이터 수집처리 정의서, 배송통관 명세서
- 인계받음: 차은호의 정책 문서 manifest VN 11건
- 요청: 관세·VAT 값을 조사하면 이동건에게 넘겨주세요. `fee_schedules` YAML 에 들어갑니다.

### 의존 관계

```
이동건(기반 완료) ──▶ 전원. 노드·서비스는 이 위에 얹는다
차은호(manifest 완료) ──▶ 권수현(RAG 적재·검색)
권수현(관세·VAT 값) ──▶ 이동건(fee_schedules YAML) ──▶ 보고서 마진 숫자 확정
차은호(market_evaluate 경쟁가 밴드) ──▶ 이동건(가격 3안 밴드 클램프)
차은호(Spring 레포 골격) ──▶ 강근우·권수현·이동건(각자 라우트)
강근우(카테고리 JSON) ──▶ 권수현(sales-info 라우트)
이동건·강근우(FE 연결) ◀── 전원의 API
```

## 6. 팀 공통 마일스톤

1주차(9/14~9/20)는 기반 세팅으로 끝났습니다. 남은 6주입니다.

| 주 | 기간 | 팀 데모 기준 |
|---|---|---|
| 2 | 9/22–9/28 (추석 24~26) | 실 LLM 으로 분석 보고서 3개국 생성. 프론트가 dev_bff 에 붙어 등록에서 보고서까지 관통 |
| 3 | 9/29–10/5 | 통관 경고에 근거 조항 표시. 판매 정보 입력과 마진 즉시 재계산 |
| 4 | 10/6–10/12 | 상세페이지 한국어·현지어 생성과 수정. AI 패널 실답변 |
| 5 | 10/13–10/19 | 이미지 AI 생성. 상품 수정 재분석. Spring 이 dev_bff 를 대체 |
| 6 | 10/20–10/26 | 프롬프트 튜닝. 산출물 문서 초안 |
| 7 | 10/27–10/31 | 통합 QA · 리허설 · 최종 문서 |

## 7. 협업 규칙

- 브랜치 `feat/<파트>-<기능>` → `develop` PR → 1인 리뷰 → 머지. `main`은 데모 태그용.
- 커밋 컨벤션은 FE README 표(Feat/Fix/Design/Docs/Refactor/Chore) 3개 레포 공통.
- **API 스펙 변경**: `docs/API_SPEC_FE기준.md` 수정 PR을 먼저 올리고 FE·BE·AI 담당이 승인한 뒤 코드 변경. 선택 필드 추가는 자유, 이름 변경·삭제는 합의.
- 매일 오전 10분: 어제 머지한 것 / 오늘 할 것 / 막힌 것. 주 1회 데모(금요일)로 마일스톤 확인.
- 비밀키(`.env`)는 커밋 금지. OpenAI 키는 이동건이 발급, 일일 토큰 예산 환경변수로 제한.

## 8. 지금 할 일 (2주차)

**전원**: 이 문서 §5 에서 자기 파트 확인 · `docs/TRACEABILITY.md` 에서 자기 요구사항 행 확인 · `docker compose up -d` 와 `make test` 로 레포가 도는지 확인

| 사람 | 이번 주 |
|---|---|
| 이동건 | OpenAI 키로 LLM 래퍼 검증 · dev_bff 보강(uploads 버그·대시보드·설정) · FE 공통 axios 전환 |
| 강근우 | content_graph 프롬프트·스키마 초안 · 카테고리 JSON 형식 확정 · FE 상품등록 연결 |
| 차은호 | 노드 4개 실 LLM 전환 시작(product_understanding · market_evaluate 우선) · Spring 레포 골격 |
| 권수현 | customs_gate 를 quick_rules 로 실판정 · 관세·VAT 값 조사해 이동건에게 전달 |

## 9. 자주 나올 질문

- **Spring이 없는데 FE 연동을 어떻게 테스트하나?** AI 레포의 `dev_bff`가 같은 API를 제공한다. FE `.env`의 `VITE_API_BASE_URL=http://localhost:8000/api/v1`.
- **국가가 3개면 정책 문서도 3배인가?** VN만 깊게, SG/TH는 금지품목 리스트·세율·Shopee 정책 5~10건이면 된다. 없으면 "확인 필요"로 표시된다.
- **마진 숫자가 FE 목과 다르게 나오면?** 정상. 요율 YAML을 FE 목 값으로 시작하면 비슷하게 나오고, 실제 값으로 바꾸면 달라진다. 근거는 응답의 `feeScheduleVersion`·`calcBasis`.
- **LLM 비용은?** 분석 1건(3개국) 약 $0.3~0.6, 상세페이지 $0.1, 이미지 $0.05~0.2. 개발 중엔 FakeLLM과 캐시를 기본으로.
- **결정서와 다른 게 있는데?** `docs/AI_개발계획_v2.md` §0 표가 변경 목록. 나머지는 결정서대로.
