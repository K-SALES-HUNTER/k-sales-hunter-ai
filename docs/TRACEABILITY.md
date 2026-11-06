# 요구사항 추적표 (traceability) — 초안 v0.1

요구사항 ID → 기능 → 화면 → 구현 → 검증을 한 줄로 잇는다.
한이음 산출물(요구사항 정의서 비고란·시험 결과서)의 근거가 되는 표다.

- 기준 문서: `명세서정리.md`(F-01~F-43 · R-000~R-006), `docs/AI_개발계획_v2.md`, `docs/API_SPEC_FE기준.md`
- 범위: AI 레포(`k-sales-hunter-ai`)가 구현하는 요구사항. Spring·FE 담당 항목은 "구현" 칸에 레포명만 적는다.
- 상태: `stub`(임시값 반환) · `구현`(실동작) · `미착수` · `범위외`
- 작성: 차은호 · 갱신 2026-09-22 (담당 열을 에이전트 배정 기준으로 정정) · 2026-10-04 강근우 (R-000-05 · R-003 절 추가)
- 담당 기준: **에이전트 담당자**(동건 마진메이커 / 근우 비서AI·상세페이지 / 은호 트렌드헌터 / 수현 통관).
  이미 구현이 끝난 행은 실제 구현자를 적고, 남은 작업은 에이전트 담당자를 적는다.

## 1. 분석 파이프라인 (R-000 비서 AI 오케스트레이터)

| 요구사항 | 내용 | 기능 | 화면 | 구현 | 검증 | 상태 | 담당 |
|---|---|---|---|---|---|---|---|
| R-000-01 | 노드 순서 오케스트레이션 (gate→market→shipping→margin→report) | F-16 | SYS-01-01 | `core/graph/analysis.py` | `test_analysis_graph.py::test_모든_노드를_거친다` | 구현 | 이동건 |
| R-000-02 | 게이트 우선 — PROHIBITED 면 이후 노드 생략 | F-14 | SYS-01-01 | `core/graph/analysis.py` · `nodes/customs_gate.py` | `test_통관_차단이면_이후_노드를_건너뛴다` | 구현 (분기) / 판정은 stub | 이동건(분기 완료) · 권수현(판정) |
| R-000-03 | 국가 fan-out 병렬 실행 후 State 병합 | F-16 | RPT-01-01 | `core/graph/analysis.py` | `test_3개국이_모두_끝까지_돈다` · `test_국가_하나가_실패해도_나머지는_끝난다` | 구현 | 이동건 |
| R-000-04 | 결과 종합 · 진입점수 확정 · 국가 랭킹 | F-18 | RPT-01-01 | `nodes/report_compose.py` · `core/pricing/scoring.py` | `test_진입점수와_순위가_확정된다` | stub | 이동건 |
| R-000-05 | 부분 재실행 — 변경 필드별 영향 범위 판정 | F-42 | EDT-01-01 | `core/graph/rerun_map.py` · `core/graph/analysis.py` (`_entry`·`_fan_out`) | `test_partial_rerun.py::test_원가만_바꾸면_마진부터_다시_돈다` 외 7건 · `test_dev_bff_flow.py::test_원가를_고치면_변경내역과_부분_재분석을_준다` | 구현 | 강근우 |
| R-000-07 | 세션·중단 — 진행 중 노드 취소 | F-42 | SYS-01-01 | `core/jobs/runner.py` | — | 구현 | 이동건 |

## 2. 시장 분석 (R-001 트렌드 헌터)

| 요구사항 | 내용 | 기능 | 화면 | 구현 | 검증 | 상태 | 담당 |
|---|---|---|---|---|---|---|---|
| R-001-02 | 상품 이해 — 시각 특징·키워드·카테고리 추출 | F-10 | PRD-01-01 | `nodes/product_understanding.py` · `core/services/product_fill.py` | — | stub | 차은호 |
| R-001-03 | 국가별 시장 데이터 수집 (경쟁 상품·가격·키워드) | F-15 | RPT-02-01 | `nodes/market_research.py` · `core/providers/` | — | stub (mock provider) | 차은호 |
| R-001-05 | 진입 적합성 4축 가중합 (수요·경쟁·K적합·수익성) | F-16 | RPT-01-01 · RPT-02-01 | `nodes/market_evaluate.py` · `core/pricing/scoring.py` | `test_scoring.py::test_시장_3축_가중합_공식` 외 | stub (점수 공식은 구현) | 차은호 |
| R-001-06 | 경쟁 환경 분석 · 경쟁가 밴드(25/50/75 분위) | F-17 | RPT-02-01 | `nodes/market_evaluate.py` | — | stub | 차은호 |
| R-001-07 | 국가별 소비 트렌드 요약 | F-19 | RPT-02-01 | `nodes/market_insight.py` | — | stub | 차은호 |
| R-001-08 | 전략적 포지셔닝 제안 (입문/프리미엄/팬덤/선물) | F-19 | RPT-02-01 | `nodes/market_insight.py` | — | stub | 차은호 |
| R-001-09 | 대시보드 판매 성과 집계 | F-38 · F-39 | DSH-01-01 | Spring 레포 | — | 범위외 | 권수현 |

## 3. 수익 계산 (R-002 마진 메이커)

| 요구사항 | 내용 | 기능 | 화면 | 구현 | 검증 | 상태 | 담당 |
|---|---|---|---|---|---|---|---|
| R-002-03 | 비용 스택 합산 (수수료·배송비·관세·VAT) | F-23 | RPT-02-01 | `core/pricing/engine.py` · `core/services/pricing_quote.py` | `test_analysis_graph.py::test_국가별_비용_구조가_프론트_표_순서와_같다` | 구현 | 이동건 |
| R-002-04 | 환율 적용 (현지통화 ↔ KRW) | F-21 | RPT-02-01 | `core/providers/` (FxProvider) | — | mock | 이동건 |
| R-002-05 | 적정 판매가 · 개당 순이익 산출 (3안) | F-22 | RPT-02-01 | `core/pricing/engine.py` · `nodes/margin.py` | — | 구현 / 3안·민감도 보강 필요 | 이동건 |
| R-002-08 | 손익분기 분석 · 반영 비용 항목 표기 | F-23 | RPT-02-01 | `core/pricing/engine.py` · `core/services/pricing_quote.py` | — | 구현 | 이동건 |
| R-002-09 | 마진 검증 (순이익 음수·마진율 10% 미만 판정) | F-23 | RPT-02-01 | `nodes/margin.py` (critic) | — | stub | 이동건 |
| R-002-10 | 마진 결과 해설 문장 생성 | F-23 | RPT-02-01 | `nodes/margin.py` (explain) | — | stub | 이동건 |

> 확인 필요: R-002-09/10 의 원문 문구는 요구사항 정의서에서 아직 확인하지 못했다. 코드 주석(`nodes/margin.py`) 기준으로 적어 두었고, 정의서 확정 시 교체한다.

## 4. 통관 · 물류 리스크 (R-004 리스크 매니저)

| 요구사항 | 내용 | 기능 | 화면 | 구현 | 검증 | 상태 | 담당 |
|---|---|---|---|---|---|---|---|
| R-004-01 | 배송 방식 추천 (직배송 / Shopee SLS) | F-20 | RPT-02-01 | `nodes/logistics_estimate.py` | — | 구현 | 권수현 |
| R-004-02 | 무게 구간별 배송비 산출 | F-20 | RPT-02-01 | `core/pricing/shipping_rate.py` · `data/shipping_rates/*.yaml` | — | 구현 / YAML 미작성 | 권수현 |
| R-004-03 | 통관 가능 여부 판정 + 근거 조항 표시 | F-14 · F-43 | RPT-02-01 | `nodes/customs_gate.py` · `core/rag/gate_rules.py` | `test_통관_차단이면_이후_노드를_건너뛴다` | stub | 권수현 |
| R-004-04 | 금지·제한 품목 매치 | F-14 | RPT-02-01 | `nodes/customs_gate.py` · `data/policies/quick_rules/{cc}.yaml` | — | stub | 권수현 |
| R-004-05 | 통관 처리 주의사항 체크리스트 | F-14 | RPT-02-01 | `nodes/risk_checklist.py` | — | stub | 권수현 |
| R-004-06 | 반품 리스크 안내 | F-14 | RPT-02-01 | `nodes/risk_checklist.py` | — | stub | 권수현 |
| R-004-07 | 운영 난이도 판정 | F-14 | RPT-02-01 | `nodes/risk_checklist.py` | — | stub | 권수현 |
| R-004-08 | 판정 근거 원문·출처·기준일 보존 | F-43 | RPT-02-01 | `infra/models.py::RagDocument` · `contracts/v1/analysis.py::Evidence` · `data/policies/manifest.yaml` | `test_policy_manifest.py` | manifest 완료 / 적재 미착수 | 권수현 (manifest 초안 차은호) |
| R-004-10 | 포장 완료 기준 치수 입력 | F-20 | SEL-01-01 | `contracts/v1/analysis.py::Packaging` | — | 구현 | 권수현 |

## 5. 콘텐츠 생성 · 판매 정보 (R-003 콘텐츠 아키텍트)

| 요구사항 | 내용 | 기능 | 화면 | 구현 | 검증 | 상태 | 담당 |
|---|---|---|---|---|---|---|---|
| R-003-12 | Shopee 카테고리 추천 (leaf, 국가별 경로) | F-29 | SEL-01-01 | `core/services/sales_suggest.py` · `core/catalog/shopee_categories.py` · `data/shopee_categories/{VN,SG,TH}.json` | `test_sales_suggest.py::test_시연_상품은_캐릭터_인형으로_채운다` · `test_키워드로_후보를_추린다` · `test_후보_밖_카테고리를_고르면_1순위로_바꾸고_값을_버린다` | 구현 (카테고리 스냅샷 43종, shopeeId 미확인) | 강근우 |
| R-003-13 | 카테고리 속성·옵션 1·2단 추천 (2단·조합 50개 제한) | F-30 | SEL-01-01 | `core/services/sales_suggest.py` (`limit_combinations` · `validate_options`) | `test_옵션_조합은_50개를_넘지_않는다` · `test_저장_전_옵션_검증` · `test_조합_초과_판매정보는_저장하지_않는다` | 구현 | 강근우 |
| R-003-06 | 현지화 상세페이지 자동 생성 (한국어 검수본 + 현지어 업로드본, 같은 구조) | F-24 | DTL-01-01 | `core/graph/content.py` · `core/agents/prompts/content_{draft,localize}.md` | `test_content_graph.py::test_한국어본과_현지어본을_같은_구조로_만든다` · `test_사양_표_기본_행은_판매정보에서_코드가_만든다` | 구현 | 강근우 |
| R-003-11 | 품질 검수 0~100점 · 미달 시 최대 2회 자동 재생성 | F-24 | DTL-01-01 | `core/content/quality.py` · `core/graph/content.py` (`_after_quality`) | `test_하드컷이면_지적사항을_넣어_다시_쓴다` · `test_2회_재생성해도_미달이면_검수필요로_결과를_준다` · `test_누락_섹션을_감점한다` | 구현 | 강근우 |
| R-003 (문화 필터) | 금기·과장·상표 표현 제거 (국가별 사전) | F-24 | DTL-01-01 | `core/content/culture.py` · `data/culture/{common,VN,SG,TH}.yaml` | `test_국가별_금기는_그_나라에서만_걸린다` · `test_치환_가능한_과장만_바꾸고_하드컷은_남긴다` · `test_영문은_단어_경계로만_찾는다` | 구현 | 강근우 |
| R-003 (F-25) | 상세페이지 텍스트 수정 · 현지어 재번역 (사람 수정값 우선) | F-25 | DTL-01-01 | `core/services/content_edit.py` · 내부 API `POST /internal/ai/content/retranslate` · Spring `PATCH .../detail-page/content` | `test_셀러_수정본을_현지어로_다시_옮긴다` · `test_content_retranslate.py` 2건 · Spring `DetailPageFlowTest` | 구현 | 강근우 |
| R-003 (F-26·F-28) | 상품·상세 이미지 AI 생성 (기본 컷 / 모델 컷 4종) | F-26 · F-28 | DTL-01-02 | `core/services/image_gen.py` · `data/models.yaml` · `core/jobs/runner.py` (즉시 취소) | `test_image_gen.py` 8건 (프롬프트·캐시·일일 상한·취소·dev_bff 전 구간) | 구현 (실 API 는 live 미검증) | 강근우 |
| R-003 (F-27) | 이미지 직접 업로드 · 대표 지정 · 삭제 | F-27 | DTL-01-01 | Spring `detailpage/DetailPageImageService` · `upload/UploadStorage` (dev_bff 와 같은 응답) | `test_상세페이지에서_이미지를_생성해_저장한다` · Spring `DetailPageFlowTest` | 구현 | 강근우 |

> 확인 필요: R-003 하위 ID 중 06·11·12·13 만 `명세서정리.md` 에서 확인했다. 나머지 행은 기능 ID(F-xx)로 적었다. 정의서가 나오면 하위 ID 로 바꾼다.

### 5-1. 이 표가 아직 안 다루는 요구사항

| 요구사항 | 내용 | 구현 | 담당 |
|---|---|---|---|
| R-005 | 전략 고도화 코파일럿 | `core/services/copilot.py` | 이동건 |
| R-006 | 플랫폼 오토 업로더 (Shopee 연동) | **과업 범위 제외** (기술결정서 결정-2). 프론트에서 셀러센터 링크로 대체 | — |

R-005 는 구현이 시작되면 이 표에 절을 추가한다.

## 6. 미해결 항목

1. 요구사항 정의서(`HD-GF-ANA-RA-10`) 원본이 비어 있어 하위 ID(R-00X-YY) 원문 문구를 코드 주석·`명세서정리.md` 에서 역추적했다. 정의서 확정 후 "내용" 칸을 원문으로 교체한다.
2. R-002-09/10, R-004-05~07 은 하위 ID 분할 근거가 코드 주석뿐이다. 팀 확인 필요.
3. "검증" 칸이 빈 행은 2~3주차 실구현과 함께 테스트를 붙인다.

## 7. 다른 파트 확인 필요

추적표를 채우면서 다른 담당자의 코드·데이터와 어긋나는 것을 발견한 항목이다. 발견 즉시 여기에 적고, 처리되면 지운다.

### 7-1. 소액 수입물품 면세(de minimis) — 3개국 모두 폐지됨 · 권수현

`core/pricing/fee_schedule.py` 의 YAML 스키마에는 `de_minimis` 필드가 없다. **없는 것이 현행법에 맞다.** 세 나라 모두 저가 수입품 면세가 사라졌으므로 앞으로도 넣지 않는다.

| 국가 | 옛 기준 | 현재 | 근거 |
|---|---|---|---|
| VN | 100만 VND 이하 특송 면세 | 2025-02-18 폐지 | Quyết định 01/2025/QĐ-TTg (구 78/2010/QĐ-TTg 폐지) |
| TH | ฿1,500 이하 관세·VAT 면제 | 2026-01-01 폐지, 1밧부터 과세 | 태국 관세청 고시 219/2568 (2025-12-04) |
| SG | S$400 이하 수입 GST 면제 | 2023-01-01 부터 OVR 체제로 과세 | IRAS Overseas Vendor Registration |

- `docs/AI_개발계획_v2.md` §6 의 표에 있던 VN "de minimis"·TH "฿1,500 기준" 은 이 PR 에서 지우고 경고 문구로 바꿨다.
- 인터넷 자료 상당수가 폐지 전 기준으로 남아 있다. 면세 한도를 넣으면 관세·VAT 가 빠져 마진이 과대 계산된다.
- 참고: <https://xaydungchinhsach.chinhphu.vn/tu-18-2-2025-bai-bo-quy-dinh-mien-thue-hang-nhap-khau-duoi-1-trieu-dong-gui-qua-chuyen-phat-nhanh-119250104170119018.htm> · <https://www.hlbthai.com/import-duty-exemption-for-low-value-goods-to-end-on-31-december-2025/> · <https://www.iras.gov.sg/taxes/goods-services-tax-(gst)/consumers/gst-on-imported-low-value-goods>

### 7-2. VN 관세율은 MFN / VKFTA 중 낮은 쪽 · 권수현

`fee_schedule.py` 의 `tariff_mode` 는 `MFN | VKFTA | NONE` 한 값만 고른다. 실제로는 한국산 원산지증명(Form VK)이 있으면 VKFTA, 없으면 MFN 이고 **둘 중 낮은 쪽이 실효세율**이다. `data/fee_schedules/VN.yaml` 작성 시 두 세율을 같이 적고 무엇을 골랐는지 남길지 정해야 한다. VKFTA 표(Nghị định 125/2022/NĐ-CP)는 연도별 인하 일정이 있어 **2026년 구간 값**을 읽어야 한다.

### 7-3. 국가별 결과 스키마 합의 · 이동건

`REPORT_COMPOSE`(이동건)가 읽는 국가별 산출물(`scores`·`insight`·`pricing`)의 모양을 2주차 초에 합의하기로 되어 있다(ONBOARDING §5). 노드 8개 실구현 전에 맞춰야 재작업이 없다.

### 7-4. 미작성 데이터 파일 · 이동건 · 권수현 · 강근우

`fee_schedule.py` 의 폴백 표와 `nodes/_stubs.py` 의 임시 세율이 동시에 쓰이고 있다. 두 곳의 값이 서로 다르면 보고서와 동기 API 가 다른 숫자를 낸다.

| 파일 | 담당 |
|---|---|
| `data/fee_schedules/*.yaml` (수수료·관세·VAT) | 이동건 (관세·VAT 값은 권수현이 제공) |
| `data/shipping_rates/*.yaml` | 권수현 |
| ~~`data/shopee_categories/*.json` · `data/culture/*.yaml`~~ 작성 완료 (2026-10-04) | 강근우 |

### 7-5. FxProvider 가 mock 뿐 · 이동건

R-002-04(환율)의 구현이 `core/providers/` 의 mock 이다. 2주차 실 LLM 노드에서 마진 숫자를 검증하려면 실제 환율이 필요하다.

### 7-6. 요구사항 정의서 원본 부재 · 전원

`중간보고산출물-GF/01. 분석/20. 요구사항 분석/HD-GF-ANA-RA-10. 요구사항 정의서` 폴더가 비어 있다. 하위 ID 문구를 코드 주석과 `명세서정리.md` 에서 역추적한 상태다(§6).

### 7-7. dev_bff 에 추가된 라우트 → Spring 이관 대상 · 권수현 · 강근우

판매 정보·상세페이지·이미지 화면을 프론트에 붙이려고 dev_bff 에 라우트를 먼저 만들었다. 응답 JSON 이 곧 Spring 컨트롤러 명세다.

| 라우트 | Spring 담당 |
|---|---|
| `GET /shopee/categories` · `GET /shopee/categories/{id}/attributes` · `GET/PUT .../sales-info` · `POST .../sales-info/suggest` | 권수현 (카테고리는 `data/shopee_categories/{cc}.json` 을 그대로 읽으면 된다) |
| `POST/GET .../detail-page` · `PATCH .../detail-page/content` · `.../detail-page/images*` · `/image-jobs/*` | 강근우 — **Spring 구현 완료** (`k-sales-hunter-be` `detailpage` 패키지, Testcontainers 통합 테스트) |
| `PUT /products/{id}` (변경 내역 + PARTIAL 재분석) | 차은호 (products 라우트) |

`POST .../detail-page/images` 는 API 스펙에서 업로드와 생성 결과 확정을 한 경로로 받게 돼 있었다. multipart 와 JSON 을 한 경로에서 받기 어려워 확정은 `POST .../detail-page/images/generated` 로 나눴다 (API_SPEC §2-4 갱신).

### 7-8. runner 수정 사항 리뷰 요청 · 이동건

이미지 잡 작업 중 `core/jobs/runner.py` 를 고쳤다. 기반 코드 담당이라 확인을 부탁한다.

- 대기(QUEUED) 중 취소 요청이 `mark_running` 에 덮여 사라지던 문제 수정 — `_guard` 가 시작 전에 취소 플래그를 본다.
- 이미지 잡은 취소 시 태스크를 바로 끊는다 (`_hard_cancel`). API 호출 하나가 20~40초라 노드 경계까지 기다리면 프론트가 그동안 '취소 요청됨'에 머문다.
- 국가가 없는 잡(상세페이지·이미지)은 `JobContext.step` 을 처음부터 준다. 안 주면 첫 flush 가 분석 단계(`MARGIN`)를 쓴다.

### 7-9. 시장 노드 구현 시 참고 · 차은호

- `CountryResult` 에 `product_features` · `market_raw` 를 선택 필드로 추가했다. 부분 재실행이 MARKET_INSIGHT 부터 돌 때 이 값을 복원한다. 값이 없으면 처음부터 다시 돈다.
- 상세페이지 생성이 `product_features.keywords` · `product_features.usps` 를 검색 키워드·강조 특징으로 쓴다. 실구현 때 키를 유지해 주면 품질 검수의 SEO 키워드 항목이 살아난다.
