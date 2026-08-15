r"""analysis_graph 조립. (구현 예시 - 배선만, 노드 내부는 각 모듈에 위임)

    START
      -> fan_out (국가별 Send)
           -> product_understanding
           -> customs_gate ---- BLOCKED ---> filtered_out (종료)
                             \-- 통과 ----> market_research -> market_score
                                            -> market_insight -> logistics_estimate
                                            -> margin_calc -> margin_critic
                                            -> margin_explain -> risk_checklist
                                            -> country_done
      -> report_compose (fan-in)
    END
"""

from __future__ import annotations

from langgraph.constants import Send
from langgraph.graph import END, START, StateGraph

from app.contracts.v1 import NodeName

from .nodes import (
    customs_gate,
    logistics_estimate,
    margin_calc,
    margin_critic,
    margin_explain,
    market_insight,
    market_research,
    market_score,
    product_understanding,
    report_compose,
    risk_checklist,
)
from .state import AnalysisState, CountryState


def _fan_out(state: AnalysisState) -> list[Send]:
    """국가별로 독립 파이프라인을 띄운다. MVP는 VN 하나."""
    return [
        Send(
            NodeName.PRODUCT_UNDERSTANDING.value,
            CountryState(
                meta=state["meta"],
                country=country,
                product=state["product"],
                sales_preference=state.get("sales_preference"),
                shipping_options=[],
                checklist=[],
                completed_nodes=[],
                failed_nodes=[],
                filtered_out=False,
            ),
        )
        for country in state["countries"]
    ]


def _after_customs_gate(state: CountryState) -> str:
    """통관 게이트 분기.

    BLOCKED 면 이후 노드를 실행하지 않는다. 근거는 이미 state 에 남아 있고,
    Spring 이 내부 감사용으로 저장한다. 사용자 화면에서만 제외된다.
    """
    if state.get("filtered_out"):
        return "country_done"
    return NodeName.MARKET_RESEARCH.value


def build_analysis_graph(checkpointer=None):  # noqa: ANN001, ANN201
    g = StateGraph(AnalysisState)

    g.add_node(NodeName.PRODUCT_UNDERSTANDING.value, product_understanding.run)
    g.add_node(NodeName.CUSTOMS_GATE.value, customs_gate.run)
    g.add_node(NodeName.MARKET_RESEARCH.value, market_research.run)
    g.add_node(NodeName.MARKET_SCORE.value, market_score.run)
    g.add_node(NodeName.MARKET_INSIGHT.value, market_insight.run)
    g.add_node(NodeName.LOGISTICS_ESTIMATE.value, logistics_estimate.run)
    g.add_node(NodeName.MARGIN_CALC.value, margin_calc.run)
    g.add_node(NodeName.MARGIN_CRITIC.value, margin_critic.run)
    g.add_node(NodeName.MARGIN_EXPLAIN.value, margin_explain.run)
    g.add_node(NodeName.RISK_CHECKLIST.value, risk_checklist.run)
    g.add_node("country_done", _collect_country)
    g.add_node(NodeName.REPORT_COMPOSE.value, report_compose.run)

    g.add_conditional_edges(START, _fan_out)

    g.add_edge(NodeName.PRODUCT_UNDERSTANDING.value, NodeName.CUSTOMS_GATE.value)
    g.add_conditional_edges(NodeName.CUSTOMS_GATE.value, _after_customs_gate)
    g.add_edge(NodeName.MARKET_RESEARCH.value, NodeName.MARKET_SCORE.value)
    g.add_edge(NodeName.MARKET_SCORE.value, NodeName.MARKET_INSIGHT.value)
    g.add_edge(NodeName.MARKET_INSIGHT.value, NodeName.LOGISTICS_ESTIMATE.value)
    g.add_edge(NodeName.LOGISTICS_ESTIMATE.value, NodeName.MARGIN_CALC.value)
    g.add_edge(NodeName.MARGIN_CALC.value, NodeName.MARGIN_CRITIC.value)
    g.add_edge(NodeName.MARGIN_CRITIC.value, NodeName.MARGIN_EXPLAIN.value)
    g.add_edge(NodeName.MARGIN_EXPLAIN.value, NodeName.RISK_CHECKLIST.value)
    g.add_edge(NodeName.RISK_CHECKLIST.value, "country_done")
    g.add_edge("country_done", NodeName.REPORT_COMPOSE.value)
    g.add_edge(NodeName.REPORT_COMPOSE.value, END)

    return g.compile(checkpointer=checkpointer)


def _collect_country(state: CountryState) -> dict:
    """국가 파이프라인 결과를 부모 state 에 누적한다. (fan-in)"""
    raise NotImplementedError
