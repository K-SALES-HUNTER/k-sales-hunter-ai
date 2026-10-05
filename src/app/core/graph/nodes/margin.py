"""MARGIN — 마진 계산 · 검증 · 해설 (요구사항 R-002-03~05 / 08 / 09 / 10).

세 단계를 한 노드에서 한다.
    calc    순수 계산. core/services/pricing_quote 를 그대로 호출한다.
            동기 API(POST /internal/ai/pricing/quote)와 같은 함수를 쓴다.
    critic  코드 규칙. 순이익 음수 → NON_VIABLE, 마진율 10% 미만 → RISK.
            목표 마진 가격(밴드 보정 전)이 경쟁가 밴드를 벗어나면 사유로 남긴다.
    explain LLM 이 판정 결과를 문장으로 설명한다. 숫자는 만들지 않는다.

[철칙] 금액은 Decimal 로 계산한다. LLM 은 해설만 담당한다.

담당: 이동건 (마진 메이커 R-002)
"""

from __future__ import annotations

import json
from decimal import Decimal

from app.contracts.v1 import MarginVerdict, NodeName
from app.core.agents import prompts
from app.core.agents.schemas import MarginExplanation
from app.core.graph.runtime import node
from app.core.graph.state import CountryState
from app.core.services.pricing_quote import quote_scenarios
from app.infra.llm import Model, complete_json

RISK_MARGIN = Decimal("0.10")  # 마진율 10% 미만이면 RISK


def critic(result: dict, band: dict | None) -> tuple[MarginVerdict, list[str]]:
    """수익성 판정. LLM 미개입, 같은 입력이면 항상 같은 판정."""
    mid = next(s for s in result["scenarios"] if s["recommended"])
    target = result["target_price_krw"]  # 밴드 보정 전, 목표 마진을 지키는 가격
    verdict, reasons = MarginVerdict.GOOD, []
    if mid["net_profit_krw"] < 0:
        verdict, reasons = MarginVerdict.NON_VIABLE, ["추천가에서도 순이익이 음수"]
    elif Decimal(str(mid["margin_rate"])) < RISK_MARGIN:
        verdict, reasons = MarginVerdict.RISK, [f"마진율 {mid['margin_rate']:.1%} 로 10% 미만"]
    if band and not band["low_krw"] <= target <= band["high_krw"]:
        side = "상단 초과" if target > band["high_krw"] else "하단 미만"
        reasons.append(f"목표 마진 가격 {target:,}원이 경쟁가 밴드 {side} → 추천가를 밴드로 보정")
    return verdict, reasons


@node(NodeName.MARGIN)
async def run(state: CountryState) -> dict:
    band = (state.get("competition") or {}).get("price_band_krw")
    # ① calc — 동기 API(POST /internal/ai/pricing/quote) 와 같은 함수
    result = await quote_scenarios(
        country=state["country"],
        product=state.get("product") or {},
        customs=state.get("customs") or {},
        logistics=state.get("logistics") or {},
        preferences=state.get("preferences") or {},
        price_band=band,
    )
    # ② critic — 코드 규칙. 같은 입력이면 항상 같은 판정 (LLM 을 거치지 않는다)
    verdict, reasons = critic(result, band)
    # ③ explain — gpt-4o 는 문장만. 숫자는 입력값만 인용 (JSON 스키마 강제)
    prompt = prompts.load("margin_explain")
    explained = await complete_json(
        schema=MarginExplanation,
        model=Model.MAIN,
        system=prompt.body,
        user=json.dumps(
            {
                "country": state["country"],
                "verdict": verdict.value,
                "reasons": reasons,
                "scenarios": result["scenarios"],
                "price_band_krw": band,
                "positioning": (state.get("insight") or {}).get("positioning_label"),
            },
            ensure_ascii=False,
        ),
        prompt_version=prompt.version,
        node=NodeName.MARGIN.value,
        job_id=(state.get("meta") or {}).get("job_id"),
    )
    # LLM 이 3개보다 적게 돌려줘도 실패시키지 않는다. 요약이 빈 안은 프론트가 숫자만 보여준다
    for scenario, summary in zip(result["scenarios"], explained.scenario_summaries, strict=False):
        scenario["summary"] = summary  # 3안별 한 줄 요약
    return {
        "pricing": {
            **result,
            "verdict": verdict.value,
            "verdict_reasons": reasons,
            "explanation": explained.explanation,
        }
    }
