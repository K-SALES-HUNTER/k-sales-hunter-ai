"""LOGISTICS_ESTIMATE — 배송 방식 추천과 배송비 산출 (요구사항 R-004-01/02).

직배송 / Shopee SLS 중 이용 가능한 방식을 고르고 무게 구간으로 요율을 조회한다.
포장 정보가 있으면 그것을 쓰고, 없으면 상품 무게에 포장 가중치를 더해 추정한다.
산출된 배송비는 마진 계산으로 넘어간다 (R-002-02).

요율표는 core/pricing/shipping_rate.py 가 읽는다. 이 노드는 입력만 고른다.

담당: 차은호 (요율 파일은 권수현)   상태: 동작함 (요율 YAML 이 없으면 임시값)
"""

from __future__ import annotations

from app.contracts.v1 import NodeName
from app.core.graph.runtime import node
from app.core.graph.state import CountryState
from app.core.pricing.shipping_rate import estimate_options, rate_version

#: 포장 무게 미입력 시 가중치. 포장 정보를 받으면 그 값을 그대로 쓴다.
PACKAGING_FACTOR = 1.15


@node(NodeName.LOGISTICS_ESTIMATE)
async def run(state: CountryState) -> dict:
    country = state.get("country", "")
    product = state.get("product") or {}
    packaging = product.get("packaging")
    weight_g = (packaging or {}).get("weight_g") or int(
        product.get("weight_g", 0) * PACKAGING_FACTOR
    )

    return {
        "logistics": {
            "options": estimate_options(country=country, weight_g=weight_g),
            "packaging_used": packaging,
            "rate_version": rate_version(country),
        }
    }
