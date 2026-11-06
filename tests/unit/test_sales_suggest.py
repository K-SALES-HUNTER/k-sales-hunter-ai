"""판매 정보 추천 (R-003-12/13).

FakeLLM 은 tests/fixtures/llm/SalesSuggestionDraft.json (시연 상품 말랑 프렌즈) 을 돌려준다.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.contracts.v1 import (
    SUPPORTED_COUNTRIES,
    OptionSpec,
    ProductSnapshot,
    SalesSuggestRequest,
)
from app.core.catalog import shopee_categories
from app.core.services import sales_suggest
from app.core.services.product_fill import CATEGORIES


@pytest.fixture
def plush() -> ProductSnapshot:
    """시연 상품. 등록 화면에서 상품명·원가·무게만 입력한다."""
    return ProductSnapshot(
        product_id=1,
        name="말랑 프렌즈 캐릭터 인형",
        category="캐릭터·굿즈",
        supply_cost_krw=11500,
        weight_g=250,
    )


# ── 카탈로그 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("country", SUPPORTED_COUNTRIES)
def test_3개국_카탈로그가_같은_id_를_쓴다(country: str):
    catalog = shopee_categories.load(country)
    vn = shopee_categories.load("VN")
    assert catalog.country == country
    assert set(catalog.categories) == set(vn.categories)


@pytest.mark.parametrize("country", SUPPORTED_COUNTRIES)
def test_모든_속성_key_에_라벨이_있다(country: str):
    catalog = shopee_categories.load(country)
    for category in catalog.categories.values():
        assert category.path and category.path_local
        assert category.option_hints
        for ref in category.attributes:
            assert ref.key in catalog.attribute_defs, f"{category.id}.{ref.key}"


def test_상품등록_대분류_11종이_모두_카테고리로_이어진다():
    catalog = shopee_categories.load("VN")
    covered = {app for item in catalog.categories.values() for app in item.app_categories}
    assert set(CATEGORIES) <= covered


def test_프론트_목과_같은_경로_라벨을_만든다():
    category = shopee_categories.load("VN").get("toys-plush")
    assert category is not None
    assert category.label == "완구·취미 › 인형·플러시 › 캐릭터 인형"


def test_키워드로_후보를_추린다():
    catalog = shopee_categories.load("VN")
    picked = shopee_categories.candidates(
        catalog, app_category="뷰티", texts=["제주 화산송이 클렌저 150ml"]
    )
    assert picked[0].id == "beauty-cleanser"
    assert len(picked) <= 5


def test_아무것도_안_맞으면_기타로_떨어진다():
    catalog = shopee_categories.load("VN")
    picked = shopee_categories.candidates(catalog, app_category="", texts=["zzzz"])
    assert [item.id for item in picked] == [shopee_categories.FALLBACK_ID]


# ── 추천 ────────────────────────────────────────────────────────────────


async def test_시연_상품은_캐릭터_인형으로_채운다(plush: ProductSnapshot):
    result = await sales_suggest.suggest(SalesSuggestRequest(country="VN", product=plush))

    assert result.category_id == "toys-plush"
    assert result.category_options[0]["value"] == "toys-plush"
    assert result.category_label_local.startswith("Đồ Chơi")
    attrs = {attr.key: attr for attr in result.category_attrs}
    assert list(attrs) == ["brand", "character", "material", "size", "origin", "age"]
    assert attrs["brand"].required and attrs["brand"].label == "브랜드"
    assert result.option1 is not None and result.option1.label == "제공 색상"
    assert len(result.option1.values) == 4
    assert result.option2 is not None and result.option2.values == ["20cm", "30cm"]


async def test_후보_밖_카테고리를_고르면_1순위로_바꾸고_값을_버린다(product: ProductSnapshot):
    """FakeLLM 은 클렌저에도 인형 카테고리를 고른다. 코드가 막아야 한다."""
    result = await sales_suggest.suggest(SalesSuggestRequest(country="VN", product=product))

    assert result.category_id == "beauty-cleanser"
    attrs = {attr.key: attr.value for attr in result.category_attrs}
    assert attrs["brand"] == ""
    assert attrs["origin"] == sales_suggest.DEFAULT_ORIGIN
    #: 옵션값은 비우고 이름만 카테고리 힌트로 준다
    assert result.option1 is not None and result.option1.values == []
    assert result.option2 is None


async def test_고른_카테고리가_있으면_그_안에서만_채운다(plush: ProductSnapshot):
    result = await sales_suggest.suggest(
        SalesSuggestRequest(country="TH", product=plush, category_id="toys-keyring")
    )
    assert result.category_id == "toys-keyring"
    assert [item["value"] for item in result.category_options] == ["toys-keyring"]


def test_옵션_조합은_50개를_넘지_않는다():
    first = OptionSpec(name="색상", values=[f"c{i}" for i in range(12)])
    second = OptionSpec(name="사이즈", values=[f"s{i}" for i in range(8)])
    limited1, limited2 = sales_suggest.limit_combinations(first, second)
    assert limited1 and limited2
    assert len(limited1.values) * len(limited2.values) <= sales_suggest.MAX_COMBINATIONS


def test_저장_전_옵션_검증():
    ok = OptionSpec(name="색상", values=["a", "b"])
    assert sales_suggest.validate_options(ok, None) == []
    assert sales_suggest.validate_options(None, ok)
    assert sales_suggest.validate_options(OptionSpec(name="색상", values=[]), None)
    many = OptionSpec(name="x", values=[str(i) for i in range(11)])
    assert sales_suggest.validate_options(many, OptionSpec(name="y", values=list("abcde")))


# ── dev_bff 라우트 ──────────────────────────────────────────────────────


@pytest.fixture
def client() -> TestClient:
    from app.entrypoints import dev_bff

    app = FastAPI()
    app.include_router(dev_bff.router)
    dev_bff._products[99] = {"id": 99, "name": "테스트"}
    return TestClient(app)


def test_카테고리_목록과_속성을_준다(client: TestClient):
    options = client.get("/api/v1/shopee/categories", params={"country": "SG"}).json()
    assert {"value", "label", "labelLocal"} <= set(options[0])

    attrs = client.get(
        "/api/v1/shopee/categories/toys-plush/attributes", params={"country": "VN"}
    ).json()
    assert attrs[0] == {"key": "brand", "label": "브랜드", "value": "", "required": True}


def test_조합_초과_판매정보는_저장하지_않는다(client: TestClient):
    body = {
        "category": "toys-plush",
        "option1": {"name": "색상", "values": [str(i) for i in range(11)]},
        "option2": {"name": "사이즈", "values": list("abcde")},
    }
    response = client.put("/api/v1/products/99/countries/VN/sales-info", json=body)
    assert response.status_code == 422


def test_판매정보를_저장하면_단계가_바뀐다(client: TestClient):
    from app.entrypoints import dev_bff

    body = {
        "category": "toys-plush",
        "finalPrice": 28900,
        "option1": {"name": "색상", "values": ["모카 (블루)"]},
        "stock": [{"option1": "모카 (블루)", "qty": 42}],
    }
    response = client.put("/api/v1/products/99/countries/vn/sales-info", json=body)
    assert response.status_code == 200
    assert (99, "VN") in dev_bff._sales_infos
