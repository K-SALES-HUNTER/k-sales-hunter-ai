"""LangGraph state 정의. (구현 예시)

국가 fan-out 구조:
    AnalysisState  - 잡 전체. 국가별 결과를 병합해 모은다.
    CountryState   - Send 로 분기된 국가 하나의 파이프라인.

MVP는 countries=["VN"] 단일이지만 fan-out 구조 자체는 유지한다.
(R-000-03 요구사항이자 논문 주제)
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class JobMeta(TypedDict):
    """모든 노드가 공유하는 식별자. 로그와 이벤트에 그대로 전파된다."""

    job_id: int
    trace_id: str
    command_id: str
    user_id: int


class CountryState(TypedDict, total=False):
    """국가 하나의 분석 파이프라인 state."""

    meta: JobMeta
    country: str

    # 입력 (스냅샷 고정값)
    product: dict[str, Any]
    sales_preference: dict[str, Any] | None

    # 노드 산출물
    product_features: dict[str, Any] | None      # PRODUCT_UNDERSTANDING
    customs: dict[str, Any] | None               # CUSTOMS_GATE
    market_raw: dict[str, Any] | None            # MARKET_RESEARCH
    market_scores: dict[str, Any] | None         # MARKET_SCORE
    market_insight: dict[str, Any] | None        # MARKET_INSIGHT
    shipping_options: list[dict[str, Any]]       # LOGISTICS_ESTIMATE
    margin: dict[str, Any] | None                # MARGIN_CALC / CRITIC / EXPLAIN
    checklist: list[dict[str, Any]]              # RISK_CHECKLIST
    summary: str | None                          # REPORT_COMPOSE

    # 실행 추적
    completed_nodes: Annotated[list[str], operator.add]
    failed_nodes: Annotated[list[str], operator.add]
    error: dict[str, Any] | None
    filtered_out: bool                           # 통관 BLOCKED


class AnalysisState(TypedDict, total=False):
    """잡 전체 state."""

    meta: JobMeta
    countries: list[str]
    job_type: str
    product: dict[str, Any]
    sales_preference: dict[str, Any] | None

    # 부분 재실행 입력
    changed_fields: list[str]
    force_rerun_nodes: list[str]

    # fan-in 결과. 국가별 CountryState 가 여기에 누적된다.
    country_results: Annotated[list[dict[str, Any]], operator.add]

    ranking: list[str]
    global_summary: str | None


class ContentState(TypedDict, total=False):
    """content_graph state."""

    meta: JobMeta
    country: str
    target_language: str
    product: dict[str, Any]
    market_context: dict[str, Any]
    tone: dict[str, Any]
    revision_instruction: str | None

    draft: dict[str, Any] | None
    quality: dict[str, Any] | None
    regeneration_count: int
    review_ko: dict[str, Any] | None
    localized: dict[str, Any] | None
    content_status: str


class CopilotState(TypedDict, total=False):
    """copilot_graph state."""

    meta: JobMeta
    message: str
    history: list[dict[str, str]]
    context: dict[str, Any]

    intent_type: str                 # QUERY | COMMAND
    intent: str | None
    answer: str | None
    change_plan: dict[str, Any] | None
    sources: list[dict[str, Any]]
