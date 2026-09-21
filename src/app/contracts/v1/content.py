"""상세페이지 생성 잡 계약 (R-003).

프론트 PdpContent 와 같은 구조로 준다. 단 price·shipping·options·stockNote 는
확정된 판매정보에서 나오는 값이라 Spring/dev_bff 가 채운다. AI 는 글을 만든다.
"""

from __future__ import annotations

from pydantic import Field

from app.contracts.v1.analysis import MarketProfile, ProductSnapshot
from app.contracts.v1.base import SCHEMA_VERSION, CamelModel
from app.contracts.v1.enums import ContentStatus, ShippingMethod


class SalesInfoSnapshot(CamelModel):
    """판매 정보 입력 화면에서 사용자가 확정한 값."""

    category_id: str = ""
    category_label: str = ""
    attributes: dict = Field(default_factory=dict)
    option1: dict | None = None
    option2: dict | None = None
    final_price_krw: int = 0
    final_price_local: float = 0.0
    currency: str = ""
    shipping_method: ShippingMethod | None = None
    stock_total: int = 0


class AnalysisDigest(CamelModel):
    """국가별 분석 결과 중 콘텐츠 생성에 필요한 부분만. 읽기 전용으로 상속받는다."""

    positioning: str = ""
    positioning_label: str = ""
    keywords: list[str] = Field(default_factory=list)
    usps: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)


class ContentCommand(CamelModel):
    schema_version: str = SCHEMA_VERSION
    job_id: str
    trace_id: str = ""
    country: str
    locale: str = "vi"
    product: ProductSnapshot
    sales_info: SalesInfoSnapshot
    analysis: AnalysisDigest = Field(default_factory=AnalysisDigest)
    market_profile: MarketProfile | None = None
    #: 코파일럿 수정 요청 시 지적 사항
    revision_instruction: str | None = None


class PdpDraft(CamelModel):
    """AI 가 만드는 부분. 프론트 PdpContent 의 부분집합."""

    name: str
    usps: list[str] = Field(default_factory=list)
    #: 소개·특징·혜택·구매유도 4단락을 합친 본문
    description: str = ""
    #: 상품 사양 표. [["브랜드", "Kora"], ...]
    specs: list[list[str]] = Field(default_factory=list)
    breadcrumb: list[str] = Field(default_factory=list)


class QualityIssue(CamelModel):
    kind: str  # BANNED_WORD | TRADEMARK | EXAGGERATION | MISSING_SECTION
    detail: str = ""
    #: 금지어·상표권은 사람 승인 전 통과 불가 (하드 컷)
    hard_block: bool = False


class ContentResult(CamelModel):
    schema_version: str = SCHEMA_VERSION
    job_id: str
    status: ContentStatus = ContentStatus.DONE
    #: 검수용 한국어본
    ko: PdpDraft | None = None
    #: 업로드용 현지어본. ko 와 같은 구조.
    local: PdpDraft | None = None
    locale: str = "vi"
    quality_score: int = 0
    quality_issues: list[QualityIssue] = Field(default_factory=list)
    regeneration_count: int = 0
