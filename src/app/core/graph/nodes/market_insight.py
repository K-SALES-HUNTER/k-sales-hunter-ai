"""MARKET_INSIGHT — 소비 트렌드 요약과 포지셔닝 제안 (요구사항 R-001-07/08).

포지셔닝은 입문 / 프리미엄 / 팬덤 / 선물 4종 중 하나를 근거 문장과 함께 고른다.

구현 메모
    gpt-4o. 숫자는 만들지 말고 state 에 이미 있는 값만 인용하도록 프롬프트에 주입한다.
    마켓 정보(브랜드 방향·셀러 유형·타깃·톤)를 함께 넣어 셀러 맥락을 반영한다.

담당: 차은호 (트렌드 헌터 R-001)   상태: stub
"""

from __future__ import annotations

from app.contracts.v1 import COUNTRY_NAMES, NodeName
from app.core.graph.nodes import _stubs
from app.core.graph.runtime import node
from app.core.graph.state import CountryState


@node(NodeName.MARKET_INSIGHT)
async def run(state: CountryState) -> dict:
    country = state.get("country", "")
    name = COUNTRY_NAMES.get(country, country)

    # TODO(차은호): gpt-4o 호출로 교체. 아래는 임시값.
    positioning, label = _stubs.POSITIONING.get(country, ("ENTRY", "입문형"))
    return {
        "insight": {
            "summary": f"{name} 시장 분석 요약은 아직 생성되지 않았습니다.",
            "trends": [],
            "positioning": positioning,
            "positioning_label": label,
            "conclusion_title": f"{label} 포지션으로 판매",
            "conclusion_body": "",
        }
    }
