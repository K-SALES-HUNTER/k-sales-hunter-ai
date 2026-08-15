"""마진 계산 엔진.

요구사항: R-002-03 ~ R-002-05, R-002-08

[구현 예시]

[철칙] 이 패키지에서는 LLM 을 import 하지 않는다.
       숫자는 코드가 계산하고, 해설은 margin_explain 노드가 담당한다.

[철칙] float 을 쓰지 않는다. 모든 금액은 Decimal 이다.
       통화별 소수 자릿수와 반올림 모드를 명시한다.

계산 순서
    1. 현지 판매가 결정 (사용자 지정 or 목표 마진 역산)
    2. 플랫폼 수수료 차감 -> 정산액
    3. 원가 + 배송비 + 관세 + VAT + 기타 변동비 합산
    4. 순이익 / 마진율 / 손익분기 수량
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

ENGINE_VERSION = "pricing-v1"

#: 통화별 최소 단위. VND 는 소수점을 쓰지 않는다.
CURRENCY_EXPONENT: dict[str, int] = {"KRW": 0, "VND": 0, "USD": 2}


def quantize(amount: Decimal, currency: str) -> Decimal:
    exponent = CURRENCY_EXPONENT.get(currency, 2)
    return amount.quantize(Decimal(1).scaleb(-exponent), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PricingInput:
    # 원가 (KRW)
    supply_cost: Decimal
    # 배송비 (KRW)
    shipping_cost: Decimal
    # 기타 변동비 (KRW). 포장비, 쿠폰 부담액 등
    other_variable_cost: Decimal = Decimal(0)

    # 판매 조건 (현지통화)
    selling_price: Decimal | None = None      # 직접 지정
    target_margin_rate: Decimal | None = None  # 역산용. 0.30 = 30%
    local_currency: str = "VND"

    # 환율: 현지통화 1단위당 KRW
    exchange_rate: Decimal = Decimal("0.055")

    # 요율
    platform_fee_rate: Decimal = Decimal("0.06")   # Shopee 수수료
    payment_fee_rate: Decimal = Decimal("0.02")
    duty_rate: Decimal = Decimal(0)
    vat_rate: Decimal = Decimal("0.10")

    # BEP 입력
    fixed_cost: Decimal = Decimal(0)

    # 재현성을 위한 버전 스냅샷
    fee_schedule_version: str = "unknown"
    tariff_rule_version: str = "unknown"
    shipping_rate_version: str = "unknown"


@dataclass
class PricingOutput:
    selling_price_local: Decimal
    settlement_amount_krw: Decimal
    total_cost_krw: Decimal
    net_profit_krw: Decimal
    margin_rate: Decimal
    break_even_units: int | None
    cost_breakdown: dict[str, Decimal] = field(default_factory=dict)
    engine_version: str = ENGINE_VERSION


def calculate(spec: PricingInput) -> PricingOutput:
    """단위 손익을 계산한다."""
    if spec.selling_price is None and spec.target_margin_rate is None:
        raise ValueError("selling_price 또는 target_margin_rate 중 하나는 필요하다")

    base_cost = spec.supply_cost + spec.shipping_cost + spec.other_variable_cost

    if spec.selling_price is not None:
        selling_local = spec.selling_price
    else:
        selling_local = _reverse_price(spec, base_cost)

    selling_krw = selling_local * spec.exchange_rate

    platform_fee = selling_krw * spec.platform_fee_rate
    payment_fee = selling_krw * spec.payment_fee_rate
    settlement = selling_krw - platform_fee - payment_fee

    # 관세/VAT 는 과세가격(원가 + 배송비) 기준으로 단순화한다.
    # 실제 부담 주체와 과세표준은 기획 확정 후 조정한다.
    dutiable = spec.supply_cost + spec.shipping_cost
    duty = dutiable * spec.duty_rate
    vat = (dutiable + duty) * spec.vat_rate

    total_cost = base_cost + duty + vat
    net_profit = settlement - total_cost
    margin_rate = (net_profit / selling_krw) if selling_krw else Decimal(0)

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
            "platform_fee": quantize(platform_fee + payment_fee, "KRW"),
            "duty": quantize(duty, "KRW"),
            "vat": quantize(vat, "KRW"),
            "other_variable_cost": quantize(spec.other_variable_cost, "KRW"),
            "total_cost": quantize(total_cost, "KRW"),
        },
    )


def _reverse_price(spec: PricingInput, base_cost: Decimal) -> Decimal:
    """목표 마진율을 만족하는 현지 판매가를 역산한다. (R-002-05 권장 판매가)

        settlement - cost = price_krw * margin
        price_krw * (1 - fee) - cost = price_krw * margin
        price_krw = cost / (1 - fee - margin)
    """
    dutiable = spec.supply_cost + spec.shipping_cost
    duty = dutiable * spec.duty_rate
    vat = (dutiable + duty) * spec.vat_rate
    total_cost = base_cost + duty + vat

    fee = spec.platform_fee_rate + spec.payment_fee_rate
    denominator = Decimal(1) - fee - spec.target_margin_rate  # type: ignore[operator]
    if denominator <= 0:
        raise ValueError("목표 마진과 수수료 합이 100% 이상이라 판매가를 역산할 수 없다")

    price_krw = total_cost / denominator
    return price_krw / spec.exchange_rate


def scenarios(spec: PricingInput, deltas: tuple[Decimal, ...] = ()) -> dict[str, PricingOutput]:
    """Low / Mid / High 가격 시나리오. (R-002-06, 2차 범위)"""
    raise NotImplementedError
