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

from dataclasses import replace
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

#: 추천가 대비 Low / High 배수. 배수라서 추천가가 밴드 경계에 걸려도 3안이 항상 다른 가격이다.
LOW_RATIO = Decimal("0.76")
HIGH_RATIO = Decimal("1.31")

#: 민감도 폭. 환율 ±10%, 수수료 +5%p(Shopee 프로그램 가입 등)
FX_SHOCK = Decimal("0.10")
FEE_SHOCK = Decimal("0.05")

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
        tax_base=fee.tax_base,
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
    """배송비 선택. 사용자가 고른 방식 → 추천 방식(SLS) → 첫 번째 방식 순으로 고른다.

    배송비는 마진 메이커가 계산하지 않는다. LOGISTICS_ESTIMATE 노드(배송통관 AI)의 산출값을 쓴다.
    """
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


def sensitivity(spec: PricingInput, fee) -> dict:  # noqa: ANN001
    """추천안 기준 민감도. 환율 ±10%, 수수료 +5%p, (있으면) VKFTA 세율.

    판매가(현지통화)는 그대로 두고 조건만 바꿔 다시 계산한다.
    "지금 정한 가격으로 팔 때 외부 조건이 흔들리면 얼마가 남는가" 를 본다.

    쓰는 곳
        fx_down_10  → report_compose 의 수익성 하위지표 '비용 안정성' 입력
        나머지       → 프론트 민감도 표, 코파일럿 답변 근거
    """

    def pick(out: PricingOutput) -> dict:
        return {"net_profit_krw": int(out.net_profit_krw), "margin_rate": float(out.margin_rate)}

    #: 환율이 바뀌면 같은 현지 판매가의 원화 매출이 바뀐다
    cases = {
        "fx_down_10": replace(spec, exchange_rate=spec.exchange_rate * (1 - FX_SHOCK)),
        "fx_up_10": replace(spec, exchange_rate=spec.exchange_rate * (1 + FX_SHOCK)),
        "fee_plus_5": replace(spec, platform_fee_rate=spec.platform_fee_rate + FEE_SHOCK),
    }
    if fee.duty_rate_vkfta is not None:
        cases["vkfta"] = replace(spec, duty_rate=fee.duty_rate_vkfta)
    return {name: pick(calculate(case)) for name, case in cases.items()}


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
    fx = get_fx_provider()
    fee = fee_module.load(country)  # data/fee_schedules/{VN,SG,TH}.yaml
    fx_rate = Decimal(str(await fx.rate(fee.currency)))
    base = {
        "fee": fee,
        "supply_cost_krw": int(product.get("supply_cost_krw", 0)),
        "shipping_cost_krw": _pick_shipping_cost(logistics, preferences.get("shipping_method")),
        "fx_rate": fx_rate,
        "fixed_cost_krw": int(preferences.get("fixed_cost_krw", 0)),
    }
    target = Decimal(str(preferences.get("target_margin_rate", 0.25)))

    # ① 목표 마진(기본 25%)을 지키는 가격을 역산한다
    # ② 그 가격을 트렌드 헌터의 경쟁가 밴드(25~75 분위) 안으로 보정해 추천가(Mid)로 쓴다
    #    밴드 밖이면 '남지만 안 팔리는 가격' 이라 시장 가격 쪽으로 당긴다
    # ③ 보정 전 가격(target_krw)은 버리지 않고 결과에 남긴다
    #    critic 의 밴드 이탈 판정과 수익성 점수의 가격 적합성이 이 값을 쓴다
    #    (보정 후 추천가는 항상 밴드 안이라 그걸로 재면 판정이 무의미해진다)
    reverse = calculate(_build_input(**base, target_margin_rate=target))
    target_krw = int((reverse.selling_price_local * fx_rate).to_integral_value(ROUND_HALF_UP))
    mid_krw = target_krw
    if price_band and price_band.get("low_krw") and price_band.get("high_krw"):
        mid_krw = max(price_band["low_krw"], min(target_krw, price_band["high_krw"]))

    # ④ Low/High 는 추천가 기준 배수. 밴드 분위수를 쓰면 추천가가 밴드 경계에 걸렸을 때
    #    두 안이 같은 가격이 되므로 배수로 고정한다
    prices = {
        PriceTier.LOW: int(Decimal(mid_krw) * LOW_RATIO),
        PriceTier.MID: mid_krw,
        PriceTier.HIGH: int(Decimal(mid_krw) * HIGH_RATIO),
    }
    scenarios = []
    for tier, price_krw in prices.items():  # 3안 모두 같은 엔진으로 비용 차감 7행 산출
        spec = _build_input(**base, price_local=Decimal(price_krw) / fx_rate)
        scenarios.append(_scenario(tier, price_krw, calculate(spec), fee, fx_rate))
        if tier is PriceTier.MID:
            mid_spec = spec

    return {
        "fx": {
            "krw_per_local": float(fx_rate),
            "currency": fee.currency,
            "as_of": await fx.as_of(fee.currency),
        },
        "fee_schedule_version": fee.version,
        "engine_version": reverse.engine_version,
        "target_price_krw": target_krw,  # 보정 전 가격. critic·가격 적합성 점수용
        "recommended_tier": PriceTier.MID.value,
        "scenarios": scenarios,
        "sensitivity": sensitivity(mid_spec, fee),
        "applied_badges": APPLIED_BADGES,
    }


async def quote(request: QuoteRequest) -> QuoteResponse:
    """POST /internal/ai/pricing/quote 용. 가격 하나를 주면 그 가격의 손익만 낸다.

    호출하는 화면 (전부 LLM 없이 ms 단위 응답)
        국가별 보고서 › 배송 방식·포장 저장        → 3안 재계산 (price_krw 없음)
        판매 정보 › 최종 판매가 입력               → 그 가격의 손익 (price_krw 있음)
        판매 관리 › 가격 변경 '예상 영향'          → 그 가격의 손익
        코파일럿 pricing_quote 도구               → "가격 낮추면 마진?" 답변 근거
    """
    fx = get_fx_provider()
    fee = fee_module.load(request.country)
    fx_rate = Decimal(str(request.fx_override or await fx.rate(fee.currency)))

    options = estimate_options(
        country=request.country,
        weight_g=(request.packaging.weight_g if request.packaging else request.weight_g),
    )
    shipping_cost = _pick_shipping_cost(
        {"options": options},
        request.shipping_method.value if request.shipping_method else None,
    )

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

    out = calculate(
        _build_input(
            fee=fee,
            supply_cost_krw=request.supply_cost_krw,
            shipping_cost_krw=shipping_cost,
            fx_rate=fx_rate,
            fixed_cost_krw=request.fixed_cost_krw,
            price_local=Decimal(request.price_krw) / fx_rate,
        )
    )
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
            "as_of": "" if request.fx_override else await fx.as_of(fee.currency),
        },
        fee_schedule_version=fee.version,
        applied_badges=APPLIED_BADGES,
    )


__all__ = ["APPLIED_BADGES", "ShippingMethod", "quote", "quote_scenarios", "sensitivity"]
