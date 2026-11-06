"""상세페이지 품질 검수 — 0~100점 (R-003-11).

순수 함수다. LLM 을 부르지 않는다. 같은 입력이면 항상 같은 점수가 나와야
"품질 미달 시 최대 2회 재생성" 규칙을 테스트로 고정할 수 있다.

감점표
    BANNED_WORD      -25  하드 컷 (의약품 오인·위조품·국가 금기)
    TRADEMARK        -25  하드 컷 (타사 상표·캐릭터)
    EXAGGERATION      -8  과장·최상급 표현
    MISSING_SECTION  -10~-20  상품명·USP·본문 4단락·사양 표 누락
    SEO_KEYWORD       -5  분석에서 나온 검색 키워드가 하나도 없음

통과 기준: 70점 이상이고 하드 컷이 없을 것.
하드 컷이 있으면 점수와 무관하게 사람 승인 전에는 업로드할 수 없다.

담당: 강근우 (콘텐츠 아키텍트 R-003)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.contracts.v1 import QualityIssue
from app.core.content import culture

PASS_SCORE = 70
#: Shopee 상품명 길이 상한
MAX_NAME_LENGTH = 120
MIN_USPS = 3
MIN_SPECS = 5
#: 소개·특징·혜택·구매유도
DESCRIPTION_SECTIONS = 4
MISSING_SECTION = "MISSING_SECTION"
SEO_KEYWORD = "SEO_KEYWORD"

PENALTY = {
    culture.BANNED: 25,
    culture.TRADEMARK: 25,
    culture.EXAGGERATION: 8,
    SEO_KEYWORD: 5,
}


@dataclass
class QualityReport:
    score: int
    issues: list[QualityIssue] = field(default_factory=list)

    @property
    def hard_blocked(self) -> bool:
        return any(issue.hard_block for issue in self.issues)

    @property
    def passed(self) -> bool:
        return self.score >= PASS_SCORE and not self.hard_blocked

    def instructions(self) -> list[str]:
        """재생성 프롬프트에 넣을 지적 사항."""
        return [issue.detail for issue in self.issues]


def text_fields(copy: dict) -> dict[str, str]:
    """검수 대상 텍스트를 필드 이름과 함께 펼친다."""
    fields = {"name": copy.get("name", "")}
    for index, usp in enumerate(copy.get("usps") or []):
        fields[f"usps[{index}]"] = usp
    for index, section in enumerate(copy.get("sections") or []):
        fields[f"sections[{index}]"] = section
    for index, row in enumerate(copy.get("specs") or []):
        fields[f"specs[{index}]"] = " ".join(str(cell) for cell in row)
    return fields


def evaluate(
    copy: dict,
    rules: culture.CultureRules,
    *,
    keywords: list[str] | None = None,
) -> QualityReport:
    """copy = {name, usps[], sections[4], specs[[k, v]]}"""
    issues: list[QualityIssue] = []
    score = 100

    def add(kind: str, detail: str, penalty: int, *, hard: bool = False) -> None:
        nonlocal score
        score -= penalty
        issues.append(QualityIssue(kind=kind, detail=detail, hard_block=hard))

    name = (copy.get("name") or "").strip()
    usps = [item for item in (copy.get("usps") or []) if item.strip()]
    sections = [item for item in (copy.get("sections") or []) if item.strip()]
    specs = copy.get("specs") or []

    if not name:
        add(MISSING_SECTION, "상품명이 비어 있습니다", 20)
    elif len(name) > MAX_NAME_LENGTH:
        add(MISSING_SECTION, f"상품명이 {MAX_NAME_LENGTH}자를 넘습니다 ({len(name)}자)", 10)
    if len(usps) < MIN_USPS:
        add(MISSING_SECTION, f"핵심 특징(USP)을 {MIN_USPS}개 이상 쓰세요 (현재 {len(usps)}개)", 15)
    if len(sections) < DESCRIPTION_SECTIONS:
        add(
            MISSING_SECTION,
            "상세 설명은 소개·특징·혜택·구매유도 4단락이 모두 있어야 합니다"
            f" (현재 {len(sections)}단락)",
            15,
        )
    if len(specs) < MIN_SPECS:
        add(MISSING_SECTION, f"상품 사양 표가 {MIN_SPECS}행보다 적습니다", 10)

    seen: set[tuple[str, str]] = set()
    for hit in culture.find(rules, text_fields(copy)):
        key = (hit.term.kind, hit.term.term)
        if key in seen:
            continue
        seen.add(key)
        add(
            hit.term.kind,
            f"'{hit.term.term}' 표현을 빼세요 ({hit.term.reason}, 위치: {hit.field})",
            PENALTY[hit.term.kind],
            hard=hit.term.hard_block,
        )

    if keywords:
        body = " ".join([name, *usps, *sections]).lower()
        if not any(word.lower() in body for word in keywords if word):
            add(
                SEO_KEYWORD,
                f"검색 키워드를 상품명이나 본문에 하나 이상 넣으세요: {', '.join(keywords[:5])}",
                PENALTY[SEO_KEYWORD],
            )

    return QualityReport(score=max(score, 0), issues=issues)
