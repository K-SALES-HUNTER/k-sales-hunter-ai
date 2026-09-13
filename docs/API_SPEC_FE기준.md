# FE 기준 API 설계 — Spring(FE용 REST) + AI 내부 API

작성: 2026-09-13. 근거: `k-sales-hunter-fe` 전체 페이지·훅·스토어·`apis/*.ts`·`types/*.ts`·`mocks/*.ts`. **FE는 UI가 완성돼 있고 API는 전부 목**이므로, FE의 함수 시그니처와 타입을 계약으로 삼는다. 문서(결정서·설계서)와 다르더라도 FE에 이미 구현된 동작을 우선한다.

## 0. 원칙

1. **FE 타입이 곧 응답 스키마.** `src/types/*.ts`와 `src/mocks/*.ts`의 export 타입(`Product`, `TotalReport`, `CountryReport`, `PdpContent`, `SalesOpsData`…)을 Spring 응답 DTO로 그대로 옮긴다. FE 쪽 `apis/*.ts`는 내부만 axios로 바꾸고 시그니처는 유지한다(파일 주석에 이미 그렇게 적혀 있음).
2. **표시용 문자열은 Spring이 만든다.** `priceLocalText: "₫535,000"`, `costText: "USD 4.5/unit"`, `amountText: "-₩2,100"`, `profitText: "₩7,200 / 개당"` 같은 것. AI는 숫자·통화코드·문장(해설)만 준다.
3. **LLM이 필요한 것만 잡(비동기)이고, 숫자 계산은 동기 API다.** 분석 보고서·상세페이지·이미지는 잡(폴링). 마진 재계산·판매정보 추천·AI 자동 채우기·코파일럿은 동기.
4. **진행 상태는 폴링.** FE에 SSE 코드가 없고, 로딩 오버레이는 5단계 목 타이머다. `GET .../analysis` 폴링(2초)으로 `step`을 받아 오버레이 단계를 실제 진행에 맞춘다. Redis Pub/Sub·콜백·seq는 쓰지 않는다.
5. **국가는 3개(VN·SG·TH).** FE 트리·카드·랭킹·오버레이 문구("3개 국가를 동시에")가 3개국 전제다. 분석 잡은 `countries`를 받아 fan-out 하고, 기본값은 연동된 스토어 국가 또는 3개 전부.

## 1. 화면 ↔ FE 함수 ↔ Spring 엔드포인트 ↔ AI 관여

| 화면 | FE 함수 (apis/) | Spring | AI |
|---|---|---|---|
| 로그인 / 회원가입 | `useAuthStore.login`(목), `requestJoin` | `POST /auth/login`, `POST /auth/join` | — |
| 대시보드 | `fetchDashboardSummary`, `fetchRecentProducts`, `fetchHasLinkedMarket` | `GET /dashboard/summary`, `GET /dashboard/recent-products`, `GET /stores/linked` | — |
| 설정 계정/마켓/연동 | `fetchAccountInfo`, `updateAccountInfo`, `fetchMarketInfo`, `updateMarketInfo`, `fetchConnectedStores`, `connectStore`, `disconnectStore`, `verifyCurrentPassword`, `changePassword` | `GET/PUT /me/account`, `GET/PUT /me/market-profile`, `GET /stores`, `POST /stores/{cc}/connect`(목 연동), `DELETE /stores/{cc}`, `POST /me/password/verify`, `PUT /me/password` | — |
| 상품 리스트 | `fetchProducts` | `GET /products` | — |
| 상품 등록 폼 | `fetchCategoryOptions`, `requestAiFill`, (이미지 업로드 없음→추가) | `GET /products/categories`, `POST /uploads/images`, **`POST /products/ai-fill`** | **product-fill(동기, Vision)** |
| 상품 등록 → 분석 로딩 | (목 타이머) | **`POST /products`** → `{productId, analysisJobId}`, **`GET /products/{id}/analysis`** 폴링, `POST /products/{id}/analysis/cancel` | **analysis-job** |
| 상품 수정 | (목) | `PUT /products/{id}` → `{changes[], analysisJobId?}` | analysis-job(PARTIAL) |
| 글로벌 보고서 | `fetchTotalReport` | `GET /products/{id}/report` (분석 중이면 202+상태) | 결과 매핑 |
| 국가별 보고서 | `fetchCountryReport` | `GET /products/{id}/report/{cc}` | 결과 매핑 |
| 국가별 보고서 › 배송·포장 저장 | (목) | `PUT /products/{id}/countries/{cc}/shipping` {method, packaging} → 재계산된 shipping·pricing 반환 | **pricing/quote(동기)** |
| 국가별 보고서 › 가격 3안 선택 | (FE 로컬) | 응답에 3안 전부 포함, 선택은 FE | — |
| 판매 정보 입력 | `fetchSalesInfo`, `saveSalesStep` | `GET /products/{id}/countries/{cc}/sales-info`, **`POST .../sales-info/suggest`**, `PUT .../sales-info`, `GET /shopee/categories?country=`, `GET /shopee/categories/{catId}/attributes` | **sales-info/suggest(동기)**, 최종가 변경 시 **pricing/quote** |
| 상세 페이지 생성 버튼 | (1.5초 목) | **`POST /products/{id}/countries/{cc}/detail-page`** → jobId, `GET .../detail-page` 폴링 | **content-job** |
| 상세 페이지 | `fetchDetailContent` | `GET .../detail-page`, `PATCH .../detail-page/content` {name, description}, `POST .../detail-page/images`(업로드), `DELETE .../images/{imgId}`, `PUT .../images/main` | — |
| 상세/상품 이미지 AI 생성 | `generateImage` | **`POST .../detail-page/images/generate`** → jobId, `GET /image-jobs/{jobId}` 폴링, `POST /image-jobs/{jobId}/cancel` | **image-job** |
| AI 패널 (모든 2Depth 화면) | `useAiChatStore.send`(목) | **`POST /products/{id}/copilot/messages`** | **copilot(동기, tool-calling)** |
| 판매 관리 | `fetchSalesOps` | `GET /products/{id}/countries/{cc}/sales-ops`, `PUT .../listing/status`(중단/재개), `PUT .../orders/{no}/status`, `PUT .../price` → `price_change_logs`, `POST .../stock/add` | summary/note 문장만 **sales-insight(동기, 선택)** |
| 재고량 추가 | `useSalesOpsStore.addStock`(목) | `POST /products/{id}/countries/{cc}/stock/add` {additions:[{variantId, qty}]} | — |

Base URL: FE `.env`의 `VITE_API_BASE_URL` → Spring `/api/v1`. 인증: `Authorization: Bearer <JWT>` (axiosInstance 인터셉터 TODO 자리 있음).

## 2. Spring 엔드포인트 상세 (FE 타입과 1:1)

### 2-1. 상품

`GET /products` → `Product[]` (types/product.ts)
```jsonc
[{ "id": 1, "name": "…", "image": "url", "images": ["url"], "category": "뷰티",
   "costPrice": 4500, "weight": 220, "description": "…", "sellingPoints": "…", "mainTarget": "…",
   "revenue": null, "registeredAt": "2026-06-20",
   "countries": [ { "code": "VN", "name": "베트남", "stage": "report"|"sales-info"|"detail",
                    "salesStatus": "판매전"|"판매중"|"판매중단", "hasDetailPage": false, "hasSalesInfo": false } ] }]
```
`countries[]` 계산 규칙(Spring): 분석 완료된 국가만 포함(게이트 PROHIBITED 국가는 제외 — FE 전제 "노출 국가 = 판매 가능 국가"). `hasSalesInfo = sales_infos 행 존재`, `hasDetailPage = detail_pages.status == done`, `stage = detail ? 'detail' : hasSalesInfo ? 'sales-info' : 'report'`, `salesStatus = listings.status` 매핑(없으면 판매전).

`POST /uploads/images` multipart → `{ "id": "img_…", "url": "https://…" }` (FE `useProductForm.addImages`의 목 프로그레스를 XHR progress로 교체)

`POST /products/ai-fill` → AI product-fill 프록시
```jsonc
// req  { "name": "…", "category": "" , "description": "", "sellingPoints": "", "mainTarget": "", "imageUrls": ["…"] }
// res  { "category": "뷰티", "description": "…", "sellingPoints": "…", "mainTarget": "…" }   // FE AI_FILL_MOCK 형태. 비어있는 필드만 FE가 채움
```

`POST /products` → 저장 + 분석 잡 시작
```jsonc
// req  { "name", "category", "costPrice", "weight", "description", "sellingPoints", "mainTarget", "imageIds": ["img_…"], "aiFilledFields": ["description"] }
// res  { "productId": 12, "analysisJobId": "a_12_1" }
```
`PUT /products/{id}` → `{ "changes": [{"label":"공급 원가","before":"4,500원","after":"5,000원"}], "analysisJobId": "a_12_2" | null }` (변경 없으면 null. 변경 필드에 따라 PARTIAL 재분석)

`GET /products/{id}/analysis` (FE 폴링 2초)
```jsonc
{ "jobId": "a_12_1", "status": "RUNNING"|"COMPLETED"|"FAILED"|"CANCELLED",
  "step": "GATE"|"MARKET"|"SHIPPING"|"MARGIN"|"REPORT",   // AiLoadingOverlay 5단계와 1:1
  "progress": 0.45, "countries": { "VN": {"status":"RUNNING","step":"MARKET"}, "SG": {…}, "TH": {…} },
  "etaSeconds": 90, "errorCode": null }
```
`POST /products/{id}/analysis/cancel` → 204 (오버레이 "중단하기")

### 2-2. 보고서

`GET /products/{id}/report` → `TotalReport` (types/report.ts). 분석 중이면 `202 { "status": "RUNNING", "step": … }` → FE 스켈레톤 유지.
```jsonc
{ "conclusionTitle": "베트남 우선 진입을 추천합니다.", "conclusionBody": "…",
  "metrics": [ {"label":"수요","grade":"높음","score":87}, {"label":"경쟁 강도","grade":"낮음","score":34,"invert":true},
               {"label":"K-트렌드 적합도","grade":"높음","score":82}, {"label":"수익성","grade":"보통","score":71} ],
  "countries": [ {"code":"VN","rank":1,"fitGrade":"매우 적합","priceLocalText":"₫535,000","priceKrw":28900}, … ],
  "investigation": { "summary":"…", "countries":["베트남","싱가포르","태국"], "criteria":["수요","경쟁 강도","K-트렌드 적합도","수익성"], "platforms":["Shopee"] },
  "nextAction": "…",
  "sales": null | SalesStatusSummary }   // 판매중 국가 있을 때만, orders 집계 (AI 아님)
```
글로벌 `metrics`는 국가별 4축 점수의 **1위 국가 값** 또는 가중 평균 — Spring이 AI 결과에서 뽑는다(권장: 1위 국가).

`GET /products/{id}/report/{cc}` → `CountryReport`
```jsonc
{ "code":"VN", "name":"베트남", "currency":"₫",
  "conclusion": { "title":"프리미엄형 포지션으로 판매", "body":"…", "positioning":"프리미엄형", "priceText":"₩28,900 (₫535,000)", "profitText":"₩7,200 / 개당" },
  "analysis": { "summary":"…", "metrics":[ {"label":"수요","grade":"높음","score":87,"comment":"…"}, … 4개 ] },
  "competition": { "summary":"…", "stats":[{"label":"유사 상품 수","value":"많음","tone":"bad"}, …4개],
                   "priceTiers":[{"label":"₩5,000 (저가형)","weight":162}, {"label":"₩10,000 (중간형)","weight":243}, {"label":"₩30,000+ (프리미엄)","weight":162}],
                   "priceMarker":{"label":"₩28,900 권장가","ratio":0.67},
                   "table":[{"type":"저가형","priceRange":"…","strength":"…","weakness":"…","strategy":"…"}, …3행] },
  "shipping": { "options":[ {"id":"direct","name":"직접 배송","costText":"USD 4.5/unit","periodText":"7~12일","fitBadge":"소량 판매에 적합","recommended":false,"description":"…"},
                            {"id":"sls","name":"Shopee SLS", … "recommended":true} ],
                "warnings":[ "… (근거: 베트남 관세법 제16조)" ] },   // AI risk.warnings → "문장 (근거: 출처)" 포맷
  "packaging": { "width":12, "depth":12, "height":8 },
  "pricing": { "scenarios":[ {"id":"low","label":"Low","price":22000,"priceLocalText":"₫407,000","netProfit":2700,"marginRate":12.3,"breakevenUnits":1820,"badge":"수익 낮음","summary":"…",
                              "costRows":[{"label":"판매가","amountText":"+₩22,000","emphasis":true},{"label":"공급 원가","amountText":"-₩12,800"},{"label":"Shopee 수수료","amountText":"-₩1,400"},{"label":"국제 배송비","amountText":"-₩3,400"},{"label":"관세 (6%)","amountText":"-₩700"},{"label":"VAT (10%)","amountText":"-₩1,000"},{"label":"예상 순이익","amountText":"₩2,700","emphasis":true}] },
                             {"id":"mid","label":"추천 (Mid)", … "recommended":true}, {"id":"high", …} ],
               "appliedBadges":["관세 반영","VAT 반영","배송비 반영","Shopee 수수료 반영","환율 반영"] } }
```
`priceMarker.ratio` = 권장가가 priceTiers 띠(low~high 경계) 위에서 차지하는 0~1 위치 — Spring 또는 AI가 계산(AI가 `priceBand{lowKrw,midKrw,highKrw}`를 주면 Spring이 ratio 산출).

`PUT /products/{id}/countries/{cc}/shipping` {method:"direct"|"sls", packaging:{weight,width,depth,height}} → `{ "shipping": …, "pricing": … }` 재계산본 (AI `pricing/quote` 동기 호출). 저장 후 `GET report/{cc}`도 갱신값 반환.

### 2-3. 판매 정보

`GET /products/{id}/countries/{cc}/sales-info` → mocks/sales.ts 형태
```jsonc
{ "priceScenarios":[{"id":"low","label":"Low","price":22000,"badge":"수익 낮음"},{"id":"mid","label":"추천 (Mid)","price":28900,"badge":"추천","recommended":true},{"id":"high",…}],
  "shippingMethods":[{"id":"direct","name":"직접 배송","cost":"USD 4.5/unit","costKrw":6200,"period":"7~12일","note":"소량 판매에 적합"},{"id":"sls",…,"aiRecommended":true}],
  "marginBasis": { "dutyRate":0.06, "vatRate":0.10, "shopeeFeeRate":0.072, "paymentFeeRate":0.02, "fixedCostKrw":0, "fxNote":"1 VND = 0.055원", "taxBase":"CIF" },   // FE PriceSection 로컬 계산용 → 실제는 quote 호출 권장
  "packaging": {"weight":320,"width":18,"depth":8,"height":8},
  "shopeeCategoryOptions":[{"value":"100001","label":"뷰티 › 스킨케어 › 클렌저"}], "shopeeCategoryDefault":"100001",
  "categoryAttrs":[{"key":"brand","label":"브랜드","value":"…","required":true}, …],
  "optionLevel1":{"name":"색상","values":["Black","White"]}, "optionLevel2":{"name":"구성","values":["본체만","파우치 포함"]},
  "stockRows":[{"option1":"Black","option2":"본체만","qty":42}],
  "saved": { "finalPrice": 28900, "selectedTier":"mid", "shippingMethod":"sls", "category":"100001", … } | null }
```
`POST .../sales-info/suggest` {category?} → AI `sales-info/suggest` (categoryAttrs·optionLevel1/2 추천). `GET /shopee/categories?country=VN` → 정적 트리(JSON 파일). `GET /shopee/categories/{catId}/attributes` → 필수/선택 속성 스키마(정적).
`PUT .../sales-info` {selectedTier, finalPrice, shippingMethod, category, attrs{}, useOptions, option1{name,values}, option2, stock:[{option1,option2,qty,extraPrice}]} → 저장, `hasSalesInfo=true`. 옵션 ≤2단, 조합 ≤50 검증.
`POST .../pricing/quote` {price, shippingMethod, packaging?} → `{unitProfitKrw, marginRate, breakevenUnits, costRows[]}` (FE `calcUnitProfit` 대체, 디바운스 300ms)

### 2-4. 상세 페이지·이미지

`POST /products/{id}/countries/{cc}/detail-page` → `{ "jobId":"c_12_VN_1" }` (판매정보 없으면 409)
`GET .../detail-page` → 생성 중 `202 {status:"GENERATING", progress}` / 완료:
```jsonc
{ "status":"DONE"|"NEEDS_REVIEW", "qualityScore": 84, "qualityIssues": [],
  "content": { "ko": PdpContent, "local": PdpContent },   // mocks/sales.ts PdpContent 그대로
  "seller": { "name":"마켓명", "meta":"온라인 · 5분 이내 응답", "rating":"—", "response":"—", "followers":"—" },
  "productImages":[{"id":"pi_1","label":"기본 1","src":"url"}], "mainImageId":"pi_1",
  "detailImages":[{"id":"di_1","label":"상세 이미지 1","src":"url","prompt":null}],
  "locale":"vi" }
```
`PdpContent = { breadcrumb[], name, price, usps[], shipping{region,fee,eta}, options[{label,values[]}], stockNote, specs[[k,v]], description }`. **AI가 만드는 것: name, usps, description, specs(상품 사양 표), breadcrumb(카테고리 경로 현지어).** price/shipping/options/stockNote는 Spring이 sales_info로 채운다(ko·local 둘 다).
`PATCH .../detail-page/content` {name, description} → ko 본 수정 + local 재번역 여부는 `retranslate:true` 옵션(동기 gpt-4o-mini 번역).
`POST .../detail-page/images` multipart {target: product|detail} → `{id,label,src}`; `DELETE .../detail-page/images/{imgId}`; `PUT .../detail-page/images/main` {imageId}.
`POST .../detail-page/images/generate` → FE `GenerateImageParams` 그대로 `{target, prompt, mode:"basic"|"model", modelId?, referenceIds[]}` → `{ "jobId":"i_…" }`
`GET /image-jobs/{jobId}` → `{status:"RUNNING"|"DONE"|"FAILED", progress, result: {id,src,prompt} | null}`; `POST /image-jobs/{jobId}/cancel`. 저장은 FE가 `POST .../detail-page/images` {generatedImageId, replaceImageId?}로 확정(재생성 시 원본 id 유지 — FE `replaceImage` 로직).

### 2-5. 코파일럿

`POST /products/{id}/copilot/messages`
```jsonc
// req  { "message":"가격 낮추면 마진 어떻게 돼?", "page": {"type":"COUNTRY_REPORT","countryCode":"VN"}, "history":[{"role":"user","text":"…"},{"role":"ai","text":"…"}] }   // 최근 10턴
// res  { "answer":"…", "action": null | {"type":"REANALYZE"|"ADD_COUNTRY"|"REGENERATE_DETAIL","jobId":"…","description":"필리핀 분석을 시작했어요"} }
```
FE 스토어는 대화를 세션 단위로 들고 있으므로 Spring은 `chat_messages`에 저장만 하고 컨텍스트는 요청의 `page`로 판단해 해당 보고서/판매정보/상세 JSON을 AI에 붙여 보낸다. 목 응답 문구대로 **보고서에 영향을 주는 명령은 3종(재생성·타 국가 추가·입력 정보 수정)** 만 action으로 처리, 나머지는 답변만.

### 2-6. 판매 관리 (`GET .../sales-ops` → `SalesOpsData`)
`summary{headline, description, trend[]}`, `link{url, registeredAt, updatedAt, lastSync}`, `orders{summary, rows[]}`, `salesTrend[]`, `performance{qty, revenue, bepRemaining, profit, margin, note, monthlyRevenue[], costBreakdown[], calcBasis}`, `priceManage{currentPrice, fxNote, note, impacts[], history[]}`. Shopee 미연동이므로 **orders·link는 Spring 시드 데이터**. `summary.headline/description`, `performance.note`, `priceManage.note`, `impacts[].impact("판매량 +8% 예상")`는 AI `sales-insight`(gpt-4o-mini, 선택) 또는 규칙 템플릿. `impacts[].margin`은 pricing/quote로 계산.

## 3. AI 내부 API (Spring → Python, `X-Internal-Token`)

| 메서드 | 경로 | 종류 | 응답 |
|---|---|---|---|
| POST | `/internal/ai/analysis-jobs` | 잡 | `202 {jobId}` |
| GET | `/internal/ai/analysis-jobs/{jobId}` | 폴링 | `{status, step, progress, countries{}, result?, error?}` |
| POST | `/internal/ai/analysis-jobs/{jobId}/cancel` | | 204 |
| POST | `/internal/ai/content-jobs` / GET `/{jobId}` / POST `/{jobId}/cancel` | 잡 | 동일 |
| POST | `/internal/ai/image-jobs` / GET / cancel | 잡 | `result {imageUrl \| base64, prompt}` |
| POST | `/internal/ai/product-fill` | 동기 (≤15s) | `{category, description, sellingPoints, mainTarget, features{}, imageUsed}` |
| POST | `/internal/ai/pricing/quote` | 동기 (ms, LLM 없음) | `{shippingOptions[], scenarios[3]?, quote{unitProfitKrw, marginRate, breakevenUnits, costRows[]}, fx, feeScheduleVersion}` |
| POST | `/internal/ai/sales-info/suggest` | 동기 (≤10s) | `{categoryId, categoryAttrs[], option1, option2, stockHint}` |
| POST | `/internal/ai/copilot/messages` | 동기 (≤20s) | `{answer, intent, action?}` |
| POST | `/internal/ai/sales-insight` | 동기 (선택) | `{headline, description, performanceNote, priceNote, impacts[]}` |
| GET | `/internal/ai/health` | | |

**jobId**: Spring이 만든 문자열(`a_{productId}_{n}`)을 그대로 키로 쓴다. 잡 상태와 결과는 `ai.jobs` 테이블(신설, `job_results` 대체)에 저장해 프로세스 재시작·Spring 재조회에 견딘다. 콜백 없음. Spring은 `COMPLETED`를 보면 `result`를 public 테이블(`country_reports`, `price_options`, `reports`)로 복사한다.

### AnalysisJob 요청
```jsonc
{ "jobId":"a_12_1", "jobType":"FULL"|"PARTIAL", "countries":["VN","SG","TH"],
  "product": { "productId":12, "name":"…", "category":"뷰티", "supplyCostKrw":4500, "weightG":220, "description":"…", "sellingPoint":"…", "mainTarget":"…",
               "packaging": {"weightG":320,"widthMm":180,"depthMm":80,"heightMm":80} | null, "imageUrls":["…"] },
  "marketProfile": {"brandDirection":"K-트렌드","sellerType":"1인 셀러","mainTarget":"…","brandTone":"…"} | null,
  "preferences": { "targetMarginRate":0.25, "shippingMethod":null, "fixedCostKrw":0 },
  "partial": { "changedFields":["product.supplyCostKrw"], "previousResult": {…이전 result…} } | null }
```
### AnalysisJob 결과 (`result`) — Spring이 §2-2로 매핑
```jsonc
{ "global": { "conclusionTitle", "conclusionBody", "ranking":["VN","SG","TH"], "investigationSummary", "nextAction" },
  "countries": { "VN": {
     "status":"DONE"|"FILTERED_OUT"|"NEEDS_REVIEW",
     "customs": { "level":"ALLOWED"|"RESTRICTED"|"PROHIBITED"|"UNKNOWN", "evidence":[{"text","sourceUrl","publisher","effectiveFrom"}], "structuralBarriers":[] },
     "scores": { "demand":87, "competition":58, "kFit":84, "profitability":71, "entryScore":78, "entryGrade":"FIT"|"NORMAL"|"CAUTION", "fitGrade":"VERY_FIT"|"PARTIAL_FIT"|"NORMAL"|"CAUTION", "rank":1,
                 "comments": {"demand":"…","competition":"…","kFit":"…","profitability":"…"}, "evidence": {...} },
     "insight": { "summary":"…", "positioning":"PREMIUM"|"ENTRY"|"FANDOM"|"GIFT", "positioningLabel":"프리미엄형", "conclusionTitle":"프리미엄형 포지션으로 판매", "conclusionBody":"…" },
     "competition": { "summary":"…", "stats":[{"label","value","tone"}], "priceBandKrw":{"low":5000,"mid":10000,"high":30000,"weights":[162,243,162]}, "table":[…3행] },
     "logistics": { "options":[{"method":"DIRECT"|"SLS","costUsd":4.5,"costKrw":6200,"etaMinDays":7,"etaMaxDays":12,"recommended":false,"fitBadge":"…","description":"…"}], "packagingUsed":{…}, "rateVersion":"…" },
     "pricing": { "fx":{"krwPerLocal":0.055,"asOf":"…"}, "feeScheduleVersion":"vn-shopee-2026.09", "recommendedTier":"MID",
                  "scenarios":[{"tier":"LOW","priceKrw":22000,"priceLocal":407000,"netProfitKrw":2700,"marginRate":0.123,"breakevenUnits":1820,"badge":"수익 낮음","summary":"…","costRows":[{"key":"salePrice","label":"판매가","amountKrw":22000},{"key":"supplyCost","label":"공급 원가","amountKrw":-12800},{"key":"platformFee","label":"Shopee 수수료","amountKrw":-1400},{"key":"shipping","label":"국제 배송비","amountKrw":-3400},{"key":"duty","label":"관세 (6%)","amountKrw":-700},{"key":"vat","label":"VAT (10%)","amountKrw":-1000},{"key":"netProfit","label":"예상 순이익","amountKrw":2700}]}, …],
                  "verdict":"GOOD"|"RISK"|"NON_VIABLE", "appliedBadges":[…] },
     "risk": { "warnings":[{"text":"…","source":"베트남 관세법 제16조","sourceUrl":"…"}], "checklist":[…], "difficulty":"LOW"|"MID"|"HIGH" } } },
  "usage": {"llmCalls":…, "inputTokens":…, "outputTokens":…, "costUsd":…} }
```
FILTERED_OUT(PROHIBITED) 국가는 Spring이 `product.countries`에서 제외하되 사유는 저장한다(향후 "판매 불가 사유" 화면용).

## 4. 상태 전이 (Spring 소유)

```
products 생성 → analysis RUNNING → COMPLETED → countries[].stage='report'
  → sales_infos 저장 → hasSalesInfo=true, stage='sales-info'   (CountryReport의 "상세 페이지 생성" 버튼 활성)
  → detail-page 잡 DONE → hasDetailPage=true, stage='detail'
  → (Shopee 링크 연결 = 프론트 외부 링크) listings 시드 → salesStatus='판매중' → 판매관리 탭 노출
  → 판매 중단/재개 → salesStatus 토글
```

## 5. FE 쪽 연동 작업 목록 (프론트 담당자 전달용)

1. `apis/*.ts` 목을 axios 호출로 교체(시그니처 유지). `axiosInstance` 인터셉터에 JWT 주입·401 처리.
2. `ProductRegisterPage`: `REGISTERED_PRODUCT_ID` 하드코딩 → `POST /products` 응답의 `productId`. `AiLoadingOverlay`의 목 타이머 → `GET /products/{id}/analysis` 폴링 결과의 `step`으로 단계 진행(5단계 enum 매핑 테이블 FE에 추가). "중단하기" → cancel 호출.
3. `useProductForm.addImages`: 목 프로그레스 → `POST /uploads/images` XHR progress. `requestAiFill()`에 현재 폼값·이미지 URL 전달(지금은 인자 없음).
4. `useTotalReport`/`useCountryReport`: 202 응답이면 `refetchInterval: 2000`.
5. `CountryReportPage` "상세 페이지 생성": 1.5초 목 → `POST detail-page` + 폴링(AiLoadingOverlay 재사용 가능, 단계는 CONTENT용 3단계).
6. `PriceSection.calcUnitProfit`(목 요율) → `POST pricing/quote` 디바운스 호출. `marginBasisMock`·`appliedCostBadgesMock` → 응답값.
7. `OptionStockSection`: `saveStep` 목 → 단계별 저장은 FE 로컬 상태로 두고 마지막 "저장"에서 `PUT sales-info` 1회. 카테고리 목록·속성은 `GET /shopee/categories`.
8. `useAiChatStore.send`: setTimeout 목 → `POST copilot/messages` (현재 페이지 type·countryCode를 인자로 넘기도록 `send(text, page)` 확장).
9. `DetailImagePage`: `generateImage` 목 → `POST images/generate` + `GET /image-jobs/{id}` 폴링, 취소 호출. `referencePhotosMock` → 상세페이지 응답의 `productImages`.
10. `useSalesOpsStore`/`useDetailImageStore`의 세션 메모리 오버라이드 → 서버 저장으로 이관(연동 후 제거 가능).
11. `SalesOpsPage`의 `shippingMethodsMock`·`stockRowsMock` 직접 참조 → `fetchSalesOps` 응답으로.
