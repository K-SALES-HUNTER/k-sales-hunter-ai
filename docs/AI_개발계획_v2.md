# AI 개발 계획 v2 — FE 구현 기준, 결과물 우선 구조

작성: 2026-09-13. 전제: **문서(결정서·설계서)는 참고, FE에 구현된 화면과 동작이 요구사항.** 백엔드(Spring)는 아직 없고 7주 남았다. 목표는 "FE의 모든 AI 관련 버튼이 실제로 동작하는 것"이다. 이 문서가 `02_AI_개발_가이드.md`의 **연동 방식·우선순위·일정을 대체**한다. 02의 노드 스펙·RAG·pricing·테스트 섹션은 그대로 유효하다. API 계약은 `04_FE기준_API_설계.md`.

---

## 0. 결정서 대비 바꾼 것과 이유

| 항목 | 결정서 v1.2 | v2 (채택) | 이유 |
|---|---|---|---|
| 진행 이벤트 | Redis Pub/Sub → Spring SSE 릴레이, seq | **폴링** `GET /analysis-jobs/{id}` 2초 | FE에 SSE 코드가 없고 오버레이는 5단계 표시가 전부. Pub/Sub·SSE·seq 3개 컴포넌트 삭제 |
| 결과 전달 | 콜백 REST + Idempotency-Key + 재시도 + job_results 보관 | **`ai.jobs` 테이블에 저장, Spring이 GET으로 회수** | 콜백·멱등성·재시도 코드 전부 불필요. Spring이 없어도 결과가 남는다 |
| 국가 | VN 단일 | **VN·SG·TH 3개 fan-out** | FE 트리·카드·랭킹·"3개 국가 동시" 문구가 3개국 전제. 코드 차이는 없고 데이터(요율·정책 문서)만 국가별 파일 |
| 마진 계산 | 분석 잡 안의 노드 | 노드 **+ 동기 API `pricing/quote`** | FE의 배송/포장 저장, 최종가 입력, 가격 관리 "예상 영향"이 즉시 재계산을 요구. LLM 없는 순수 계산이므로 ms 응답 |
| 판매정보 추천 | 언급 없음 | 동기 `sales-info/suggest` | FE 옵션·재고 섹션의 "AI가 자동으로 값을 채움" |
| 이미지 생성 | 범위 밖 | **image-job (gpt-image-1)** | FE에 화면 4상태·재생성·모델 컷 4종이 완성돼 있음. 데모에 반드시 나온다 |
| 코파일럿 | intent → changePlan 반환, Spring이 재실행 | **tool-calling 답변** (pricing_quote, search_policy 도구) + 명령 3종만 action | FE 패널은 텍스트 답변만 표시. changePlan 확인 UI가 없다. "가격 낮추면 마진?" 같은 질문은 도구 호출로 정확히 답한다 |
| 실행 모델 | FastAPI + asyncio Semaphore(3) | 동일 | 유지 |
| LLM 스키마/계약 분리, pricing 순수, RAG pgvector, llm_call_logs | 동일 | 유지 | |

Spring이 없는 동안: **`entrypoints/dev_bff.py`** — 04 문서의 FE용 엔드포인트를 그대로 구현한 개발용 BFF(SQLite/인메모리 + 로컬 파일 업로드 + JWT 목). FE가 `VITE_API_BASE_URL`만 AI 서버로 바꾸면 **지금 바로 실연동**된다. Spring이 완성되면 같은 API 스펙이므로 URL만 되돌린다. 백엔드 담당자에게는 "실행 가능한 API 명세" 역할.

---

## 1. 서비스 구성

```
FastAPI (단일 프로세스, uvicorn)
├─ /internal/ai/*      ← Spring이 호출하는 진짜 API (§3)
├─ /api/v1/*           ← dev_bff (개발용, Spring 대체. 운영에선 끔)
├─ JobRunner           ← asyncio.create_task + Semaphore(3), ai.jobs 상태 갱신
└─ core/
   ├─ graph/analysis    (3개국 fan-out, 9노드)
   ├─ graph/content     (상세페이지 생성·검수)
   ├─ services/         ← 동기 서비스: product_fill, pricing_quote, sales_suggest, copilot, image_gen, sales_insight
   ├─ pricing/          (engine, fee_schedule, scoring, scenarios)  ★LLM 금지
   ├─ rag/              (ingest, retriever, gate_rules)
   ├─ providers/        (market: mock|tavily, fx: mock|exchangerate, image: openai)
   └─ agents/           (prompts/*.md, schemas.py, mappers.py)
data/
├─ fee_schedules/{VN,SG,TH}.yaml     수수료·관세·VAT·과세기준·버전
├─ shipping_rates/{VN,SG,TH}.yaml    직배송/SLS 무게구간 요율·ETA
├─ shopee_categories/{VN,SG,TH}.json 카테고리 트리 + 속성 스키마 (정적 스냅샷)
├─ culture/{VN,SG,TH}.yaml           금기어·과장 표현
├─ policies/manifest.yaml            RAG 수집 대상 (VN 우선, SG/TH 최소)
└─ fixtures/                         골든 상품 3개 + FakeLLM 응답
```

## 2. 잡 모델 — `ai.jobs` (마이그레이션 1개 추가, `job_results` 삭제)

| 컬럼 | 타입 | 비고 |
|---|---|---|
| job_id | varchar PK | Spring 발번 `a_12_1` / `c_12_VN_1` / `i_…` |
| job_type | ANALYSIS / CONTENT / IMAGE | |
| status | QUEUED / RUNNING / COMPLETED / FAILED / CANCELLED | |
| step | GATE / MARKET / SHIPPING / MARGIN / REPORT (content: DRAFT / REVIEW / LOCALIZE) | FE 오버레이 단계 |
| progress | float | |
| country_states | jsonb | `{VN:{status,step}}` |
| request | jsonb | 입력 원본 (재실행·디버그) |
| result | jsonb | 완료 시 |
| error_code / error_detail | | |
| llm_cost_usd, created_at, started_at, finished_at | | |

노드 경계마다 `step/progress/country_states` UPDATE. 취소는 Redis `ai:cancel:{jobId}` 또는 DB `status=CANCEL_REQUESTED` 확인(Redis 없이도 되게 DB 우선). 프로세스 재시작 시 RUNNING인 잡은 FAILED(INTERRUPTED)로 마킹 — 체크포인트 재개는 시간 남으면.

**노드 → UI step 매핑**

| step(FE 오버레이) | 노드 | 에이전트 표시 |
|---|---|---|
| GATE "판매 가능 여부 확인" | product_understanding, customs_gate | 리스크 매니저 |
| MARKET "시장·경쟁 분석 (3개 국가 동시)" | market_research, market_evaluate(3축+Critic+부분점수), market_insight | 트렌드 헌터 |
| SHIPPING "배송비·관세 계산" | logistics_estimate | 리스크 매니저 |
| MARGIN "적정 가격·마진 계산" | margin(calc→critic→explain), risk_checklist | 마진 메이커 |
| REPORT "보고서 정리" | report_compose(진입점수 확정·랭킹·종합 결론) | 비서 AI |

잡 전체 step은 "가장 느린 국가"의 step. `etaSeconds`는 노드별 평균 소요(측정값)로 계산.

## 3. 파이프라인 (analysis_graph) — 02 §5 스펙 유지, 차이만

- `_fan_out`은 `countries` 3개를 `Send`. 국가별 데이터 파일이 없으면 그 국가는 `NEEDS_REVIEW`로 끝내되 잡은 성공.
- `customs_gate`: VN은 RAG(VERIFIED 문서), SG/TH는 문서가 적으므로 **Shopee 금지품목 리스트 + 카테고리 규칙표(`data/policies/quick_rules/{cc}.yaml`)** 를 1차로 보고 RAG는 보강. 문서 0건이면 UNKNOWN→NEEDS_REVIEW(FE엔 노출, warnings에 "근거 문서 확인 필요").
- `market_research`: Tavily 쿼리 템플릿 국가별(`"{product} shopee {country} price"`, `"{category} trend {country} 2026"`). Mock provider는 3개국 fixture.
- `market_evaluate`: 3축 LLM(gpt-4o-mini, evidence 필수) + Critic ≤2회 + `scoring.market_partial`. 경쟁가 밴드(low/mid/high KRW + 3구간 가중치)는 수집된 가격 샘플의 25/50/75 분위로 코드 계산 → FE `priceTiers`·`priceMarker`.
- `margin`: `pricing_quote` 서비스를 그대로 호출(잡과 동기 API가 **같은 함수**를 쓴다). 3안: mid=목표마진 역산을 밴드에 클램프, low=밴드 25분위, high=75분위.
- `report_compose`: profit_score → entry_score → rank → fitGrade(1위&FIT=VERY_FIT…) → gpt-4o 종합 결론 1회. `investigationSummary`·`nextAction`도 여기서.
- PARTIAL: `previousResult`를 받아 changedFields→노드 의존표(`rerun_map.py`)로 시작 노드 결정, 그 이전 노드 산출물은 previousResult에서 복원. 체크포인터 불필요.

## 4. 동기 서비스 4개 (FE 버튼과 1:1)

### 4-1. `product_fill` — 상품 등록 "자동 채우기"
입력 `{name, category, description, sellingPoints, mainTarget, imageUrls[]}`. 이미지 ≤4장 1024px 리사이즈 → gpt-4o vision 1회, json_schema `{category(11종 enum), description(≤200자), sellingPoints("A · B · C" 형식), mainTarget, features{colors,materials,shape,style}, keywords[], kTrendCategory, confidence}`. 카테고리 enum은 FE `CATEGORY_OPTIONS` 11종 그대로. 이미지 없고 이름만 있으면 텍스트만으로. 응답 ≤10초, 캐시 키 = 입력 해시.

### 4-2. `pricing_quote` — 배송/포장 저장·최종가 입력·가격 관리 영향표
입력 `{country, product{supplyCostKrw, weightG, packaging?}, shippingMethod?, price? (KRW or local), targetMarginRate?, fixedCostKrw?, fxOverride?}`
처리: shipping_rates 조회(포장 무게 우선, 없으면 weightG×1.15) → fee_schedule → `engine.calculate` → costRows(FE 순서 고정: 판매가/공급 원가/Shopee 수수료/국제 배송비/관세(x%)/VAT(y%)/예상 순이익) → price 없으면 3안 생성.
출력 `{shippingOptions[], quote{priceKrw, priceLocal, netProfitKrw, marginRate, breakevenUnits|null, costRows[]}, scenarios[3]?, fx{…}, feeScheduleVersion, appliedBadges[]}`. 결정론·ms 단위·테스트 벡터로 고정. `fixedCostKrw=0`이면 BEP null → Spring이 "—" 표시(FE는 `breakevenUnits.toLocaleString()`을 호출하므로 Spring이 0 또는 문자열 처리 필요 — FE 타입은 number. **가정: 고정비 미입력 시 Spring이 기본 고정비(예: 월 광고·포장 50만원)를 적용**, 04 문서 `marginBasis.fixedCostKrw`로 노출).

### 4-3. `sales_suggest` — 판매 정보 "AI가 자동으로 값을 채움"
입력 `{country, product, productFeatures?, categoryId?}`. `data/shopee_categories/{cc}.json`에서 후보 leaf 5개를 키워드 매칭으로 추린 뒤 gpt-4o-mini가 1개 선택 + 해당 카테고리 속성 스키마(브랜드/모델/소재/제조국/보증 등)에 값 채움 + 옵션 1·2단 이름·값 추천(뷰티면 용량/색상, 굿즈면 종류/구성). 출력은 FE `categoryAttrs`, `optionLevel1/2` 형태. 재고 힌트(옵션당 초기 재고 제안)는 텍스트 한 줄.

### 4-4. `copilot` — AI 패널
입력 `{message, page{type, countryCode}, context{report|salesInfo|detail 요약 JSON}, history[≤10], product, marketProfile}`.
gpt-4o + tools:
- `pricing_quote(price, shippingMethod)` → "가격 낮추면 마진?" "추천 가격 근거" 류를 실제 숫자로.
- `search_policy(country, query)` → "이 국가 관세 알려줘" 류를 근거 문서로.
- `get_report_section(section)` → 컨텍스트가 클 때 필요한 부분만.
의도 분류는 별도 호출 없이 시스템 프롬프트에서: 명령 3종(다른 국가 분석 추가 / 보고서·상세 재생성 / 입력 정보 수정)이면 `action{type, params}`를 구조화 출력에 포함하고, 답변 문장은 "○○를 시작할게요. 완료되면 보고서가 갱신됩니다." 형식. 그 외는 QUERY. Spring이 action을 받으면 잡을 만든다(dev_bff도 동일). 답변 ≤600자, 페이지 추천 프롬프트(FE 상수) 12종은 골든 테스트 케이스로.

### 4-5. `image_gen` (잡) — 상세/상품 이미지 AI 생성
입력: FE `GenerateImageParams` + 레퍼런스 이미지 URL들(선택한 보유 사진 + 업로드). OpenAI `images.edit`(gpt-image-1, 참조 이미지 다중 입력) 1장 1024×1024. `mode=model`이면 `data/models.yaml`의 4종 페르소나 문장(20대 여성 동아시아 …)을 프롬프트 앞에 결합, `target=detail`이면 "인포그래픽/상세 컷" 스타일 지시. 결과는 `uploads/`(dev) 또는 S3(Spring이 URL 발급 시)에 저장하고 URL 반환. 20~40초 → 잡+폴링, 취소 시 태스크 cancel. 비용 ~$0.05~0.2/장, 일일 상한 환경변수.

### 4-6. `sales_insight` (선택, P3)
주문·재고·가격 통계 → gpt-4o-mini 한 줄 요약 4개(headline/description/performanceNote/priceNote) + 가격 영향표의 "판매량 ±x% 예상"(탄력성 상수 기반 규칙, LLM 아님). Spring 시드 데이터로 데모.

## 5. content_graph — 상세페이지 잡
입력: product + salesInfo(확정값: 카테고리·속성·옵션·최종가·배송·재고) + 국가별 분석 요약(positioning·keywords·usp) + marketProfile(톤) + locale(VN=vi, SG=en, TH=th).
```
usp_extract(캐시) → draft_ko(gpt-4o: name, usps[4], description(소개·특징·혜택·구매유도 4단락), specs[[k,v]] 10행 내외, breadcrumb)
→ culture_filter(사전 + gpt-4o-mini) → quality_check(코드: 금지어·상표권·과장·필수누락 → 0~100) → [≥70] localize(gpt-4o: local 언어 동일 구조) → END
→ [<70 && n<2] draft_ko(지적 주입) / [else] NEEDS_REVIEW로 종료(그래도 결과는 준다)
```
Spring/dev_bff가 price·shipping·options·stockNote를 ko/local에 채워 FE `PdpContent` 완성. `PATCH content`의 `retranslate`는 gpt-4o-mini 번역 1회.

## 6. 국가별 데이터 파일 (코드보다 먼저 확보할 것)

| 파일 | VN | SG | TH | 출처 |
|---|---|---|---|---|
| fee_schedules | 커미션 4~9%(카테고리), 거래 5%, 결제 2%, 관세 MFN/VKFTA, VAT 10%, de minimis | 커미션, GST 9%, 관세 0% | 커미션, 관세 ~10%, VAT 7%, ฿1,500 기준 | Shopee 셀러센터 수수료 공지, ASEAN Tariff Finder |
| shipping_rates | SLS·직배송 무게구간(0.5kg 단위) 요율·ETA | 〃 | 〃 | Shopee SLS 요율표, 우체국 EMS/K-Packet |
| shopee_categories | 뷰티·굿즈·생활 등 FE 11종 카테고리에 대응하는 leaf 30~50개 + 속성 스키마 | 〃 | 〃 | Shopee 카테고리 트리(셀러센터 수동 캡처 → JSON) |
| policies (RAG) | 금지·제한 품목, 화장품 CPN, 세관 절차, 반품 정책, Shopee VN 정책 20~40건 | 금지 품목·GST·IMDA 5~10건 | 금지 품목·FDA·관세 5~10건 | 각국 세관, Shopee 정책 페이지 |
| culture | 금기·과장 표현 사전 | 〃 | 〃 | 직접 작성 |
FE 목 값(VN 관세 6%/VAT 10%, SG 0%/GST 9%, TH 10%/7%, 배송 USD 4.5/6.8 등)을 **초기 YAML 값**으로 넣어 두면 화면이 목과 비슷하게 나와 데모 일관성이 좋다. 실제 값은 기획 확인 후 교체.

## 7. 우선순위와 7주 일정 (FE 데모 관통 순서대로)

| 주 | 기간 | 만드는 것 | 데모 가능 상태 |
|---|---|---|---|
| 1 | 9/14–9/20 | 레포 정상화(config·errors·contracts·logging·`ai.jobs` 마이그레이션·Makefile·.env.example), FakeLLM·Mock provider, **pricing_quote + fee/shipping YAML 3개국 + 테스트 벡터**, JobRunner, analysis_graph 9노드 stub 관통, `/internal/ai/*` 라우터, **dev_bff 1차**(auth 목·products·uploads·analysis 폴링·report) | FE `.env`를 AI 서버로 바꾸면 상품 등록 → 로딩 5단계(실제 진행) → 글로벌/국가 보고서가 **목 데이터로** 뜬다 |
| 2 | 9/21–9/27 (추석 24~26) | LLM 래퍼(로깅·캐시·예산), **product_fill**, market_research(Tavily)·market_evaluate(3축+Critic)·market_insight·margin_explain·report_compose 실 LLM, FX provider | 실 LLM 분석 보고서 3개국 |
| 3 | 9/28–10/4 | RAG ingest + VN 문서 적재, customs_gate·risk_checklist 실데이터(SG/TH는 quick_rules), **sales_suggest** + shopee_categories JSON, dev_bff 판매정보·shipping 저장, FE 연동 항목 1~7 지원 | 판매 정보 입력까지 실동작, 통관 경고에 근거 조항 |
| 4 | 10/5–10/11 | **content_graph** + 품질 루프 + localize, dev_bff detail-page·content PATCH·이미지 업로드, **copilot** tool-calling(12개 추천 프롬프트 골든) | 상세페이지 ko/vi 생성·수정, AI 패널 실답변 |
| 5 | 10/12–10/18 | **image_gen 잡**(gpt-image-1, 모델 컷 4종), PARTIAL 재분석(상품 수정·포장 변경), sales_insight, Spring 실연동(준비되면 dev_bff와 병행 검증) | FE 전 화면 AI 버튼 동작. 등록→승인 전 구간 |
| 6 | 10/19–10/25 | evals(골든 상품 3개 × 3개국 + 코파일럿 12건), 프롬프트 튜닝, 산출물 문서(알고리즘 명세서·데이터 수집처리 정의서·흐름도) | 산출물 초안 |
| 7 | 10/26–10/31 | 통합 QA, 비용·타임아웃 튜닝, 리허설, 최종 문서 | 종료 |

리스크: ① 국가별 데이터 파일(§6) — 1주차부터 기획과 병행, FE 목 값으로 임시 채움 ② Spring 부재 — dev_bff가 데모를 책임짐 ③ 이미지 생성 비용·시간 — 일일 상한 + 데모용 캐시.

## 8. 1주차 상세 (다음 세션 착수 순서)

1. `pyproject` 보정(openai, python-dotenv, tiktoken, tenacity, pyyaml, pillow, aiosqlite, python-multipart, python-jose) → `.env.example` → `Makefile`.
2. `app/config.py`, `app/errors.py`, `contracts/v1/{enums,jobs,analysis,content,image,sync}.py`(camelCase alias), `observability/logging.py`.
3. `infra/models.py`에 `Job` 추가, `job_results` 제거 마이그레이션.
4. `core/pricing/fee_schedule.py`(YAML 로더) + `data/fee_schedules/*.yaml` + `data/shipping_rates/*.yaml` + `core/pricing/scoring.py` + `core/services/pricing_quote.py` + `tests/unit/pricing/*`(FE 목 VN 케이스 재현).
5. `infra/llm.py`(FakeLLM 포함), `core/providers/{mock,tavily,fx}.py`.
6. `core/graph/runtime.py` + 노드 9개(stub은 fixture 반환) + `analysis.py` 배선 + `core/jobs/runner.py`.
7. `entrypoints/http.py`(`/internal/ai/*`) + `entrypoints/dev_bff.py`(auth·products·uploads·analysis·report·categories) + `scripts/generate_contracts.py`.
8. FE에서 `VITE_API_BASE_URL=http://localhost:8000/api/v1`로 등록→보고서 관통 확인. 이 시점의 dev_bff 스펙을 백엔드 담당자에게 전달.
