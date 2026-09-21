"""PRODUCT_UNDERSTANDING — 상품 이해 (요구사항 R-001-02).

이미지와 설명에서 시각 특징·핵심 키워드·K-트렌드 카테고리를 뽑는다.

구현 메모
    gpt-4o vision, 이미지는 최대 4장 1024px 로 리사이즈해 보낸다.
    이미지를 못 받으면 텍스트만으로 진행하고 image_used=False 를 남긴다 (UC-01 A2).
    상품 등록 화면의 'AI 자동 채우기'(core/services/product_fill.py)와 프롬프트를 공유한다.

담당: 차은호   상태: stub
"""

from __future__ import annotations

from app.contracts.v1 import NodeName
from app.core.graph.runtime import node
from app.core.graph.state import CountryState


@node(NodeName.PRODUCT_UNDERSTANDING)
async def run(state: CountryState) -> dict:
    product = state.get("product") or {}

    # TODO(차은호): gpt-4o vision 호출로 교체. 아래는 임시값.
    return {
        "product_features": {
            "colors": [],
            "materials": [],
            "shape": "",
            "style": "",
            "keywords": [product.get("category", "")],
            "k_trend_category": product.get("category", ""),
            "usps": [
                line.strip() for line in product.get("selling_point", "").split("·") if line.strip()
            ],
            "image_used": False,
            "confidence": 0.0,
        }
    }
