"""MARGIN — 마진 계산 · 검증 · 해설 (요구사항 R-002-03~05 / 08 / 09 / 10).

세 단계를 한 노드에서 한다.
    calc    순수 계산. core/services/pricing_quote 를 그대로 호출한다.
            동기 API(POST /internal/ai/pricing/quote)와 같은 함수를 쓴다.
    critic  순이익 음수 / 마진율 10% 미만 / 추천가가 경쟁가 밴드 이탈이면 부정 판정.
    explain LLM 이 판정 결과를 문장으로 설명한다. 숫자는 만들지 않는다.

[철칙] 금액은 Decimal 로 계산한다. LLM 은 해설만 담당한다.

담당: 차은호 (계산 엔진은 권수현)   상태: stub
"""

from __future__ import annotations

from app.contracts.v1 import MarginVerdict, NodeName
from app.core.graph.runtime import node
from app.core.graph.state import CountryState
from app.core.services.pricing_quote import quote_scenarios


@node(NodeName.MARGIN)
async def run(state: CountryState) -> dict:
    result = await quote_scenarios(
        country=state.get("country", ""),
        product=state.get("product") or {},
        customs=state.get("customs") or {},
        logistics=state.get("logistics") or {},
        preferences=state.get("preferences") or {},
        price_band=(state.get("competition") or {}).get("price_band_krw"),
    )

    # TODO(차은호): critic 규칙 + gpt-4o 해설 추가.
    result.setdefault("verdict", MarginVerdict.GOOD.value)
    result.setdefault("verdict_reasons", [])
    result.setdefault("explanation", "")
    return {"pricing": result}
