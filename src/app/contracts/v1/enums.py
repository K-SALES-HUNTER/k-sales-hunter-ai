"""계약 enum 모음.

[규칙] 프론트는 여기 값으로 분기하고 한국어 문구는 프론트가 매핑한다.
       Python 이 사용자 노출 문구를 만들지 않는다. (문구 수정 때문에 AI 서버를 재배포하지 않기 위함)
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_COMMAND_SCHEMA = "INVALID_COMMAND_SCHEMA"
    PRODUCT_SNAPSHOT_INCOMPLETE = "PRODUCT_SNAPSHOT_INCOMPLETE"
    IMAGE_FETCH_FAILED = "IMAGE_FETCH_FAILED"
    CUSTOMS_DATA_INSUFFICIENT = "CUSTOMS_DATA_INSUFFICIENT"
    CUSTOMS_BLOCKED = "CUSTOMS_BLOCKED"
    MARKET_DATA_UNAVAILABLE = "MARKET_DATA_UNAVAILABLE"
    LLM_STRUCTURED_OUTPUT_FAILED = "LLM_STRUCTURED_OUTPUT_FAILED"
    LLM_RATE_LIMITED = "LLM_RATE_LIMITED"
    CONTENT_QUALITY_BELOW_THRESHOLD = "CONTENT_QUALITY_BELOW_THRESHOLD"
    EXTERNAL_API_UNAVAILABLE = "EXTERNAL_API_UNAVAILABLE"
    SALES_INFO_INVALID = "SALES_INFO_INVALID"
    COPILOT_INTENT_UNCLEAR = "COPILOT_INTENT_UNCLEAR"
    DAILY_BUDGET_EXCEEDED = "DAILY_BUDGET_EXCEEDED"
    JOB_ALREADY_RUNNING = "JOB_ALREADY_RUNNING"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    JOB_CANCELLED = "JOB_CANCELLED"
    JOB_TIMEOUT = "JOB_TIMEOUT"
    JOB_INTERRUPTED = "JOB_INTERRUPTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class JobType(StrEnum):
    ANALYSIS = "ANALYSIS"
    CONTENT = "CONTENT"
    IMAGE = "IMAGE"


class JobKind(StrEnum):
    """분석 잡의 실행 방식."""

    FULL = "FULL"
    PARTIAL = "PARTIAL"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)


class JobStep(StrEnum):
    """프론트 로딩 오버레이 단계와 1:1. 한국어 문구는 프론트가 매핑한다."""

    # 분석 잡 5단계
    GATE = "GATE"
    MARKET = "MARKET"
    SHIPPING = "SHIPPING"
    MARGIN = "MARGIN"
    REPORT = "REPORT"
    # 상세페이지 잡 3단계
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    LOCALIZE = "LOCALIZE"
    # 이미지 잡
    GENERATE = "GENERATE"


class NodeName(StrEnum):
    """analysis_graph 노드 9개. 요구사항 ID 와 1:1 (docs/traceability.md 참조)."""

    PRODUCT_UNDERSTANDING = "PRODUCT_UNDERSTANDING"  # R-001-02
    CUSTOMS_GATE = "CUSTOMS_GATE"  # R-004-03/04
    MARKET_RESEARCH = "MARKET_RESEARCH"  # R-001-03
    MARKET_EVALUATE = "MARKET_EVALUATE"  # R-001-05/06
    MARKET_INSIGHT = "MARKET_INSIGHT"  # R-001-07/08
    LOGISTICS_ESTIMATE = "LOGISTICS_ESTIMATE"  # R-004-01/02
    MARGIN = "MARGIN"  # R-002-03~05/08/09/10
    RISK_CHECKLIST = "RISK_CHECKLIST"  # R-004-05~08
    REPORT_COMPOSE = "REPORT_COMPOSE"  # R-000-04


#: 노드가 끝나면 잡 step 이 무엇으로 보이는가. 프론트 오버레이 진행에 쓰인다.
NODE_STEP: dict[NodeName, JobStep] = {
    NodeName.PRODUCT_UNDERSTANDING: JobStep.GATE,
    NodeName.CUSTOMS_GATE: JobStep.GATE,
    NodeName.MARKET_RESEARCH: JobStep.MARKET,
    NodeName.MARKET_EVALUATE: JobStep.MARKET,
    NodeName.MARKET_INSIGHT: JobStep.MARKET,
    NodeName.LOGISTICS_ESTIMATE: JobStep.SHIPPING,
    NodeName.MARGIN: JobStep.MARGIN,
    NodeName.RISK_CHECKLIST: JobStep.MARGIN,
    NodeName.REPORT_COMPOSE: JobStep.REPORT,
}

#: 국가 파이프라인 실행 순서. 진행률(index / len) 계산에 쓴다.
COUNTRY_NODE_ORDER: tuple[NodeName, ...] = (
    NodeName.PRODUCT_UNDERSTANDING,
    NodeName.CUSTOMS_GATE,
    NodeName.MARKET_RESEARCH,
    NodeName.MARKET_EVALUATE,
    NodeName.MARKET_INSIGHT,
    NodeName.LOGISTICS_ESTIMATE,
    NodeName.MARGIN,
    NodeName.RISK_CHECKLIST,
)


class NodeStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class CountryStatus(StrEnum):
    RUNNING = "RUNNING"
    DONE = "DONE"
    #: 통관 PROHIBITED. 프론트 국가 목록에서 제외하되 사유는 저장한다.
    FILTERED_OUT = "FILTERED_OUT"
    #: 근거 부족·품질 미달. 결과는 주되 라벨을 붙인다.
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


class CustomsLevel(StrEnum):
    ALLOWED = "ALLOWED"
    RESTRICTED = "RESTRICTED"
    PROHIBITED = "PROHIBITED"
    #: 근거 문서가 없을 때. 판매 가능으로 추정하지 않는다.
    UNKNOWN = "UNKNOWN"


class AxisGrade(StrEnum):
    """4축 지표 등급. 프론트 '높음/보통/낮음'."""

    HIGH = "HIGH"
    MID = "MID"
    LOW = "LOW"


class EntryGrade(StrEnum):
    """진입점수 3단계 해석 라벨. 가짜 정밀도를 배제하려고 점수와 함께 준다."""

    FIT = "FIT"  # >= 70
    NORMAL = "NORMAL"  # >= 40
    CAUTION = "CAUTION"


class FitGrade(StrEnum):
    """프론트 국가 카드 뱃지. '매우 적합/일부 적합/보통/유의'."""

    VERY_FIT = "VERY_FIT"
    PARTIAL_FIT = "PARTIAL_FIT"
    NORMAL = "NORMAL"
    CAUTION = "CAUTION"


class Positioning(StrEnum):
    ENTRY = "ENTRY"
    PREMIUM = "PREMIUM"
    FANDOM = "FANDOM"
    GIFT = "GIFT"


class ShippingMethod(StrEnum):
    DIRECT = "DIRECT"
    SLS = "SLS"


class PriceTier(StrEnum):
    LOW = "LOW"
    MID = "MID"
    HIGH = "HIGH"


class MarginVerdict(StrEnum):
    GOOD = "GOOD"
    RISK = "RISK"
    NON_VIABLE = "NON_VIABLE"


class RiskDifficulty(StrEnum):
    LOW = "LOW"
    MID = "MID"
    HIGH = "HIGH"


class ContentStatus(StrEnum):
    DONE = "DONE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


class ImageTarget(StrEnum):
    PRODUCT = "PRODUCT"
    DETAIL = "DETAIL"


class ImageMode(StrEnum):
    BASIC = "BASIC"
    MODEL = "MODEL"


class CopilotPage(StrEnum):
    """AI 패널이 열린 화면. 어떤 컨텍스트를 붙일지 결정한다."""

    TOTAL_REPORT = "TOTAL_REPORT"
    COUNTRY_REPORT = "COUNTRY_REPORT"
    SALES_INFO = "SALES_INFO"
    DETAIL_PAGE = "DETAIL_PAGE"
    SALES_OPS = "SALES_OPS"


class CopilotIntent(StrEnum):
    QUERY = "QUERY"
    COMMAND = "COMMAND"
    CLARIFY = "CLARIFY"


class CopilotAction(StrEnum):
    """보고서에 영향을 주는 명령 3종. 그 외 요청은 답변만 한다."""

    ADD_COUNTRY = "ADD_COUNTRY"
    REANALYZE = "REANALYZE"
    REGENERATE_DETAIL = "REGENERATE_DETAIL"


#: MVP 대상 국가. 프론트 트리·카드·랭킹이 3개국 전제로 짜여 있다.
SUPPORTED_COUNTRIES: tuple[str, ...] = ("VN", "SG", "TH")

COUNTRY_NAMES: dict[str, str] = {"VN": "베트남", "SG": "싱가포르", "TH": "태국"}
COUNTRY_CURRENCY: dict[str, str] = {"VN": "VND", "SG": "SGD", "TH": "THB"}
COUNTRY_LOCALE: dict[str, str] = {"VN": "vi", "SG": "en", "TH": "th"}
