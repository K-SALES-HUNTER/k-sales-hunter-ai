"""마진 계산 서비스 — 잡과 동기 API 가 같은 함수를 쓴다.

두 군데서 호출된다.
    MARGIN 노드                    분석 잡 안에서 3안을 만든다
    POST /internal/ai/pricing/quote 배송·포장 저장, 최종가 입력, 가격 관리 영향표

프론트는 값을 바꿀 때마다 즉시 재계산을 기대한다. 그래서 LLM 을 쓰지 않고 ms 안에 답한다.

[철칙] 금액은 Decimal. float 로 계산하지 않는다.
[철칙] 이 모듈은 LLM 을 import 하지 않는다. 해설은 MARGIN 노드의 explain 단계가 붙인다.

담당: 이동건 (마진 메이커 R-002)
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.contracts.v1 import (
    COUNTRY_CURRENCY,
    PriceTier,
    QuoteRequest,
    QuoteResponse,
    ShippingMethod,
)
from app.core.pricing import fee_schedule as fee_module
from app.core.pricing.engine import PricingInput, PricingOutput, calculate
from app.core.pricing.shipping_rate import estimate_options
from app.core.providers import get_fx_provider

#: 반영된 비용 항목. 프론트가 뱃지로 보여준다. 누락 검증용 (R-002-08)
APPLIED_BADGES = ["관세 반영", "VAT 반영", "배송비 반영", "Shopee 수수료 반영", "환율 반영"]

#: 추천가 대비 Low / High 배수. TODO(이동건): 경쟁가 분위수 기반으로 교체.
_LOW_RATIO = Decimal("0.76")
_HIGH_RATIO = Decimal("1.31")

_TIER_BADGE = {
    PriceTier.LOW: "수익 낮음",
    PriceTier.MID: "추천",
    PriceTier.HIGH: "수익 높지만 구매 부담",
}


def _cost_rows(price_krw: int, out: PricingOutput, fee) -> list[dict]:  # noqa: ANN001
    """프론트 '비용 차감 구조' 표 순서 그대로."""
    breakdown = out.cost_breakdown
    duty_pct = int(fee.duty_rate * 100)
    vat_pct = int(fee.vat_rate * 100)
    vat_label = "GST" if fee.tariff_mode == "GST" else "VAT"
    return [
        {"key": "salePrice", "label": "판매가", "amount_krw": price_krw},
        {"key": "supplyCost", "label": "공급 원가", "amount_krw": -int(breakdown["supply_cost"])},
        {
            "key": "platformFee",
            "label": "Shopee 수수료",
            "amount_krw": -int(breakdown["platform_fee"]),
        },
        {"key": "shipping", "label": "국제 배송비", "amount_krw": -int(breakdown["shipping_cost"])},
        {"key": "duty", "label": f"관세 ({duty_pct}%)", "amount_krw": -int(breakdown["duty"])},
        {"key": "vat", "label": f"{vat_label} ({vat_pct}%)", "amount_krw": -int(breakdown["vat"])},
        {"key": "netProfit", "label": "예상 순이익", "amount_krw": int(out.net_profit_krw)},
    ]


def _build_input(
    *,
    fee,  # noqa: ANN001
    supply_cost_krw: int,
    shipping_cost_krw: int,
    fx_rate: Decimal,
    fixed_cost_krw: int,
    price_local: Decimal | None = None,
    target_margin_rate: Decimal | None = None,
) -> PricingInput:
    return PricingInput(
        supply_cost=Decimal(supply_cost_krw),
        shipping_cost=Decimal(shipping_cost_krw),
        selling_price=price_local,
        target_margin_rate=target_margin_rate,
        local_currency=fee.currency,
        exchange_rate=fx_rate,
        platform_fee_rate=fee.platform_fee_rate,
        payment_fee_rate=fee.payment_fee_rate,
        duty_rate=fee.duty_rate,
        vat_rate=fee.vat_rate,
        fixed_cost=Decimal(fixed_cost_krw),
        fee_schedule_version=fee.version,
    )


def _scenario(
    tier: PriceTier,
    price_krw: int,
    out: PricingOutput,
    fee,  # noqa: ANN001
    fx_rate: Decimal,
) -> dict:
    return {
        "tier": tier.value,
        "price_krw": price_krw,
        "price_local": float(Decimal(price_krw) / fx_rate) if fx_rate else 0.0,
        "net_profit_krw": int(out.net_profit_krw),
        "margin_rate": float(out.margin_rate),
        "break_even_units": out.break_even_units,
        "badge": _TIER_BADGE[tier],
        "summary": "",
        "cost_rows": _cost_rows(price_krw, out, fee),
        "recommended": tier is PriceTier.MID,
    }


def _pick_shipping_cost(logistics: dict, method: str | None) -> int:
    options = logistics.get("options") or []
    if not options:
        return 0
    if method:
        for option in options:
            if option.get("method") == method:
                return int(option.get("cost_krw", 0))
    for option in options:
        if option.get("recommended"):
            return int(option.get("cost_krw", 0))
    return int(options[0].get("cost_krw", 0))


async def quote_scenarios(
    *,
    country: str,
    product: dict,
    customs: dict,
    logistics: dict,
    preferences: dict,
    price_band: dict | None = None,
) -> dict:
    """MARGIN 노드용. Low / Mid / High 3안을 만든다."""
    fee = fee_module.load(country)
    fx_rate = Decimal(str(await get_fx_provider().rate(fee.currency)))
    supply_cost = int(product.get("supply_cost_krw", 0))
    shipping_cost = _pick_shipping_cost(logistics, preferences.get("shipping_method"))
    fixed_cost = int(preferences.get("fixed_cost_krw", 0))
    target = Decimal(str(preferences.get("target_margin_rate", 0.25)))

    #: 목표 마진을 만족하는 판매가를 역산한 뒤 경쟁가 밴드 안으로 당긴다
    reverse = calculate(
        _build_input(
            fee=fee,
            supply_cost_krw=supply_cost,
            shipping_cost_krw=shipping_cost,
            fx_rate=fx_rate,
            fixed_cost_krw=fixed_cost,
            target_margin_rate=target,
        )
    )
    mid_krw = int((reverse.selling_price_local * fx_rate).to_integral_value(ROUND_HALF_UP))
    if price_band:
        low_bound, high_bound = price_band.get("low_krw", 0), price_band.get("high_krw", 0)
        if low_bound and high_bound:
            mid_krw = max(low_bound, min(mid_krw, high_bound))

    prices = {
        PriceTier.LOW: int(Decimal(mid_krw) * _LOW_RATIO),
        PriceTier.MID: mid_krw,
        PriceTier.HIGH: int(Decimal(mid_krw) * _HIGH_RATIO),
    }

    scenarios = []
    for tier, price_krw in prices.items():
        out = calculate(
            _build_input(
                fee=fee,
                supply_cost_krw=supply_cost,
                shipping_cost_krw=shipping_cost,
                fx_rate=fx_rate,
                fixed_cost_krw=fixed_cost,
                price_local=Decimal(price_krw) / fx_rate,
            )
        )
        scenarios.append(_scenario(tier, price_krw, out, fee, fx_rate))

    return {
        "fx": {
            "krw_per_local": float(fx_rate),
            "currency": fee.currency,
            "as_of": "",
        },
        "fee_schedule_version": fee.version,
        "engine_version": reverse.engine_version,
        "recommended_tier": PriceTier.MID.value,
        "scenarios": scenarios,
        "applied_badges": APPLIED_BADGES,
    }


async def quote(request: QuoteRequest) -> QuoteResponse:
    """POST /internal/ai/pricing/quote 용. 가격 하나를 주면 그 가격의 손익만 낸다."""
    fee = fee_module.load(request.country)
    fx_rate = Decimal(str(request.fx_override or await get_fx_provider().rate(fee.currency)))

    options = estimate_options(
        country=request.country,
        weight_g=(request.packaging.weight_g if request.packaging else request.weight_g),
    )
    shipping_cost = _pick_shipping_cost(
        {"options": options},
        request.shipping_method.value if request.shipping_method else None,
    )

    base = {
        "fee": fee,
        "supply_cost_krw": request.supply_cost_krw,
        "shipping_cost_krw": shipping_cost,
        "fx_rate": fx_rate,
        "fixed_cost_krw": request.fixed_cost_krw,
    }

    if request.price_krw is None:
        result = await quote_scenarios(
            country=request.country,
            product={"supply_cost_krw": request.supply_cost_krw, "weight_g": request.weight_g},
            customs={},
            logistics={"options": options},
            preferences={
                "target_margin_rate": request.target_margin_rate,
                "fixed_cost_krw": request.fixed_cost_krw,
                "shipping_method": (
                    request.shipping_method.value if request.shipping_method else None
                ),
            },
            price_band=request.price_band_krw,
        )
        return QuoteResponse.model_validate({**result, "shipping_options": options, "quote": None})

    out = calculate(_build_input(**base, price_local=Decimal(request.price_krw) / fx_rate))
    return QuoteResponse(
        shipping_options=options,  # type: ignore[arg-type]
        quote={  # type: ignore[arg-type]
            "price_krw": request.price_krw,
            "price_local": float(Decimal(request.price_krw) / fx_rate),
            "net_profit_krw": int(out.net_profit_krw),
            "margin_rate": float(out.margin_rate),
            "break_even_units": out.break_even_units,
            "cost_rows": _cost_rows(request.price_krw, out, fee),
        },
        fx={  # type: ignore[arg-type]
            "krw_per_local": float(fx_rate),
            "currency": COUNTRY_CURRENCY.get(request.country, fee.currency),
            "as_of": "",
        },
        fee_schedule_version=fee.version,
        applied_badges=APPLIED_BADGES,
    )


__all__ = ["APPLIED_BADGES", "ShippingMethod", "quote", "quote_scenarios"]
