"""상세페이지 생성 (R-003-06/11).

FakeLLM 은 tests/fixtures/llm/PdpCopyKo.json · PdpCopyLocal.json (시연 상품) 을 돌려준다.
재생성 루프는 complete_json 을 바꿔 끼워 확인한다.
"""

from __future__ import annotations

import pytest

from app.contracts.v1 import (
    ContentCommand,
    ContentStatus,
    ProductSnapshot,
    SalesInfoSnapshot,
    ShippingMethod,
)
from app.core.agents.schemas import PdpCopyKo, PdpCopyLocal, SpecRow
from app.core.content import culture, quality
from app.core.graph import content
from app.core.graph.content import run_content
from app.core.services import content_edit
from app.infra.llm import fake_instance


@pytest.fixture
def command() -> ContentCommand:
    return ContentCommand(
        job_id="c_1_VN_1",
        country="VN",
        locale="vi",
        product=ProductSnapshot(
            product_id=1,
            name="말랑 프렌즈 캐릭터 인형",
            category="캐릭터·굿즈",
            supply_cost_krw=11500,
            weight_g=250,
        ),
        sales_info=SalesInfoSnapshot(
            category_id="toys-plush",
            category_label="완구·취미 › 인형·플러시 › 캐릭터 인형",
            attributes={
                "brand": "말랑 프렌즈 (Mallang Friends)",
                "character": "모카 · 코코 · 포미 · 베리",
                "material": "폴리에스터 100% 극세사",
                "size": "20cm / 30cm",
                "origin": "대한민국",
                "age": "만 14세 이상 소장용",
            },
            option1={
                "name": "색상",
                "values": ["모카 (블루)", "코코 (블랙)", "포미 (화이트)", "베리 (퍼플)"],
            },
            option2={"name": "사이즈", "values": ["20cm", "30cm"]},
            final_price_krw=28900,
            shipping_method=ShippingMethod.SLS,
            stock_total=156,
        ),
    )


# ── 전 구간 ─────────────────────────────────────────────────────────────


async def test_한국어본과_현지어본을_같은_구조로_만든다(command: ContentCommand):
    result = await run_content(command)

    assert result.status is ContentStatus.DONE
    assert result.quality_score >= quality.PASS_SCORE
    assert result.regeneration_count == 0
    assert result.ko and result.local

    assert result.ko.breadcrumb == ["홈", "완구·취미", "인형·플러시", "캐릭터 인형"]
    assert result.local.breadcrumb[0] == "Trang chủ"
    assert len(result.ko.usps) == len(result.local.usps) == 4
    assert result.ko.description.count("\n\n") == 3
    assert len(result.ko.specs) == len(result.local.specs)
    assert result.local.options[0]["values"][3] == "Berry (Tím)"


async def test_사양_표_기본_행은_판매정보에서_코드가_만든다(command: ContentCommand):
    result = await run_content(command)
    assert result.ko
    specs = dict((row[0], row[1]) for row in result.ko.specs)
    assert specs["카테고리"] == "완구·취미 › 인형·플러시 › 캐릭터 인형"
    assert specs["브랜드"] == "말랑 프렌즈 (Mallang Friends)"
    assert specs["재고"] == "156개"
    #: LLM 이 덧붙인 행
    assert specs["세탁 방법"] == "30°C 이하 손세탁"


# ── 재생성 루프 ─────────────────────────────────────────────────────────


def _copy(name: str, intro: str) -> PdpCopyKo:
    return PdpCopyKo(
        name=name,
        usps=["정품 라이선스", "극세사 원단", "4종 택1", "한국 직배송"],
        intro=intro,
        features="폴리에스터 원단입니다.",
        benefits="선물로 좋습니다.",
        call_to_action="옵션을 골라 주세요.",
        extra_specs=[SpecRow(label="구성", value="선물 상자")],
    )


def _fake_llm(drafts: list[PdpCopyKo], calls: list[dict]):  # noqa: ANN202
    async def fake(**kwargs):  # noqa: ANN003, ANN202
        calls.append(kwargs)
        if kwargs["schema"] is PdpCopyKo:
            return drafts[
                min(len([c for c in calls if c["schema"] is PdpCopyKo]) - 1, len(drafts) - 1)
            ]
        return fake_instance(PdpCopyLocal)

    return fake


async def test_하드컷이면_지적사항을_넣어_다시_쓴다(command, monkeypatch):  # noqa: ANN001
    calls: list[dict] = []
    bad = _copy("말랑 인형", "아토피 개선에 좋은 인형입니다.")
    good = _copy("말랑 프렌즈 인형", "한국 정품 캐릭터 인형입니다.")
    monkeypatch.setattr(content, "complete_json", _fake_llm([bad, good], calls))

    result = await run_content(command)

    assert result.regeneration_count == 1
    assert result.status is ContentStatus.DONE
    second_draft = [c for c in calls if c["schema"] is PdpCopyKo][1]
    assert "아토피 개선" in second_draft["user"]


async def test_2회_재생성해도_미달이면_검수필요로_결과를_준다(command, monkeypatch):  # noqa: ANN001
    calls: list[dict] = []
    bad = _copy("샤넬 스타일 인형", "부드러운 인형입니다.")
    monkeypatch.setattr(content, "complete_json", _fake_llm([bad], calls))

    result = await run_content(command)

    assert result.regeneration_count == content.MAX_REGENERATION
    assert result.status is ContentStatus.NEEDS_REVIEW
    assert any(
        issue.kind == culture.TRADEMARK and issue.hard_block for issue in result.quality_issues
    )
    #: 미달이어도 현지어본까지 준다. 셀러가 편집 화면에서 고친다.
    assert result.local is not None
    assert len([c for c in calls if c["schema"] is PdpCopyKo]) == 3


# ── 품질 검수 · 문화 필터 ───────────────────────────────────────────────


def _valid_copy(**override) -> dict:  # noqa: ANN003
    copy = {
        "name": "말랑 프렌즈 캐릭터 인형",
        "usps": ["a", "b", "c", "d"],
        "sections": ["소개", "특징", "혜택", "구매"],
        "specs": [["k", "v"]] * 5,
    }
    copy.update(override)
    return copy


def test_문제없는_초안은_만점이다():
    report = quality.evaluate(_valid_copy(), culture.load("VN"))
    assert report.score == 100 and report.passed


def test_과장_표현은_감점만_한다():
    report = quality.evaluate(_valid_copy(name="역대급 세계 최초 인형"), culture.load("VN"))
    assert report.score == 100 - 2 * quality.PENALTY[culture.EXAGGERATION]
    assert not report.hard_blocked


def test_누락_섹션을_감점한다():
    report = quality.evaluate(
        _valid_copy(usps=["a"], sections=["소개", ""], specs=[]), culture.load("VN")
    )
    assert report.score == 100 - 15 - 15 - 10
    assert not report.passed


def test_검색_키워드가_없으면_감점한다():
    report = quality.evaluate(_valid_copy(), culture.load("VN"), keywords=["gấu bông"])
    assert report.score == 100 - quality.PENALTY[quality.SEO_KEYWORD]


def test_국가별_금기는_그_나라에서만_걸린다():
    copy = _valid_copy(sections=["불상 모양 장식", "특징", "혜택", "구매"])
    assert quality.evaluate(copy, culture.load("TH")).hard_blocked
    assert not quality.evaluate(copy, culture.load("VN")).hard_blocked


def test_치환_가능한_과장만_바꾸고_하드컷은_남긴다():
    rules = culture.load("VN")
    assert culture.sanitize(rules, "최고의 선물") == "만족스러운 선물"
    assert culture.sanitize(rules, "기적의 인형") == "인형"
    assert culture.sanitize(rules, "치료 효과") == "치료 효과"


def test_영문은_단어_경계로만_찾는다():
    rules = culture.load("SG")
    assert not culture.find(rules, {"x": "secure packaging"})
    assert culture.find(rules, {"x": "It can cure acne"})


async def test_셀러_수정본을_현지어로_다시_옮긴다():
    result = await content_edit.retranslate(
        country="VN", locale="vi", name="말랑 인형", description="부드러운 인형"
    )
    assert result.name.startswith("Gấu Bông")
