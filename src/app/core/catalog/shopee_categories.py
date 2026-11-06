"""Shopee 카테고리 트리 조회 (R-003-12, 화면 SEL-01-01).

data/shopee_categories/{VN,SG,TH}.json 을 읽는다. Shopee Open API 연동은 과업 범위 밖이라
셀러센터 카테고리 트리를 수동으로 정리한 정적 스냅샷을 쓴다.

파일 형식
    {
      "country": "VN", "locale": "vi", "version": "vn-shopee-categories-2026.10-snapshot",
      "homeLabel": "Trang chủ",
      "attributeDefs": { "brand": {"label": "브랜드", "labelLocal": "Thương hiệu"}, ... },
      "categories": [
        { "id": "toys-plush", "shopeeId": null,
          "path": ["완구·취미", "인형·플러시", "캐릭터 인형"],
          "pathLocal": ["Đồ Chơi & Sở Thích", "Thú Nhồi Bông", "Gấu Bông Nhân Vật"],
          "appCategories": ["캐릭터·굿즈"],          # 상품 등록 드롭다운 11종과의 대응
          "keywords": ["인형", "plush"],              # 후보 추리기용
          "attributes": [{"key": "brand", "required": true}, ...],
          "optionHints": [{"name": "색상", "label": "제공 색상"}, ...] }
      ]
    }

id 는 국가 공통 slug 다. 실제 Shopee category_id 는 국가마다 달라 shopeeId 에 따로 둔다
(셀러센터에서 확인 전까지 null). 판매 정보 저장·상세페이지는 id 로만 참조한다.

Spring 의 GET /shopee/categories 도 이 파일을 그대로 읽으면 된다 (권수현).

[철칙] LLM 을 import 하지 않는다. 후보를 추리는 것까지는 코드가 한다.

담당: 강근우 (콘텐츠 아키텍트 R-003-12/13)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache

from app.config import DATA_DIR
from app.contracts.v1 import CategoryAttr

#: 경로 표시 구분자. 프론트 목과 같은 문자.
PATH_SEPARATOR = " › "
#: 키워드 매칭에 실패했을 때 고르는 카테고리
FALLBACK_ID = "other-general"


@dataclass(frozen=True)
class AttrRef:
    key: str
    required: bool


@dataclass(frozen=True)
class OptionHint:
    name: str
    label: str


@dataclass(frozen=True)
class Category:
    id: str
    shopee_id: str | None
    path: tuple[str, ...]
    path_local: tuple[str, ...]
    app_categories: tuple[str, ...]
    keywords: tuple[str, ...]
    attributes: tuple[AttrRef, ...]
    option_hints: tuple[OptionHint, ...]

    @property
    def label(self) -> str:
        return PATH_SEPARATOR.join(self.path)

    @property
    def label_local(self) -> str:
        return PATH_SEPARATOR.join(self.path_local)


@dataclass(frozen=True)
class Catalog:
    country: str
    locale: str
    version: str
    home_label: str
    attribute_defs: dict[str, dict[str, str]]
    categories: dict[str, Category] = field(default_factory=dict)

    def get(self, category_id: str | None) -> Category | None:
        return self.categories.get(category_id or "")

    def attr_label(self, key: str, *, local: bool = False) -> str:
        spec = self.attribute_defs.get(key, {})
        return spec.get("labelLocal" if local else "label", key)

    def attribute_schema(self, category: Category) -> list[CategoryAttr]:
        """값이 빈 속성 목록. 프론트 categoryAttrs 와 같은 모양."""
        return [
            CategoryAttr(key=ref.key, label=self.attr_label(ref.key), required=ref.required)
            for ref in category.attributes
        ]


def _parse(raw: dict) -> Catalog:
    categories = {}
    for item in raw.get("categories", []):
        category = Category(
            id=item["id"],
            shopee_id=item.get("shopeeId"),
            path=tuple(item.get("path", [])),
            path_local=tuple(item.get("pathLocal", [])),
            app_categories=tuple(item.get("appCategories", [])),
            keywords=tuple(word.lower() for word in item.get("keywords", [])),
            attributes=tuple(
                AttrRef(key=attr["key"], required=bool(attr.get("required")))
                for attr in item.get("attributes", [])
            ),
            option_hints=tuple(
                OptionHint(name=hint["name"], label=hint.get("label", hint["name"]))
                for hint in item.get("optionHints", [])
            ),
        )
        categories[category.id] = category
    return Catalog(
        country=raw.get("country", ""),
        locale=raw.get("locale", ""),
        version=raw.get("version", "unknown"),
        home_label=raw.get("homeLabel", ""),
        attribute_defs=raw.get("attributeDefs", {}),
        categories=categories,
    )


@lru_cache
def load(country: str) -> Catalog:
    """국가 파일이 없으면 VN 을 쓴다. 판매 정보 화면이 비지 않게 하는 것이 우선이다."""
    path = DATA_DIR / "shopee_categories" / f"{country.upper()}.json"
    if not path.exists():
        path = DATA_DIR / "shopee_categories" / "VN.json"
    return _parse(json.loads(path.read_text(encoding="utf-8")))


def _score(category: Category, app_category: str, text: str) -> int:
    score = 0
    if app_category and app_category in category.app_categories:
        #: 사용자가 고른 대분류가 가장 강한 신호다
        score += 3
    score += sum(2 for word in category.keywords if word and word in text)
    return score


def candidates(
    catalog: Catalog,
    *,
    app_category: str = "",
    texts: list[str] | None = None,
    limit: int = 5,
) -> list[Category]:
    """키워드 매칭으로 후보를 추린다. LLM 은 이 안에서만 고른다.

    후보를 좁히면 환각이 줄고 토큰이 싸다. 점수가 전부 0 이면 기타로 떨어진다.
    """
    text = " ".join(texts or []).lower()
    scored = [
        (_score(category, app_category, text), index, category)
        for index, category in enumerate(catalog.categories.values())
    ]
    scored = [item for item in scored if item[0] > 0]
    #: 점수 내림차순, 같으면 파일 순서
    scored.sort(key=lambda item: (-item[0], item[1]))
    picked = [category for _, _, category in scored[:limit]]

    if not picked:
        fallback = catalog.get(FALLBACK_ID)
        return [fallback] if fallback else list(catalog.categories.values())[:1]
    return picked
