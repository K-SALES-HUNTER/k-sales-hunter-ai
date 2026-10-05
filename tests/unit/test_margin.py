"""마진 메이커 공식 고정 (R-002).

이 테스트가 깨지면 알고리즘 명세서(제작설계서 66·67장)와 코드가 어긋난 것이다.
"""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from app.contracts.v1 import MarginVerdict, PriceTier
from app.core.graph.nodes.margin import critic
from app.core.pricing.engine import PricingInput, calculate
from app.core.services.pricing_quote import quote_scenarios

BASE = {"supply_cost": D(12800), "shipping_cost": D(9400)}
COUNTRY = {
    "VN": {
        "local_currency": "VND",
        "exchange_rate": D("0.055"),
        "duty_rate": D("0.06"),
        "vat_rate": D("0.10"),
        "tax_base": "CIF",
    },
    "TH": {
        "local_currency": "THB",
        "exchange_rate": D("39.0"),
        "duty_rate": D("0.10"),
        "vat_rate": D("0.07"),
        "tax_base": "CIF",
    },
    "SG": {
        "local_currency": "SGD",
        "exchange_rate": D("1160.5"),
        "duty_rate": D("0"),
        "vat_rate": D("0.09"),
        "tax_base": "SALE_PRICE",
    },
}


@pytest.mark.parametrize("country", ["VN", "TH", "SG"])
def test_역산한_권장가는_목표마진을_정확히_만든다(country: str):
    out = calculate(PricingInput(**BASE, target_margin_rate=D("0.25"), **COUNTRY[country]))
    assert out.margin_rate == D("0.2500")


def test_정산액은_매출에서_수수료_스택만_뺀다():
    # 매출 = 400,000 VND × 0.055 = 22,000원, 수수료 스택 = 22,000 × (0.072 + 0.02) = 2,024원
    out = calculate(PricingInput(**BASE, selling_price=D(400000), **COUNTRY["VN"]))
    assert out.settlement_amount_krw == D(22000 - 2024)


def test_CIF_는_원가와_배송비에_관세_VAT를_매긴다():
    out = calculate(PricingInput(**BASE, selling_price=D(400000), **COUNTRY["VN"]))
    duty = D(22200) * D("0.06")  # 1,332
    assert out.cost_breakdown["duty"] == D(1332)
    assert out.cost_breakdown["vat"] == ((D(22200) + duty) * D("0.10")).quantize(D(1))


def test_판매가_기준_과세는_매출에_GST를_매긴다():
    out = calculate(PricingInput(**BASE, selling_price=D(30), **COUNTRY["SG"]))
    assert out.cost_breakdown["vat"] == (D(30) * D("1160.5") * D("0.09")).quantize(D(1))


def test_고정비가_없거나_적자면_손익분기를_내지_않는다():
    no_fixed = calculate(PricingInput(**BASE, selling_price=D(400000), **COUNTRY["VN"]))
    assert no_fixed.break_even_units is None
    loss = calculate(
        PricingInput(**BASE, selling_price=D(100000), fixed_cost=D(500000), **COUNTRY["VN"])
    )
    assert loss.net_profit_krw < 0 and loss.break_even_units is None


def test_역산_불가능한_목표마진은_오류다():
    with pytest.raises(ValueError):
        calculate(PricingInput(**BASE, target_margin_rate=D("0.95"), **COUNTRY["VN"]))


async def test_추천가가_밴드_상단에_걸려도_3안은_서로_다르다():
    band = {"low_krw": 5000, "mid_krw": 10000, "high_krw": 30000}
    result = await quote_scenarios(
        country="VN",
        product={"supply_cost_krw": 12800},
        customs={},
        logistics={"options": [{"method": "SLS", "cost_krw": 9400, "recommended": True}]},
        preferences={"target_margin_rate": 0.25},
        price_band=band,
    )
    prices = {s["tier"]: s["price_krw"] for s in result["scenarios"]}
    assert result["target_price_krw"] > band["high_krw"]  # 목표 마진 가격은 밴드 밖
    assert prices[PriceTier.MID.value] == band["high_krw"]  # 추천가는 밴드로 보정
    assert len(set(prices.values())) == 3
    assert {"fx_down_10", "fx_up_10", "fee_plus_5"} <= result["sensitivity"].keys()


def _result(net: int, margin: float, target: int) -> dict:
    return {
        "target_price_krw": target,
        "scenarios": [{"recommended": True, "net_profit_krw": net, "margin_rate": margin}],
    }


def test_critic_판정은_순이익과_마진율로만_정한다():
    assert critic(_result(-500, -0.02, 20000), None)[0] is MarginVerdict.NON_VIABLE
    assert critic(_result(1500, 0.05, 20000), None)[0] is MarginVerdict.RISK
    assert critic(_result(7000, 0.25, 20000), None)[0] is MarginVerdict.GOOD


def test_목표마진_가격이_밴드를_벗어나면_사유를_남긴다():
    verdict, reasons = critic(_result(7000, 0.25, 41000), {"low_krw": 5000, "high_krw": 30000})
    assert verdict is MarginVerdict.GOOD
    assert any("상단 초과" in r for r in reasons)
