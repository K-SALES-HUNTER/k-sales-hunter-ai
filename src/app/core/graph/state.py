"""LangGraph state 정의.

국가 fan-out 구조:
    AnalysisState  잡 전체. 국가별 결과를 병합해 모은다.
    CountryState   Send 로 분기된 국가 하나의 파이프라인.

MVP 는 countries=["VN","SG","TH"] 3개국이다. 프론트 트리·카드·랭킹이 3개국 전제다.

[노드 작성자에게]
    노드는 CountryState 를 받아 "바뀐 키만" dict 로 반환한다.
    Annotated[list, operator.add] 가 붙은 키는 반환값이 누적되고, 나머지는 덮어쓴다.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class JobMeta(TypedDict, total=False):
    """모든 노드가 공유하는 식별자. 로그와 이벤트에 그대로 전파된다."""

    job_id: str
    trace_id: str
    user_id: int


class CountryState(TypedDict, total=False):
    """국가 하나의 분석 파이프라인 state."""

    meta: JobMeta
    country: str

    # ── 입력 (스냅샷 고정값) ──────────────────────────────
    product: dict[str, Any]
    market_profile: dict[str, Any] | None
    preferences: dict[str, Any]

    # ── 노드 산출물 ───────────────────────────────────────
    product_features: dict[str, Any] | None  # PRODUCT_UNDERSTANDING
    customs: dict[str, Any] | None  # CUSTOMS_GATE
    market_raw: dict[str, Any] | None  # MARKET_RESEARCH
    scores: dict[str, Any] | None  # MARKET_EVALUATE
    competition: dict[str, Any] | None  # MARKET_EVALUATE
    insight: dict[str, Any] | None  # MARKET_INSIGHT
    logistics: dict[str, Any] | None  # LOGISTICS_ESTIMATE
    pricing: dict[str, Any] | None  # MARGIN
    risk: dict[str, Any] | None  # RISK_CHECKLIST

    # ── 실행 추적 ─────────────────────────────────────────
    completed_nodes: Annotated[list[str], operator.add]
    failed_nodes: Annotated[list[str], operator.add]
    review_reasons: Annotated[list[str], operator.add]
    error: dict[str, Any] | None
    #: 통관 PROHIBITED. 프론트 국가 목록에서 제외하되 사유는 남긴다.
    filtered_out: bool
    #: 중단 신호. True 면 남은 노드가 통과만 한다 (실패·취소·게이트 차단 공용).
    halted: bool


class AnalysisState(TypedDict, total=False):
    """잡 전체 state."""

    meta: JobMeta
    countries: list[str]
    product: dict[str, Any]
    market_profile: dict[str, Any] | None
    preferences: dict[str, Any]

    #: 부분 재실행 입력
    changed_fields: list[str]
    force_rerun_nodes: list[str]
    previous_result: dict[str, Any] | None

    #: fan-in 결과. 국가별 CountryState 가 여기에 누적된다.
    country_results: Annotated[list[dict[str, Any]], operator.add]

    #: REPORT_COMPOSE 산출물
    ranking: list[str]
    global_result: dict[str, Any] | None


class ContentState(TypedDict, total=False):
    """content_graph state (R-003)."""

    meta: JobMeta
    country: str
    locale: str
    product: dict[str, Any]
    sales_info: dict[str, Any]
    analysis: dict[str, Any]
    market_profile: dict[str, Any] | None
    revision_instruction: str | None

    usps: list[str]
    draft_ko: dict[str, Any] | None
    local: dict[str, Any] | None
    quality_score: int
    quality_issues: list[dict[str, Any]]
    regeneration_count: int
    status: str


class CopilotState(TypedDict, total=False):
    """copilot_graph state (R-005)."""

    meta: JobMeta
    message: str
    history: list[dict[str, str]]
    context: dict[str, Any]

    intent: str
    answer: str | None
    action: dict[str, Any] | None
    sources: list[dict[str, Any]]
