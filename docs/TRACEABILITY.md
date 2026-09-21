# 요구사항 추적표 (traceability) — 초안 v0.1

요구사항 ID → 기능 → 화면 → 구현 → 검증을 한 줄로 잇는다.
한이음 산출물(요구사항 정의서 비고란·시험 결과서)의 근거가 되는 표다.

- 기준 문서: `명세서정리.md`(F-01~F-43 · R-000~R-006), `docs/AI_개발계획_v2.md`, `docs/API_SPEC_FE기준.md`
- 범위: AI 레포(`k-sales-hunter-ai`)가 구현하는 요구사항. Spring·FE 담당 항목은 "구현" 칸에 레포명만 적는다.
- 상태: `stub`(임시값 반환) · `구현`(실동작) · `미착수` · `범위외`
- 작성: 차은호 · 갱신 2026-09-21 (1주차 말)

## 1. 분석 파이프라인 (R-000 비서 AI 오케스트레이터)

| 요구사항 | 내용 | 기능 | 화면 | 구현 | 검증 | 상태 | 담당 |
|---|---|---|---|---|---|---|---|
| R-000-01 | 노드 순서 오케스트레이션 (gate→market→shipping→margin→report) | F-16 | SYS-01-01 | `core/graph/analysis.py` | `test_analysis_graph.py::test_모든_노드를_거친다` | 구현 | 이동건 |
| R-000-02 | 게이트 우선 — PROHIBITED 면 이후 노드 생략 | F-14 | SYS-01-01 | `core/graph/analysis.py` · `nodes/customs_gate.py` | `test_통관_차단이면_이후_노드를_건너뛴다` | 구현 | 차은호 |
| R-000-03 | 국가 fan-out 병렬 실행 후 State 병합 | F-16 | RPT-01-01 | `core/graph/analysis.py` | `test_3개국이_모두_끝까지_돈다` · `test_국가_하나가_실패해도_나머지는_끝난다` | 구현 | 이동건 |
| R-000-04 | 결과 종합 · 진입점수 확정 · 국가 랭킹 | F-18 | RPT-01-01 | `nodes/report_compose.py` · `core/pricing/scoring.py` | `test_진입점수와_순위가_확정된다` | stub | 이동건 |
| R-000-05 | 부분 재실행 — 변경 필드별 영향 범위 판정 | F-42 | EDT-01-01 | `core/graph/rerun_map.py` | — | 미착수 (5주차) | 차은호 |
| R-000-07 | 세션·중단 — 진행 중 노드 취소 | F-42 | SYS-01-01 | `core/jobs/runner.py` | — | 구현 | 이동건 |

## 2. 시장 분석 (R-001 트렌드 헌터)

| 요구사항 | 내용 | 기능 | 화면 | 구현 | 검증 | 상태 | 담당 |
|---|---|---|---|---|---|---|---|
| R-001-02 | 상품 이해 — 시각 특징·키워드·카테고리 추출 | F-10 | PRD-01-01 | `nodes/product_understanding.py` · `core/services/product_fill.py` | — | stub | 차은호 / 강근우(동기 API) |
| R-001-03 | 국가별 시장 데이터 수집 (경쟁 상품·가격·키워드) | F-15 | RPT-02-01 | `nodes/market_research.py` · `core/providers/` | — | stub (mock provider) | 차은호 |
| R-001-05 | 진입 적합성 4축 가중합 (수요·경쟁·K적합·수익성) | F-16 | RPT-01-01 · RPT-02-01 | `nodes/market_evaluate.py` · `core/pricing/scoring.py` | `test_scoring.py::test_시장_3축_가중합_공식` 외 | stub (점수 공식은 구현) | 차은호 |
| R-001-06 | 경쟁 환경 분석 · 경쟁가 밴드(25/50/75 분위) | F-17 | RPT-02-01 | `nodes/market_evaluate.py` | — | stub | 차은호 |
| R-001-07 | 국가별 소비 트렌드 요약 | F-19 | RPT-02-01 | `nodes/market_insight.py` | — | stub | 차은호 |
| R-001-08 | 전략적 포지셔닝 제안 (입문/프리미엄/팬덤/선물) | F-19 | RPT-02-01 | `nodes/market_insight.py` | — | stub | 차은호 |
| R-001-09 | 대시보드 판매 성과 집계 | F-38 · F-39 | DSH-01-01 | Spring 레포 | — | 범위외 | 권수현 |

## 3. 수익 계산 (R-002 마진 메이커)

| 요구사항 | 내용 | 기능 | 화면 | 구현 | 검증 | 상태 | 담당 |
|---|---|---|---|---|---|---|---|
| R-002-03 | 비용 스택 합산 (수수료·배송비·관세·VAT) | F-23 | RPT-02-01 | `core/pricing/engine.py` · `core/services/pricing_quote.py` | `test_analysis_graph.py::test_국가별_비용_구조가_프론트_표_순서와_같다` | 구현 | 권수현 |
| R-002-04 | 환율 적용 (현지통화 ↔ KRW) | F-21 | RPT-02-01 | `core/providers/` (FxProvider) | — | mock | 이동건 |
| R-002-05 | 적정 판매가 · 개당 순이익 산출 (3안) | F-22 | RPT-02-01 | `core/pricing/engine.py` · `nodes/margin.py` | — | 구현 / 노드는 stub | 권수현 / 차은호 |
| R-002-08 | 손익분기 분석 · 반영 비용 항목 표기 | F-23 | RPT-02-01 | `core/pricing/engine.py` · `core/services/pricing_quote.py` | — | 구현 | 권수현 |
| R-002-09 | 마진 검증 (순이익 음수·마진율 10% 미만 판정) | F-23 | RPT-02-01 | `nodes/margin.py` (critic) | — | stub | 차은호 |
| R-002-10 | 마진 결과 해설 문장 생성 | F-23 | RPT-02-01 | `nodes/margin.py` (explain) | — | stub | 차은호 |

> 확인 필요: R-002-09/10 의 원문 문구는 요구사항 정의서에서 아직 확인하지 못했다. 코드 주석(`nodes/margin.py`) 기준으로 적어 두었고, 정의서 확정 시 교체한다.

## 4. 통관 · 물류 리스크 (R-004 리스크 매니저)

| 요구사항 | 내용 | 기능 | 화면 | 구현 | 검증 | 상태 | 담당 |
|---|---|---|---|---|---|---|---|
| R-004-01 | 배송 방식 추천 (직배송 / Shopee SLS) | F-20 | RPT-02-01 | `nodes/logistics_estimate.py` | — | 구현 | 차은호 |
| R-004-02 | 무게 구간별 배송비 산출 | F-20 | RPT-02-01 | `core/pricing/shipping_rate.py` · `data/shipping_rates/*.yaml` | — | 구현 / YAML 미작성 | 권수현 |
| R-004-03 | 통관 가능 여부 판정 + 근거 조항 표시 | F-14 · F-43 | RPT-02-01 | `nodes/customs_gate.py` · `core/rag/gate_rules.py` | `test_통관_차단이면_이후_노드를_건너뛴다` | stub | 차은호 |
| R-004-04 | 금지·제한 품목 매치 | F-14 | RPT-02-01 | `nodes/customs_gate.py` · `data/policies/quick_rules/{cc}.yaml` | — | stub | 차은호 |
| R-004-05 | 통관 처리 주의사항 체크리스트 | F-14 | RPT-02-01 | `nodes/risk_checklist.py` | — | stub | 차은호 |
| R-004-06 | 반품 리스크 안내 | F-14 | RPT-02-01 | `nodes/risk_checklist.py` | — | stub | 차은호 |
| R-004-07 | 운영 난이도 판정 | F-14 | RPT-02-01 | `nodes/risk_checklist.py` | — | stub | 차은호 |
| R-004-08 | 판정 근거 원문·출처·기준일 보존 | F-43 | RPT-02-01 | `infra/models.py::RagDocument` · `contracts/v1/analysis.py::Evidence` · `data/policies/manifest.yaml` | `test_policy_manifest.py` | 구현 (문서 적재는 3주차) | 차은호 |
| R-004-10 | 포장 완료 기준 치수 입력 | F-20 | SEL-01-01 | `contracts/v1/analysis.py::Packaging` | — | 구현 | 이동건 |

## 5. 범위 밖 (참고)

| 요구사항 | 내용 | 구현 | 담당 |
|---|---|---|---|
| R-003 | 콘텐츠 아키텍트 — 상세페이지·이미지 생성 | `core/graph/` content_graph (미작성) · `core/services/image_gen.py` | 강근우 |
| R-005 | 전략 고도화 코파일럿 | `core/services/copilot.py` | 이동건 |
| R-006 | 플랫폼 오토 업로더 (Shopee 연동) | Spring 레포 | 권수현 · 강근우 |

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

- `docs/AI_개발계획_v2.md` §6 의 표에 VN "de minimis", TH "฿1,500 기준" 이 남아 있다. 낡은 값이므로 지워야 한다.
- 인터넷 자료 상당수가 폐지 전 기준으로 남아 있다. 면세 한도를 넣으면 관세·VAT 가 빠져 마진이 과대 계산된다.
- 참고: <https://xaydungchinhsach.chinhphu.vn/tu-18-2-2025-bai-bo-quy-dinh-mien-thue-hang-nhap-khau-duoi-1-trieu-dong-gui-qua-chuyen-phat-nhanh-119250104170119018.htm> · <https://www.hlbthai.com/import-duty-exemption-for-low-value-goods-to-end-on-31-december-2025/> · <https://www.iras.gov.sg/taxes/goods-services-tax-(gst)/consumers/gst-on-imported-low-value-goods>

### 7-2. VN 관세율은 MFN / VKFTA 중 낮은 쪽 · 권수현

`fee_schedule.py` 의 `tariff_mode` 는 `MFN | VKFTA | NONE` 한 값만 고른다. 실제로는 한국산 원산지증명(Form VK)이 있으면 VKFTA, 없으면 MFN 이고 **둘 중 낮은 쪽이 실효세율**이다. `data/fee_schedules/VN.yaml` 작성 시 두 세율을 같이 적고 무엇을 골랐는지 남길지 정해야 한다. VKFTA 표(Nghị định 125/2022/NĐ-CP)는 연도별 인하 일정이 있어 **2026년 구간 값**을 읽어야 한다.

### 7-3. 국가별 결과 스키마 합의 · 이동건

`REPORT_COMPOSE`(이동건)가 읽는 국가별 산출물(`scores`·`insight`·`pricing`)의 모양을 2주차 초에 합의하기로 되어 있다(ONBOARDING §5). 노드 8개 실구현 전에 맞춰야 재작업이 없다.

### 7-4. 미작성 데이터 파일 · 권수현

`data/fee_schedules/*.yaml`·`data/shipping_rates/*.yaml` 이 아직 없어 `fee_schedule.py` 의 폴백 표와 `nodes/_stubs.py` 의 임시 세율이 쓰이고 있다. 두 곳의 값이 서로 다르면 보고서와 동기 API 가 다른 숫자를 낸다.

### 7-5. FxProvider 가 mock 뿐 · 이동건

R-002-04(환율)의 구현이 `core/providers/` 의 mock 이다. 2주차 실 LLM 노드에서 마진 숫자를 검증하려면 실제 환율이 필요하다.

### 7-6. 요구사항 정의서 원본 부재 · 전원

`중간보고산출물-GF/01. 분석/20. 요구사항 분석/HD-GF-ANA-RA-10. 요구사항 정의서` 폴더가 비어 있다. 하위 ID 문구를 코드 주석과 `명세서정리.md` 에서 역추적한 상태다(§6).
