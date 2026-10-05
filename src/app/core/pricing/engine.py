"""마진 계산 엔진.

요구사항: R-002-03 ~ R-002-05, R-002-08

계산 순서 (아래 주석 1)~4) 와 같다)
    1. 비용요소 — 환율·요율은 호출부(services/pricing_quote)가 FxProvider·요율 YAML 에서 채워 넘긴다
    2. 쇼피 수수료 스택 — 커미션 + 거래 + 결제, 판매가 비례
    3. 정산액 · 세금 — 관세는 CIF 기준, VAT 는 과세기준(CIF / 판매가)에 따라
    4. 순이익 / 마진율 / 손익분기 수량

해설은 nodes/margin.py 의 explain 단계가 붙인다. 이 모듈은 숫자만 만든다.

설계 메모
    - 관세·VAT 는 정산액에서 빼지 않고 비용 쪽에 더한다. 순이익은 같지만
      "정산액 = 플랫폼이 셀러에게 입금하는 금액" 이라는 정의를 지키기 위함이다.
    - 과세기준(tax_base)은 국가별 요율 YAML 이 정한다.
        CIF        (원가 + 배송비) 에 관세, (원가 + 배송비 + 관세) 에 VAT  → VN · TH
        SALE_PRICE 판매가에 GST                                          → SG
    - 역산(_reverse_price)은 수수료·판매가 기준 세금이 판매가에 비례한다는 점을 이용해
      1차 방정식 한 번으로 푼다. 반복 탐색을 하지 않아 결과가 항상 같다.
    - 공식은 tests/unit/test_margin.py 가 고정한다. 깨지면 제작설계서 66·67장과 코드가 어긋난 것.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

# core/pricing/engine.py — 마진 계산 엔진 (R-002-03~05, 08)
# [철칙] 이 패키지는 LLM 을 import 하지 않는다. float 을 쓰지 않는다. 모든 금액은 Decimal.
ENGINE_VERSION = "pricing-v1"
CURRENCY_EXPONENT = {"KRW": 0, "VND": 0, "SGD": 2, "THB": 2}  # 통화별 최소 단위


def quantize(amount: Decimal, currency: str) -> Decimal:
    exp = CURRENCY_EXPONENT.get(currency, 2)
    return amount.quantize(Decimal(1).scaleb(-exp), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PricingInput:
    supply_cost: Decimal  # 원가 (KRW)
    shipping_cost: Decimal  # 배송비 (KRW) ← LOGISTICS_ESTIMATE 산출값 상속
    other_variable_cost: Decimal = Decimal(0)  # 포장비 등 기타 변동비 (KRW)
    selling_price: Decimal | None = None  # 판매가(현지통화) → 정방향
    target_margin_rate: Decimal | None = None  # 0.25 = 25% → 역방향
    local_currency: str = "VND"
    exchange_rate: Decimal = Decimal("0.055")  # 현지통화 1단위당 KRW (FxProvider)
    platform_fee_rate: Decimal = Decimal("0.072")  # 커미션 + 거래 (요율 YAML)
    payment_fee_rate: Decimal = Decimal("0.02")
    duty_rate: Decimal = Decimal(0)
    vat_rate: Decimal = Decimal("0.10")
    tax_base: str = "CIF"  # CIF: 원가+배송비 과세 | SALE_PRICE: 판매가 과세(SG GST)
    fixed_cost: Decimal = Decimal(0)  # BEP 입력
    fee_schedule_version: str = "unknown"  # 어떤 요율로 계산했는지 스냅샷
    tariff_rule_version: str = "unknown"
    shipping_rate_version: str = "unknown"


def calculate(spec: PricingInput) -> PricingOutput:
    if spec.selling_price is None and spec.target_margin_rate is None:
        raise ValueError("selling_price 또는 target_margin_rate 중 하나는 필요하다")
    # 1) 비용요소 — 환율·요율은 호출부(pricing_quote)가 FxProvider·요율 YAML 에서 채워 넘긴다
    base_cost = spec.supply_cost + spec.shipping_cost + spec.other_variable_cost
    if spec.selling_price is not None:
        selling_local = spec.selling_price
    else:
        selling_local = _reverse_price(spec, base_cost)  # 목표마진 → 권장가 역산
    selling_krw = selling_local * spec.exchange_rate
    # 2) 쇼피 수수료 스택 = 커미션 + 거래 + 결제 (판매가 비례)
    fee_stack = selling_krw * (spec.platform_fee_rate + spec.payment_fee_rate)
    # 3) 정산액 · 세금 — 관세는 CIF 기준, VAT 는 과세기준에 따라
    settlement = selling_krw - fee_stack
    dutiable = spec.supply_cost + spec.shipping_cost
    duty = dutiable * spec.duty_rate
    vat_base = (dutiable + duty) if spec.tax_base == "CIF" else selling_krw
    vat = vat_base * spec.vat_rate
    # 4) 순이익 · 마진율 · 손익분기 수량
    total_cost = base_cost + duty + vat
    net_profit = settlement - total_cost
    margin_rate = net_profit / selling_krw if selling_krw else Decimal(0)
    break_even = None
    if spec.fixed_cost > 0 and net_profit > 0:
        break_even = int((spec.fixed_cost / net_profit).to_integral_value(ROUND_HALF_UP))
    return PricingOutput(
        selling_price_local=quantize(selling_local, spec.local_currency),
        settlement_amount_krw=quantize(settlement, "KRW"),
        total_cost_krw=quantize(total_cost, "KRW"),
        net_profit_krw=quantize(net_profit, "KRW"),
        margin_rate=margin_rate.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        break_even_units=break_even,
        cost_breakdown={
            "supply_cost": quantize(spec.supply_cost, "KRW"),
            "shipping_cost": quantize(spec.shipping_cost, "KRW"),
            "platform_fee": quantize(fee_stack, "KRW"),
            "duty": quantize(duty, "KRW"),
            "vat": quantize(vat, "KRW"),
            "other_variable_cost": quantize(spec.other_variable_cost, "KRW"),
            "total_cost": quantize(total_cost, "KRW"),
        },
        engine_version=ENGINE_VERSION,
    )


def _reverse_price(spec: PricingInput, base_cost: Decimal) -> Decimal:
    """목표 마진율을 만족하는 현지 판매가 (R-002-05)

    매출 × (1 − 수수료율) − 비용 = 매출 × 목표마진  ⇒  매출 = 비용 / (1 − 수수료율 − 목표마진)
    판매가 기준 과세면 VAT 도 매출 비례 → 분모에서 VAT율을 함께 뺀다
    """
    dutiable = spec.supply_cost + spec.shipping_cost
    duty = dutiable * spec.duty_rate
    fee = spec.platform_fee_rate + spec.payment_fee_rate
    margin = spec.target_margin_rate or Decimal(0)
    if spec.tax_base == "CIF":
        cost = base_cost + duty + (dutiable + duty) * spec.vat_rate
        denominator = Decimal(1) - fee - margin
    else:  # SALE_PRICE (SG GST)
        cost = base_cost + duty
        denominator = Decimal(1) - fee - spec.vat_rate - margin
    if denominator <= 0:
        raise ValueError("목표 마진과 수수료·세율 합이 100% 이상이라 판매가를 역산할 수 없다")
    return (cost / denominator) / spec.exchange_rate  # KRW → 현지통화


@dataclass
class PricingOutput:
    """calculate() 결과. 금액은 전부 통화 최소단위로 반올림된 Decimal 이다."""

    selling_price_local: Decimal  # 판매가 (현지통화). 역산이면 계산된 권장가
    settlement_amount_krw: Decimal  # 정산액 = 매출 − 수수료 스택
    total_cost_krw: Decimal  # 원가 + 배송비 + 기타 변동비 + 관세 + VAT
    net_profit_krw: Decimal  # 정산액 − 총비용 (음수면 팔수록 손해)
    margin_rate: Decimal  # 순이익 / 원화 매출. 소수 4자리 (0.2500 = 25%)
    break_even_units: int | None  # 고정비 / 단위 순이익. 고정비 0 이거나 적자면 None
    #: 비용 차감 구조. pricing_quote._cost_rows 가 프론트 표 7행으로 바꾼다
    cost_breakdown: dict[str, Decimal] = field(default_factory=dict)
    #: 엔진 버전. 공식이 바뀌면 올려서 과거 결과와 구분한다
    engine_version: str = ENGINE_VERSION


def scenarios(spec: PricingInput, deltas: tuple[Decimal, ...] = ()) -> dict[str, PricingOutput]:
    """[미사용] 초기 설계의 자리. 가격 3안은 services/pricing_quote.quote_scenarios 가,
    민감도는 services/pricing_quote.sensitivity 가 만든다. 엔진은 단일 가격 계산만 책임진다."""
    raise NotImplementedError
