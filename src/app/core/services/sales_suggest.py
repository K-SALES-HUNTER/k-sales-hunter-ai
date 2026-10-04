"""판매 정보 추천 — 카테고리·속성·옵션 (요구사항 R-003-12/13, 화면 SEL-01-01).

AI 가 먼저 채우고 사람이 확정한다 (HITL). 확정값이 상세페이지와 업로드에 그대로 쓰인다.

Shopee 제약
    옵션은 최대 2단, 조합은 최대 50개. 초과하면 등록이 안 되므로 코드가 막는다.
    카테고리는 최종 하위(leaf) 를 골라야 하고 국가마다 id 가 다르다.

흐름
    1. data/shopee_categories/{cc}.json 에서 키워드 매칭으로 후보 5개를 추린다 (코드)
    2. gpt-4o-mini 가 후보 중 1개를 고르고 속성 값·옵션을 채운다
    3. 결과를 다시 검증한다. 후보 밖 id, 스키마에 없는 속성 key, 50개 초과 조합은 코드가 고친다

후보를 좁혀야 환각이 줄고 싸다. LLM 이 실패하거나 빈 값을 내도 화면은 뜬다
(1순위 후보 + 빈 속성 + 옵션 힌트 이름). 셀러가 직접 채우면 된다.

담당: 강근우 (콘텐츠 아키텍트 R-003-12/13)
"""

from __future__ import annotations

import json

from app.contracts.v1 import (
    CategoryAttr,
    OptionSpec,
    SalesSuggestRequest,
    SalesSuggestResponse,
)
from app.core.agents import prompts
from app.core.agents.schemas import OptionDraft, SalesSuggestionDraft
from app.core.catalog import shopee_categories
from app.core.catalog.shopee_categories import Catalog, Category
from app.errors import ServiceError
from app.infra.llm import Model, complete_json
from app.observability.logging import get_logger

log = get_logger(mod="sales_suggest")

#: Shopee 제약. 검증은 Spring 과 여기 양쪽에서 한다.
MAX_OPTION_LEVELS = 2
MAX_COMBINATIONS = 50
#: 한 단의 옵션값 수. 화면에서 다루기 좋은 범위로 자른다.
MAX_OPTION_VALUES = 20
#: 제조국 기본값. 한국 셀러의 역직구 상품이다.
DEFAULT_ORIGIN = "대한민국"
DEFAULT_STOCK_HINT = "옵션 조합당 10~20개로 시작해 첫 2주 판매량을 보고 늘리세요."


async def suggest(request: SalesSuggestRequest) -> SalesSuggestResponse:
    catalog = shopee_categories.load(request.country)
    product = request.product

    fixed = catalog.get(request.category_id)
    pool = (
        [fixed]
        if fixed
        else shopee_categories.candidates(
            catalog,
            app_category=product.category,
            texts=[
                product.name,
                product.description,
                product.selling_point,
                *request.keywords,
            ],
        )
    )

    draft = await _ask_llm(request, catalog, pool)
    return _finalize(catalog, pool, draft)


async def _ask_llm(
    request: SalesSuggestRequest, catalog: Catalog, pool: list[Category]
) -> SalesSuggestionDraft | None:
    """LLM 실패는 추천 실패일 뿐이다. 화면은 빈 값으로라도 떠야 하므로 삼킨다."""
    product = request.product
    payload = {
        "product": {
            "name": product.name,
            "category": product.category,
            "description": product.description,
            "sellingPoints": product.selling_point,
            "mainTarget": product.main_target,
        },
        "keywords": request.keywords,
        "candidates": [
            {
                "id": category.id,
                "path": category.label,
                "attributes": [
                    {"key": ref.key, "label": catalog.attr_label(ref.key), "required": ref.required}
                    for ref in category.attributes
                ],
                "optionHints": [
                    {"name": hint.name, "label": hint.label} for hint in category.option_hints
                ],
            }
            for category in pool
        ],
    }

    prompt = prompts.load("sales_suggest")
    try:
        return await complete_json(
            schema=SalesSuggestionDraft,
            system=prompt.body,
            user=json.dumps(payload, ensure_ascii=False, indent=2),
            model=Model.LIGHT,
            prompt_version=prompt.version,
            node="SALES_SUGGEST",
        )
    except ServiceError as exc:
        log.warning("판매 정보 추천 LLM 실패, 빈 값으로 응답", code=exc.code.value)
        return None


def _finalize(
    catalog: Catalog, pool: list[Category], draft: SalesSuggestionDraft | None
) -> SalesSuggestResponse:
    """LLM 출력을 그대로 믿지 않는다. 카테고리·속성·옵션을 카탈로그 기준으로 다시 맞춘다."""
    by_id = {category.id: category for category in pool}
    category = by_id.get(draft.category_id) if draft else None
    if category is None:
        if draft and draft.category_id:
            log.warning("후보 밖 카테고리를 골랐다, 1순위로 교체", picked=draft.category_id)
            #: 다른 카테고리 기준으로 채운 속성·옵션이라 버린다
            draft = None
        category = pool[0]

    values = {item.key: item.value.strip() for item in (draft.attributes if draft else [])}
    attrs = [
        CategoryAttr(
            key=attr.key,
            label=attr.label,
            required=attr.required,
            value=values.get(attr.key) or (DEFAULT_ORIGIN if attr.key == "origin" else ""),
        )
        for attr in catalog.attribute_schema(category)
    ]

    option1 = _option(draft.option1 if draft else None, category, level=0)
    option2 = _option(draft.option2 if draft else None, category, level=1)
    if option1 is None and option2 is not None:
        #: 2단만 있으면 1단으로 올린다
        option1, option2 = option2, None
    option1, option2 = limit_combinations(option1, option2)

    ordered = [category] + [item for item in pool if item.id != category.id]
    return SalesSuggestResponse(
        category_id=category.id,
        category_label=category.label,
        category_label_local=category.label_local,
        category_options=[{"value": item.id, "label": item.label} for item in ordered],
        category_attrs=attrs,
        option1=option1,
        option2=option2,
        stock_hint=(draft.stock_hint.strip() if draft and draft.stock_hint else "")
        or DEFAULT_STOCK_HINT,
        catalog_version=catalog.version,
    )


def _option(draft: OptionDraft | None, category: Category, *, level: int) -> OptionSpec | None:
    """옵션 이름은 카테고리 힌트에 맞추고, 값은 공백·중복을 걷어낸다.

    LLM 이 옵션을 안 냈으면 힌트 이름만 채운 빈 옵션을 준다 (1단만).
    셀러가 값만 넣으면 되도록 하기 위해서다.
    """
    hints = {hint.name: hint for hint in category.option_hints}

    if draft is None or not draft.name.strip():
        if level == 0 and category.option_hints:
            hint = category.option_hints[0]
            return OptionSpec(name=hint.name, label=hint.label, values=[])
        return None

    name = draft.name.strip()
    hint = hints.get(name)
    label = hint.label if hint else (draft.label.strip() or name)

    seen: set[str] = set()
    values = []
    for raw in draft.values:
        value = raw.strip()
        if value and value not in seen:
            seen.add(value)
            values.append(value)
    return OptionSpec(name=name, label=label, values=values[:MAX_OPTION_VALUES])


def limit_combinations(
    option1: OptionSpec | None, option2: OptionSpec | None
) -> tuple[OptionSpec | None, OptionSpec | None]:
    """조합 수가 50 을 넘으면 값이 많은 쪽부터 뒤에서 하나씩 덜어낸다."""
    if option1 is None or option2 is None:
        return option1, option2

    first, second = list(option1.values), list(option2.values)
    while len(first) * max(len(second), 1) > MAX_COMBINATIONS:
        if len(first) >= len(second):
            first.pop()
        else:
            second.pop()
    return (
        option1.model_copy(update={"values": first}),
        option2.model_copy(update={"values": second}),
    )


def validate_options(option1: OptionSpec | None, option2: OptionSpec | None) -> list[str]:
    """판매 정보 저장 전 검증. 문제가 없으면 빈 목록.

    Spring 의 PUT sales-info 도 같은 규칙으로 막는다.
    """
    problems = []
    if option2 is not None and option1 is None:
        problems.append("2단 옵션은 1단 옵션이 있어야 합니다")
    count1 = len(option1.values) if option1 else 0
    count2 = len(option2.values) if option2 else 0
    if option1 is not None and count1 == 0:
        problems.append("1단 옵션값을 하나 이상 입력하세요")
    if count1 * max(count2, 1) > MAX_COMBINATIONS:
        problems.append(f"옵션 조합은 최대 {MAX_COMBINATIONS}개입니다 (현재 {count1 * count2}개)")
    return problems
