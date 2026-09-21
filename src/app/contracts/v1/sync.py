"""동기 서비스 계약 — 프론트 버튼 하나와 1:1.

product-fill     상품 등록 'AI 자동 채우기'
pricing/quote    배송·포장 저장, 최종가 입력, 가격 관리 영향표 (LLM 없음, ms 응답)
sales-info/suggest 판매 정보 'AI 가 자동으로 값을 채움'
copilot/messages AI 패널
"""

from __future__ import annotations

from pydantic import Field

from app.contracts.v1.analysis import (
    CostRow,
    ExchangeRate,
    MarketProfile,
    Packaging,
    PriceScenario,
    ProductSnapshot,
    ShippingOption,
)
from app.contracts.v1.base import SCHEMA_VERSION, CamelModel
from app.contracts.v1.enums import (
    CopilotAction,
    CopilotIntent,
    CopilotPage,
    PriceTier,
    ShippingMethod,
)

# ── product-fill ────────────────────────────────────────────────────────


class ProductFillRequest(CamelModel):
    name: str = ""
    category: str = ""
    description: str = ""
    selling_points: str = ""
    main_target: str = ""
    image_urls: list[str] = Field(default_factory=list)


class ProductFeatures(CamelModel):
    colors: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    shape: str = ""
    style: str = ""


class ProductFillResponse(CamelModel):
    """프론트는 비어 있던 필드에만 이 값을 채운다. 사용자 입력은 덮어쓰지 않는다."""

    category: str = ""
    description: str = ""
    selling_points: str = ""
    main_target: str = ""
    features: ProductFeatures = Field(default_factory=ProductFeatures)
    keywords: list[str] = Field(default_factory=list)
    k_trend_category: str = ""
    confidence: float = 0.0
    #: 이미지 분석 실패 시 false. 프론트가 '이미지 미반영' 라벨을 붙인다.
    image_used: bool = False


# ── pricing/quote ───────────────────────────────────────────────────────


class QuoteRequest(CamelModel):
    country: str
    supply_cost_krw: int
    weight_g: int
    packaging: Packaging | None = None
    shipping_method: ShippingMethod | None = None
    #: 지정하면 정방향(판매가 -> 마진), 없으면 target_margin_rate 로 역산한다.
    price_krw: int | None = None
    target_margin_rate: float = 0.25
    fixed_cost_krw: int = 0
    #: 경쟁가 밴드. 3안 생성 시 low/high 기준으로 쓴다.
    price_band_krw: dict | None = None
    #: 환율 고정 테스트용 오버라이드
    fx_override: float | None = None


class Quote(CamelModel):
    price_krw: int
    price_local: float
    net_profit_krw: int
    margin_rate: float
    break_even_units: int | None = None
    cost_rows: list[CostRow] = Field(default_factory=list)


class QuoteResponse(CamelModel):
    schema_version: str = SCHEMA_VERSION
    shipping_options: list[ShippingOption] = Field(default_factory=list)
    quote: Quote | None = None
    #: price_krw 를 주지 않았을 때만 3안을 만든다.
    scenarios: list[PriceScenario] = Field(default_factory=list)
    recommended_tier: PriceTier = PriceTier.MID
    fx: ExchangeRate | None = None
    fee_schedule_version: str = "unknown"
    applied_badges: list[str] = Field(default_factory=list)


# ── sales-info/suggest ──────────────────────────────────────────────────


class CategoryAttr(CamelModel):
    key: str
    label: str
    value: str = ""
    required: bool = False


class OptionSpec(CamelModel):
    name: str
    values: list[str] = Field(default_factory=list)


class SalesSuggestRequest(CamelModel):
    country: str
    product: ProductSnapshot
    #: 사용자가 이미 고른 카테고리가 있으면 그 안에서 속성만 채운다.
    category_id: str | None = None


class SalesSuggestResponse(CamelModel):
    schema_version: str = SCHEMA_VERSION
    category_id: str = ""
    category_label: str = ""
    category_attrs: list[CategoryAttr] = Field(default_factory=list)
    option1: OptionSpec | None = None
    option2: OptionSpec | None = None
    #: 옵션당 초기 재고 제안 한 줄
    stock_hint: str = ""


# ── copilot/messages ────────────────────────────────────────────────────


class ChatTurn(CamelModel):
    role: str  # user | ai
    text: str


class CopilotRequest(CamelModel):
    message: str
    page: CopilotPage = CopilotPage.TOTAL_REPORT
    country_code: str | None = None
    #: 현재 화면의 보고서·판매정보·상세 요약 JSON
    context: dict = Field(default_factory=dict)
    #: 최근 10턴
    history: list[ChatTurn] = Field(default_factory=list)
    product: ProductSnapshot | None = None
    market_profile: MarketProfile | None = None


class CopilotActionPlan(CamelModel):
    type: CopilotAction
    params: dict = Field(default_factory=dict)
    #: 프론트에 그대로 보여줄 한 줄. 예) 필리핀 분석을 시작했어요
    description: str = ""


class CopilotResponse(CamelModel):
    schema_version: str = SCHEMA_VERSION
    answer: str
    intent: CopilotIntent = CopilotIntent.QUERY
    #: 보고서에 영향을 주는 명령 3종일 때만 채워진다. Spring 이 잡을 만든다.
    action: CopilotActionPlan | None = None
    #: 정책 문서를 인용했다면 출처
    sources: list[dict] = Field(default_factory=list)
