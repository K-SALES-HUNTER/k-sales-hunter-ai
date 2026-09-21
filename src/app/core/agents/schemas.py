"""LLM 에게 주는 출력 스키마.

[철칙] 계약 스키마(contracts/v1)와 여기를 분리한다.
       여기는 프롬프트를 튜닝하며 매주 바뀐다. 계약은 바꾸려면 협의가 필요하다.
       같은 모델을 두 용도로 쓰면 프롬프트를 개선할 때마다 Spring 이 깨진다.
       사이 변환은 core/agents/mappers.py 가 한다.

[규칙] 근거(evidence)가 필요한 스키마는 min_length=1 로 막는다.
       근거 없는 점수는 생성 단계에서 차단하는 것이 사후 검증보다 싸다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# ── REPORT_COMPOSE (담당: 이동건) ───────────────────────────────────────


class GlobalConclusion(BaseModel):
    """전체 보고서 종합 결론. 국가 카드 요약만 보고 1회 생성한다."""

    conclusion_title: str = Field(description="한 줄 결론. 예) 베트남 우선 진입을 추천합니다.")
    conclusion_body: str = Field(description="추천 근거 2~3문장. 숫자는 주어진 값만 인용한다.")
    investigation_summary: str = Field(description="어떤 국가를 어떤 기준으로 비교했는지 1~2문장")
    next_action: str = Field(description="다음에 할 일 제안 2~3문장")


# ── MARKET_EVALUATE (담당: 차은호) ──────────────────────────────────────
# TODO(차은호): 아래 두 스키마로 3축 평가와 Critic 을 구현한다.


class Axis(BaseModel):
    score: int = Field(ge=0, le=100)
    evidence: list[str] = Field(min_length=1, description="수집 데이터에서 인용. 지어내지 않는다.")
    reasoning: str


class MarketAxes(BaseModel):
    demand: Axis
    competition: Axis
    k_fit: Axis


class CriticVerdict(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)


# ── MARKET_INSIGHT (담당: 차은호) ───────────────────────────────────────


class MarketInsight(BaseModel):
    summary: str
    trends: list[str]
    positioning: str = Field(description="ENTRY | PREMIUM | FANDOM | GIFT 중 하나")
    positioning_reason: str
    conclusion_title: str
    conclusion_body: str


# ── PRODUCT_UNDERSTANDING / product_fill (담당: 강근우) ─────────────────


class ProductUnderstanding(BaseModel):
    category: str
    description: str
    selling_points: str
    main_target: str
    colors: list[str]
    materials: list[str]
    shape: str
    style: str
    keywords: list[str]
    k_trend_category: str
    confidence: float


# ── content_graph (담당: 강근우) ────────────────────────────────────────


class DetailContent(BaseModel):
    title: str = Field(max_length=120, description="Shopee 제목 규칙: 120자 이내")
    usps: list[str] = Field(min_length=3, max_length=6)
    sections: list[str] = Field(
        min_length=4, max_length=4, description="소개·특징·혜택·구매유도 순서"
    )
    specs: list[list[str]]
    breadcrumb: list[str]


# ── copilot (담당: 이동건) ──────────────────────────────────────────────


class CopilotAnswer(BaseModel):
    answer: str = Field(description="600자 이내. 숫자는 도구 결과만 인용한다.")
    intent: str = Field(description="QUERY | COMMAND | CLARIFY")
    action_type: str = Field(
        description="없으면 빈 문자열. ADD_COUNTRY | REANALYZE | REGENERATE_DETAIL"
    )
    action_params: dict = Field(default_factory=dict)
