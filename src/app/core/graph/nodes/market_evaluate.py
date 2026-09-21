"""MARKET_EVALUATE — 시장 3축 평가 + 경쟁가 밴드 (요구사항 R-001-05/06).

추론과 계산을 분리한다.
    LLM  : 수요·경쟁강도·K트렌드 적합도를 0~100 으로 평가하고 근거를 인용한다.
    코드 : 가중합(0.35 / 0.25 / 0.25)으로 시장 부분점수를 낸다. 최대 85점.

Critic 루프
    (1) 축마다 근거가 있는가 (2) 근거 논조와 점수 방향이 모순되지 않는가
    실패하면 지적 사항을 프롬프트에 주입해 최대 2회 재평가, 초과하면 검수 필요 라벨.

경쟁가 밴드는 수집된 가격 샘플의 25/50/75 분위수로 코드가 계산한다.
수익성 축은 여기서 못 낸다. 마진·리스크 결과가 필요해 REPORT_COMPOSE 에서 합산한다.

담당: 차은호   상태: stub
"""

from __future__ import annotations

from app.contracts.v1 import NodeName
from app.core.graph.nodes import _stubs
from app.core.graph.runtime import node
from app.core.graph.state import CountryState
from app.core.pricing.scoring import axis_grade, market_partial_score


@node(NodeName.MARKET_EVALUATE)
async def run(state: CountryState) -> dict:
    country = state.get("country", "")

    # TODO(차은호): gpt-4o-mini CoT 평가 + Critic 루프로 교체. 아래는 임시값.
    axes = _stubs.AXES.get(country, {"demand": 50, "competition": 50, "k_fit": 50})
    demand, competition, k_fit = axes["demand"], axes["competition"], axes["k_fit"]

    def axis(score: int, comment: str = "") -> dict:
        return {
            "score": score,
            "grade": axis_grade(score).value,
            "evidence": [],
            "comment": comment,
        }

    return {
        "scores": {
            "demand": axis(demand),
            "competition": axis(competition),
            "k_fit": axis(k_fit),
            "market_partial": market_partial_score(demand, competition, k_fit),
            "critic_attempts": 0,
        },
        "competition": {
            "summary": "",
            "stats": [],
            "price_band_krw": _stubs.PRICE_BAND.get(country),
            "table": [],
        },
    }
