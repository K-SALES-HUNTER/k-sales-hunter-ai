"""분석 잡 계약 — Spring 이 보내는 command 와 받아가는 result.

[읽는 법] AnalysisResult 는 프론트 TotalReport / CountryReport 로 그대로 매핑된다.
          매핑 표는 docs/API_SPEC_FE기준.md §2-2.

[규칙] 표시용 문자열(₫535,000, USD 4.5/unit, -₩2,100)은 여기 담지 않는다.
       숫자와 통화 코드만 주고 포맷은 Spring/프론트가 한다.
       단 해설 문장(summary, comment, conclusionBody)은 AI 산출물이므로 여기 담는다.
"""

from __future__ import annotations

from pydantic import Field

from app.contracts.v1.base import SCHEMA_VERSION, CamelModel
from app.contracts.v1.enums import (
    AxisGrade,
    CountryStatus,
    CustomsLevel,
    EntryGrade,
    ErrorCode,
    FitGrade,
    JobKind,
    MarginVerdict,
    Positioning,
    PriceTier,
    RiskDifficulty,
    ShippingMethod,
)

# ── 입력 ────────────────────────────────────────────────────────────────


class Packaging(CamelModel):
    """포장 완료 기준 치수. 배송 요율 구간을 결정한다 (R-004-10)."""

    weight_g: int
    width_mm: int
    depth_mm: int
    height_mm: int


class ProductSnapshot(CamelModel):
    """Spring 이 보내는 상품 스냅샷. Python 은 업무 DB 를 읽지 않는다."""

    product_id: int
    name: str
    category: str
    supply_cost_krw: int
    weight_g: int
    description: str = ""
    selling_point: str = ""
    main_target: str = ""
    packaging: Packaging | None = None
    #: presigned URL. 만료 60분으로 발급받는다.
    image_urls: list[str] = Field(default_factory=list)


class MarketProfile(CamelModel):
    """셀러의 브랜드 설정. 시장 해설과 콘텐츠 톤에 반영된다 (MKT-01-03)."""

    brand_direction: str = ""
    seller_type: str = ""
    main_target: str = ""
    brand_tone: str = ""


class AnalysisPreferences(CamelModel):
    target_margin_rate: float = 0.25
    shipping_method: ShippingMethod | None = None
    #: 손익분기 계산용. 0 이면 BEP 를 내지 않는다.
    fixed_cost_krw: int = 0


class PartialSpec(CamelModel):
    """부분 재실행 입력. changed_fields 로 시작 노드를 정하고 나머지는 이전 결과에서 복원한다."""

    changed_fields: list[str] = Field(default_factory=list)
    force_rerun_nodes: list[str] = Field(default_factory=list)
    previous_result: dict | None = None


class AnalysisCommand(CamelModel):
    schema_version: str = SCHEMA_VERSION
    #: Spring 이 발번한 값을 그대로 쓴다. Python 은 자체 ID 를 만들지 않는다.
    job_id: str
    trace_id: str = ""
    job_type: JobKind = JobKind.FULL
    countries: list[str] = Field(default_factory=lambda: ["VN", "SG", "TH"])
    product: ProductSnapshot
    market_profile: MarketProfile | None = None
    preferences: AnalysisPreferences = Field(default_factory=AnalysisPreferences)
    partial: PartialSpec | None = None


# ── 출력: 국가 단위 ──────────────────────────────────────────────────────


class Evidence(CamelModel):
    """판정 근거. 출처와 기준일 없이 판정하지 않는다 (R-004-08)."""

    text: str
    source_url: str = ""
    publisher: str = ""
    effective_from: str = ""


class CustomsResult(CamelModel):
    level: CustomsLevel
    sellable: bool
    evidence: list[Evidence] = Field(default_factory=list)
    #: 현지법인·인증 등 구조적 장벽. 예) 베트남 화장품 CPN 신고
    structural_barriers: list[str] = Field(default_factory=list)
    #: 관세·VAT 율. 마진 계산으로 전달된다.
    duty_rate: float = 0.0
    vat_rate: float = 0.0
    tariff_mode: str = "MFN"


class AxisScore(CamelModel):
    score: int = Field(ge=0, le=100)
    grade: AxisGrade
    #: 수집 데이터에서 인용한 근거. 비어 있으면 Critic 이 반려한다.
    evidence: list[str] = Field(default_factory=list)
    #: 프론트 지표 행의 한 줄 해설
    comment: str = ""


class ScoreResult(CamelModel):
    """4축 가중합 결과 (R-001-05).

    entry_score = 0.35*demand + 0.25*(100-competition) + 0.25*k_fit + 0.15*profitability
    """

    demand: AxisScore
    competition: AxisScore
    k_fit: AxisScore
    profitability: AxisScore
    market_partial: float = 0.0
    entry_score: int = 0
    entry_grade: EntryGrade = EntryGrade.NORMAL
    fit_grade: FitGrade = FitGrade.NORMAL
    rank: int = 0
    #: Critic 재평가 횟수. 2 초과면 needs_review.
    critic_attempts: int = 0


class InsightResult(CamelModel):
    summary: str = ""
    trends: list[str] = Field(default_factory=list)
    positioning: Positioning = Positioning.ENTRY
    #: 프론트 노출용 한국어 라벨. 예) 프리미엄형
    positioning_label: str = ""
    conclusion_title: str = ""
    conclusion_body: str = ""


class CompetitionStat(CamelModel):
    label: str
    value: str
    #: bad 면 프론트가 빨간 타일로 강조한다
    tone: str | None = None


class PriceBand(CamelModel):
    """경쟁가 분포. 수집 가격 샘플의 25/50/75 분위수로 코드가 계산한다."""

    low_krw: int
    mid_krw: int
    high_krw: int
    #: 저가형·중간형·프리미엄 띠 폭 가중치
    weights: list[int] = Field(default_factory=lambda: [1, 1, 1])


class CompetitorRow(CamelModel):
    type: str
    price_range: str
    strength: str
    weakness: str
    strategy: str


class CompetitionResult(CamelModel):
    summary: str = ""
    stats: list[CompetitionStat] = Field(default_factory=list)
    price_band_krw: PriceBand | None = None
    table: list[CompetitorRow] = Field(default_factory=list)


class ShippingOption(CamelModel):
    method: ShippingMethod
    cost_krw: int
    cost_usd: float = 0.0
    eta_min_days: int = 0
    eta_max_days: int = 0
    recommended: bool = False
    #: 판매 유형 적합 뱃지. 예) 소량 판매에 적합
    fit_badge: str = ""
    description: str = ""


class LogisticsResult(CamelModel):
    options: list[ShippingOption] = Field(default_factory=list)
    packaging_used: Packaging | None = None
    #: 요율표 버전. 재현성 확보용.
    rate_version: str = "unknown"


class CostRow(CamelModel):
    """비용 차감 구조 한 행. 프론트 표 순서를 그대로 따른다.

    salePrice / supplyCost / platformFee / shipping / duty / vat / netProfit
    """

    key: str
    label: str
    amount_krw: int


class ExchangeRate(CamelModel):
    #: 현지통화 1단위당 원화
    krw_per_local: float
    currency: str
    as_of: str = ""


class PriceScenario(CamelModel):
    tier: PriceTier
    price_krw: int
    price_local: float
    net_profit_krw: int
    margin_rate: float
    #: 고정비 미입력이거나 순이익이 음수면 None
    break_even_units: int | None = None
    badge: str = ""
    summary: str = ""
    cost_rows: list[CostRow] = Field(default_factory=list)
    recommended: bool = False


class PricingResult(CamelModel):
    fx: ExchangeRate | None = None
    fee_schedule_version: str = "unknown"
    engine_version: str = "pricing-v1"
    recommended_tier: PriceTier = PriceTier.MID
    scenarios: list[PriceScenario] = Field(default_factory=list)
    verdict: MarginVerdict = MarginVerdict.GOOD
    verdict_reasons: list[str] = Field(default_factory=list)
    explanation: str = ""
    #: 계산에 반영된 비용 항목. 누락 검증용 (R-002-08)
    applied_badges: list[str] = Field(default_factory=list)
    #: 환율 ±10%, 수수료·VKFTA 적용 여부별 시나리오
    sensitivity: dict = Field(default_factory=dict)


class ChecklistItem(CamelModel):
    item: str
    required: bool = False


class RiskWarning(CamelModel):
    text: str
    source: str = ""
    source_url: str = ""
    effective_from: str = ""


class RiskResult(CamelModel):
    warnings: list[RiskWarning] = Field(default_factory=list)
    checklist: list[ChecklistItem] = Field(default_factory=list)
    difficulty: RiskDifficulty = RiskDifficulty.MID
    disclaimer: str = ""


class CountryResult(CamelModel):
    country: str
    status: CountryStatus = CountryStatus.RUNNING
    customs: CustomsResult | None = None
    scores: ScoreResult | None = None
    insight: InsightResult | None = None
    competition: CompetitionResult | None = None
    logistics: LogisticsResult | None = None
    pricing: PricingResult | None = None
    risk: RiskResult | None = None
    completed_nodes: list[str] = Field(default_factory=list)
    failed_nodes: list[str] = Field(default_factory=list)
    error_code: ErrorCode | None = None
    #: 근거 부족·품질 미달 사유. 프론트가 '검수 필요' 라벨로 쓴다.
    review_reasons: list[str] = Field(default_factory=list)


# ── 출력: 잡 단위 ───────────────────────────────────────────────────────


class GlobalResult(CamelModel):
    conclusion_title: str = ""
    conclusion_body: str = ""
    #: 진입점수 내림차순 국가 코드
    ranking: list[str] = Field(default_factory=list)
    best_country: str | None = None
    investigation_summary: str = ""
    next_action: str = ""


class Usage(CamelModel):
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class AnalysisResult(CamelModel):
    schema_version: str = SCHEMA_VERSION
    job_id: str
    global_: GlobalResult = Field(default_factory=GlobalResult, alias="global")
    countries: list[CountryResult] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
