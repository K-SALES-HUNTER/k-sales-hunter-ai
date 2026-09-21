"""REPORT_COMPOSE — 결과 종합과 1차 보고서 (요구사항 R-000-04).

국가별 파이프라인이 모두 끝난 뒤 fan-in 지점에서 딱 한 번 돈다.

하는 일
    1. 수익성 점수를 계산한다. 마진·리스크 결과가 있어야 나오므로 여기서만 가능하다.
       (MARKET_EVALUATE 시점에는 아직 마진이 없어 3축 부분점수까지만 낸다)
    2. 진입점수를 확정하고 국가를 정렬한다. 금지품목 국가는 0점 하드 컷으로 랭킹에서 뺀다.
    3. 종합 결론·조사 요약·다음 액션을 LLM 으로 1회 생성한다.

[규칙] 점수 계산은 core/pricing/scoring.py 의 순수 함수만 쓴다. LLM 은 문장만 만든다.

담당: 이동건
"""

from __future__ import annotations

import json

from app.contracts.v1 import COUNTRY_NAMES, CountryStatus, CustomsLevel, NodeName
from app.core.agents import prompts
from app.core.agents.schemas import GlobalConclusion
from app.core.graph.runtime import node
from app.core.graph.state import AnalysisState
from app.core.pricing import scoring
from app.infra.llm import Model, complete_json
from app.observability.logging import get_logger

log = get_logger(node="REPORT_COMPOSE")


def _profit_sub_scores(country: dict) -> dict[str, float]:
    """수익성 하위 5지표. 마진·리스크·경쟁가 결과에서 뽑는다."""
    pricing = country.get("pricing") or {}
    scenarios = pricing.get("scenarios") or []
    recommended = next(
        (item for item in scenarios if item.get("recommended")),
        scenarios[0] if scenarios else {},
    )
    margin_rate = float(recommended.get("margin_rate", 0.0))
    band = (country.get("competition") or {}).get("price_band_krw")
    customs_level = (country.get("customs") or {}).get("level", CustomsLevel.UNKNOWN.value)

    return {
        "unit_margin": scoring.unit_margin_score(margin_rate),
        # TODO(권수현): 환율 -10% 시나리오가 생기면 실제 값으로 교체
        "cost_stability": scoring.cost_stability_score(margin_rate, margin_rate * 0.85),
        "price_fit": scoring.price_fit_score(int(recommended.get("price_krw", 0)), band),
        "bep_feasibility": scoring.bep_feasibility_score(recommended.get("break_even_units")),
        "risk_stability": scoring.risk_stability_score(customs_level),
    }


def _finalize_scores(country: dict) -> dict:
    """국가 하나의 진입점수를 확정한다.

    게이트에서 막히거나 중간에 실패한 국가는 시장 3축이 없다.
    점수를 억지로 만들지 않고 비워 둔다. 랭킹에서도 빠진다.
    """
    scores = dict(country.get("scores") or {})
    if "demand" not in scores:
        country["scores"] = None
        return country

    customs = country.get("customs") or {}
    prohibited = customs.get("level") == CustomsLevel.PROHIBITED.value

    profit = scoring.profitability_score(_profit_sub_scores(country), prohibited=prohibited)
    market_partial = float(scores.get("market_partial", 0.0))
    total = scoring.entry_score(market_partial, profit)
    grade = scoring.entry_grade(total)

    scores["profitability"] = {
        "score": int(round(profit)),
        "grade": scoring.axis_grade(profit).value,
        "evidence": [],
        "comment": "",
    }
    scores["entry_score"] = total
    scores["entry_grade"] = grade.value
    country["scores"] = scores
    return country


async def _write_conclusion(countries: list[dict], job_id: str) -> GlobalConclusion:
    """국가 카드 요약만 넣는다. 원본 전체를 넣으면 토큰이 낭비되고 환각이 는다."""
    digest = [
        {
            "country": COUNTRY_NAMES.get(item["country"], item["country"]),
            "code": item["country"],
            "status": item.get("status"),
            "entryScore": (item.get("scores") or {}).get("entry_score"),
            "entryGrade": (item.get("scores") or {}).get("entry_grade"),
            "customs": (item.get("customs") or {}).get("level"),
            "positioning": (item.get("insight") or {}).get("positioning_label"),
            "recommendedPriceKrw": next(
                (
                    scenario.get("price_krw")
                    for scenario in ((item.get("pricing") or {}).get("scenarios") or [])
                    if scenario.get("recommended")
                ),
                None,
            ),
        }
        for item in countries
    ]

    prompt = prompts.load("report_compose")
    return await complete_json(
        schema=GlobalConclusion,
        system=prompt.body,
        user=json.dumps(digest, ensure_ascii=False, indent=2),
        model=Model.MAIN,
        prompt_version=prompt.version,
        node=NodeName.REPORT_COMPOSE.value,
        job_id=job_id,
    )


@node(NodeName.REPORT_COMPOSE)
async def run(state: AnalysisState) -> dict:
    results = list(state.get("country_results") or [])
    if not results:
        log.warning("국가 결과가 비어 있다")
        return {"ranking": [], "global_result": {}}

    scored = [_finalize_scores(dict(item)) for item in results]

    #: 판매 불가 국가는 랭킹에서 뺀다. 결과 자체는 사유와 함께 남긴다.
    rankable = [
        item
        for item in scored
        if item.get("status") not in (CountryStatus.FILTERED_OUT.value, CountryStatus.FAILED.value)
    ]
    rankable.sort(key=lambda item: (item.get("scores") or {}).get("entry_score", 0), reverse=True)

    for index, item in enumerate(rankable, start=1):
        scores = item["scores"]
        scores["rank"] = index
        scores["fit_grade"] = scoring.fit_grade(
            index, scoring.entry_grade(scores["entry_score"])
        ).value

    ranking = [item["country"] for item in rankable]
    conclusion = await _write_conclusion(scored, state.get("meta", {}).get("job_id", ""))

    return {
        "country_results": [],  # 이미 누적돼 있다. 덮어쓰지 않는다.
        "ranking": ranking,
        "global_result": {
            "conclusion_title": conclusion.conclusion_title,
            "conclusion_body": conclusion.conclusion_body,
            "investigation_summary": conclusion.investigation_summary,
            "next_action": conclusion.next_action,
            "ranking": ranking,
            "best_country": ranking[0] if ranking else None,
            #: 점수가 확정된 국가 결과. runner 가 이걸로 최종 result 를 만든다.
            "scored": scored,
        },
    }
