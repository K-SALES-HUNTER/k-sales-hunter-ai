"""부분 재실행 — 바뀐 필드로 다시 돌 노드를 정한다 (요구사항 R-000-05, 화면 EDT-01-01).

상품 수정이나 포장 변경으로 PARTIAL 잡이 오면 처음부터 다 돌지 않는다.
바뀐 필드가 영향을 주는 가장 앞 노드부터 돌리고, 그 앞 노드 산출물은 이전 결과에서 복원한다.
체크포인터를 쓰지 않는다. 이전 결과(previousResult)가 곧 체크포인트다.

    원가 변경          product.supplyCostKrw   ─▶ MARGIN 부터            (LLM 0회, 즉시)
    무게·포장 변경     product.weightG/packaging ─▶ LOGISTICS_ESTIMATE 부터
    목표 마진·배송 방식 preferences.*           ─▶ MARGIN 부터
    브랜드 톤 변경     marketProfile.*         ─▶ MARKET_INSIGHT 부터
    상품명·카테고리·설명·이미지 / 모르는 필드 ─▶ 처음부터 (통관 판정이 바뀔 수 있다)

복원할 수 없으면 처음부터 돈다. 예) 이전 결과에 market_raw 가 없는데 MARKET_INSIGHT 부터
시작해야 하는 경우. 틀린 결과보다 느린 결과가 낫다.

담당: 강근우 (비서 AI 오케스트레이터 R-000-05)
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from app.contracts.v1 import (
    COUNTRY_NODE_ORDER,
    CountryResult,
    CountryStatus,
    NodeName,
)

FULL = NodeName.PRODUCT_UNDERSTANDING

#: 필드 -> 다시 시작할 노드. 키는 snake_case 경로. 접두사로도 찾는다 (market_profile.*).
FIELD_START: dict[str, NodeName] = {
    "product.name": FULL,
    "product.category": FULL,
    "product.description": FULL,
    "product.selling_point": FULL,
    "product.main_target": FULL,
    "product.image_urls": FULL,
    "product.weight_g": NodeName.LOGISTICS_ESTIMATE,
    "product.packaging": NodeName.LOGISTICS_ESTIMATE,
    "product.supply_cost_krw": NodeName.MARGIN,
    "preferences.target_margin_rate": NodeName.MARGIN,
    "preferences.fixed_cost_krw": NodeName.MARGIN,
    "preferences.shipping_method": NodeName.MARGIN,
    "market_profile": NodeName.MARKET_INSIGHT,
}

#: 노드가 CountryState 에 남기는 키. 복원할 때 이 키들을 이전 결과에서 꺼낸다.
NODE_OUTPUTS: dict[NodeName, tuple[str, ...]] = {
    NodeName.PRODUCT_UNDERSTANDING: ("product_features",),
    NodeName.CUSTOMS_GATE: ("customs",),
    NodeName.MARKET_RESEARCH: ("market_raw",),
    NodeName.MARKET_EVALUATE: ("scores", "competition"),
    NodeName.MARKET_INSIGHT: ("insight",),
    NodeName.LOGISTICS_ESTIMATE: ("logistics",),
    NodeName.MARGIN: ("pricing",),
    NodeName.RISK_CHECKLIST: ("risk",),
}

_CAMEL = re.compile(r"(?<!^)(?=[A-Z])")


def normalize(field: str) -> str:
    """'product.supplyCostKrw' -> 'product.supply_cost_krw'. Spring 은 camelCase 로 보낸다."""
    return ".".join(_CAMEL.sub("_", part).lower() for part in field.split("."))


def _start_for(field: str) -> NodeName:
    path = normalize(field)
    while path:
        if path in FIELD_START:
            return FIELD_START[path]
        path = path.rpartition(".")[0]
    return FULL


def start_node(changed_fields: list[str]) -> NodeName:
    """바뀐 필드들 중 가장 앞 노드. 아무것도 없으면 처음부터."""
    if not changed_fields:
        return FULL
    starts = [_start_for(field) for field in changed_fields]
    return min(starts, key=COUNTRY_NODE_ORDER.index)


def find_previous(previous_result: dict | None, country: str) -> dict | None:
    if not previous_result:
        return None
    for item in previous_result.get("countries") or []:
        if item.get("country") == country:
            return item
    return None


def _snapshot(previous: dict) -> dict | None:
    """이전 결과를 계약 스키마로 읽는다. 형식이 깨졌으면 None (처음부터 돌린다)."""
    try:
        return CountryResult.model_validate(previous).model_dump(mode="json")
    except ValidationError:
        return None


def carry_over(previous: dict, start: NodeName) -> dict | None:
    """다시 돌 필요가 없는 국가면 이전 스냅샷을 그대로 준다.

    통관에서 막힌 국가는 통관 뒤 필드가 바뀌어도 여전히 막혀 있다.
    """
    status = previous.get("status")
    gate_index = COUNTRY_NODE_ORDER.index(NodeName.CUSTOMS_GATE)
    if status == CountryStatus.FILTERED_OUT.value and COUNTRY_NODE_ORDER.index(start) > gate_index:
        return _snapshot(previous)
    return None


def restore(previous: dict, start: NodeName) -> dict[str, Any] | None:
    """start 앞 노드들의 산출물을 CountryState 모양(snake_case)으로 되살린다.

    하나라도 없으면 None. 호출한 쪽은 처음부터 돌린다.
    실패한 국가도 None 이다. 이전 결과가 불완전해 믿을 수 없다.
    """
    if start == FULL:
        return None
    if previous.get("status") == CountryStatus.FAILED.value:
        return None

    snapshot = _snapshot(previous)
    if snapshot is None:
        return None
    patch: dict[str, Any] = {}
    done: list[str] = []
    for node in COUNTRY_NODE_ORDER[: COUNTRY_NODE_ORDER.index(start)]:
        for key in NODE_OUTPUTS[node]:
            if snapshot.get(key) is None:
                return None
            patch[key] = snapshot[key]
        done.append(node.value)

    patch["completed_nodes"] = done
    return patch
