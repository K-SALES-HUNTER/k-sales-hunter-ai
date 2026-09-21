r"""analysis_graph 조립 — 국가 fan-out + 순차 파이프라인 + fan-in.

    START
      ├─ Send(run_country, VN) ┐
      ├─ Send(run_country, SG) ├─ 병렬. 국가 수가 늘어도 가장 느린 국가 기준으로 끝난다.
      └─ Send(run_country, TH) ┘
                               └─▶ report_compose ─▶ END

국가 하나 안에서는 순차로 돈다 (country_graph).

    product_understanding ─▶ customs_gate ─┬─ BLOCKED ─▶ END (조기 종료)
                                           └─ 통과 ────▶ market_research ─▶ market_evaluate
                                              ─▶ market_insight ─▶ logistics_estimate
                                              ─▶ margin ─▶ risk_checklist ─▶ END

게이트 우선 원칙 (R-000-02)
    통관이 막힌 국가는 시장·마진 분석을 아예 하지 않는다. LLM 호출 비용을 아끼는 것이 목적이다.

[설계 메모] 국가 파이프라인을 서브그래프로 분리한 이유
    Send 로 보낸 노드의 반환값은 부모 state 채널에 병합된다. 8개 노드를 부모에 직접 달면
    3개국의 중간 산출물이 같은 키에서 충돌한다. 서브그래프로 감싸면 국가별 state 가 격리되고
    부모에는 country_results 하나만 누적된다.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.contracts.v1 import CountryStatus, NodeName
from app.core.graph.nodes import (
    customs_gate,
    logistics_estimate,
    margin,
    market_evaluate,
    market_insight,
    market_research,
    product_understanding,
    report_compose,
    risk_checklist,
)
from app.core.graph.state import AnalysisState, CountryState

#: 부모 그래프에서 국가 하나를 실행하는 노드 이름
RUN_COUNTRY = "run_country"


def build_country_graph():  # noqa: ANN201
    """국가 하나의 순차 파이프라인."""
    graph = StateGraph(CountryState)

    graph.add_node(NodeName.PRODUCT_UNDERSTANDING.value, product_understanding.run)
    graph.add_node(NodeName.CUSTOMS_GATE.value, customs_gate.run)
    graph.add_node(NodeName.MARKET_RESEARCH.value, market_research.run)
    graph.add_node(NodeName.MARKET_EVALUATE.value, market_evaluate.run)
    graph.add_node(NodeName.MARKET_INSIGHT.value, market_insight.run)
    graph.add_node(NodeName.LOGISTICS_ESTIMATE.value, logistics_estimate.run)
    graph.add_node(NodeName.MARGIN.value, margin.run)
    graph.add_node(NodeName.RISK_CHECKLIST.value, risk_checklist.run)

    graph.add_edge(START, NodeName.PRODUCT_UNDERSTANDING.value)
    graph.add_edge(NodeName.PRODUCT_UNDERSTANDING.value, NodeName.CUSTOMS_GATE.value)

    #: 게이트 결과에 따라 조기 종료하거나 나머지를 돈다
    graph.add_conditional_edges(
        NodeName.CUSTOMS_GATE.value,
        _after_customs_gate,
        {"blocked": END, "continue": NodeName.MARKET_RESEARCH.value},
    )

    graph.add_edge(NodeName.MARKET_RESEARCH.value, NodeName.MARKET_EVALUATE.value)
    graph.add_edge(NodeName.MARKET_EVALUATE.value, NodeName.MARKET_INSIGHT.value)
    graph.add_edge(NodeName.MARKET_INSIGHT.value, NodeName.LOGISTICS_ESTIMATE.value)
    graph.add_edge(NodeName.LOGISTICS_ESTIMATE.value, NodeName.MARGIN.value)
    graph.add_edge(NodeName.MARGIN.value, NodeName.RISK_CHECKLIST.value)
    graph.add_edge(NodeName.RISK_CHECKLIST.value, END)

    return graph.compile()


def _after_customs_gate(state: CountryState) -> str:
    """판매 불가면 이후 노드를 실행하지 않는다.

    근거는 이미 state 에 있고 Spring 이 감사용으로 저장한다. 사용자 화면에서만 제외된다.
    """
    return "blocked" if state.get("halted") or state.get("filtered_out") else "continue"


def _fan_out(state: AnalysisState) -> list[Send]:
    """국가별로 독립 파이프라인을 띄운다. MVP 는 VN·SG·TH 3개."""
    return [
        Send(
            RUN_COUNTRY,
            CountryState(
                meta=state["meta"],
                country=country,
                product=state["product"],
                market_profile=state.get("market_profile"),
                preferences=state.get("preferences", {}),
                completed_nodes=[],
                failed_nodes=[],
                review_reasons=[],
                filtered_out=False,
                halted=False,
            ),
        )
        for country in state.get("countries", [])
    ]


def _country_status(result: dict[str, Any]) -> CountryStatus:
    if result.get("filtered_out"):
        return CountryStatus.FILTERED_OUT
    if result.get("failed_nodes"):
        return CountryStatus.FAILED
    if result.get("review_reasons"):
        return CountryStatus.NEEDS_REVIEW
    return CountryStatus.DONE


async def _run_country(payload: CountryState) -> dict:
    """서브그래프를 돌리고 결과를 부모의 country_results 에 하나 얹는다."""
    from app.core.graph.runtime import current_job

    country_graph = build_country_graph()
    result: dict[str, Any] = await country_graph.ainvoke(payload)

    snapshot = {
        "country": result.get("country", payload.get("country", "")),
        "status": _country_status(result).value,
        "customs": result.get("customs"),
        "scores": result.get("scores"),
        "insight": result.get("insight"),
        "competition": result.get("competition"),
        "logistics": result.get("logistics"),
        "pricing": result.get("pricing"),
        "risk": result.get("risk"),
        "product_features": result.get("product_features"),
        "completed_nodes": result.get("completed_nodes", []),
        "failed_nodes": result.get("failed_nodes", []),
        "review_reasons": result.get("review_reasons", []),
        "error": result.get("error"),
    }

    ctx = current_job.get()
    if ctx is not None:
        ctx.mark_country(snapshot["country"], _country_status(result))
        await ctx.flush()

    return {"country_results": [snapshot]}


def build_analysis_graph():  # noqa: ANN201
    """잡 전체 그래프. runner 가 이걸 ainvoke 한다."""
    graph = StateGraph(AnalysisState)

    graph.add_node(RUN_COUNTRY, _run_country)
    graph.add_node(NodeName.REPORT_COMPOSE.value, report_compose.run)

    graph.add_conditional_edges(START, _fan_out, [RUN_COUNTRY])
    graph.add_edge(RUN_COUNTRY, NodeName.REPORT_COMPOSE.value)
    graph.add_edge(NodeName.REPORT_COMPOSE.value, END)

    return graph.compile()
