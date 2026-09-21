"""배송 요율 조회 (R-004-02).

무게 구간별 기본료 + kg당 요금으로 배송비와 예상 기간을 낸다. LLM 을 쓰지 않는다.
LOGISTICS_ESTIMATE 노드와 pricing/quote 동기 API 가 같은 함수를 쓴다.

data/shipping_rates/{VN,SG,TH}.yaml 예시

    version: vn-sls-2026.09
    source: Shopee SLS 요율표
    methods:
      DIRECT:
        eta_min_days: 7
        eta_max_days: 12
        fit_badge: 소량 판매에 적합
        description: 발송 채널을 직접 고를 수 있어 소량 판매 시 비용 관리가 쉽습니다.
        tiers:                     # 무게 상한(g) 기준 오름차순
          - { up_to_g: 500,  base_krw: 5200 }
          - { up_to_g: 1000, base_krw: 6200 }
          - { up_to_g: null, base_krw: 6200, per_kg_krw: 2600 }
      SLS: { ... }

담당: 권수현 (YAML 실제 값 조사·작성)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from app.config import DATA_DIR
from app.contracts.v1 import ShippingMethod
from app.observability.logging import get_logger

log = get_logger(mod="shipping_rate")

#: YAML 이 아직 없을 때 쓰는 임시값. 프론트 목 데이터와 비슷한 숫자.
#: TODO(권수현): data/shipping_rates/*.yaml 작성 후 이 표를 지운다.
_FALLBACK: dict[str, dict[str, Any]] = {
    "VN": {"DIRECT": (6200, 7, 12), "SLS": (9400, 4, 7)},
    "SG": {"DIRECT": (7100, 5, 9), "SLS": (10200, 3, 5)},
    "TH": {"DIRECT": (5600, 6, 10), "SLS": (8500, 4, 6)},
}

_BADGE = {
    ShippingMethod.DIRECT: (
        "소량 판매에 적합",
        "발송 채널을 직접 고를 수 있어 소량 판매 시 비용 관리가 쉽습니다.",
    ),
    ShippingMethod.SLS: (
        "대량 판매에 적합",
        "Shopee 주문 시스템과 연동돼 배송 관리 부담이 낮습니다.",
    ),
}


@lru_cache
def _load(country: str) -> dict:
    path = DATA_DIR / "shipping_rates" / f"{country}.yaml"
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    log.warning("배송 요율 파일 없음, 임시값 사용", country=country, expected=str(path))
    return {}


def _cost_from_tiers(tiers: list[dict], weight_g: int) -> int:
    for tier in tiers:
        limit = tier.get("up_to_g")
        if limit is None or weight_g <= limit:
            base = int(tier.get("base_krw", 0))
            per_kg = int(tier.get("per_kg_krw", 0))
            over_kg = max(0, weight_g - int(tier.get("from_g", 0))) / 1000
            return base + int(per_kg * over_kg)
    return 0


def estimate_options(*, country: str, weight_g: int) -> list[dict]:
    """이용 가능한 배송 방식과 개당 비용·기간. SLS 를 기본 추천한다."""
    raw = _load(country)
    methods = raw.get("methods") or {}
    options: list[dict] = []

    for method in (ShippingMethod.DIRECT, ShippingMethod.SLS):
        badge, description = _BADGE[method]
        spec = methods.get(method.value)
        if spec:
            cost = _cost_from_tiers(spec.get("tiers") or [], weight_g)
            eta_min = int(spec.get("eta_min_days", 0))
            eta_max = int(spec.get("eta_max_days", 0))
            badge = spec.get("fit_badge", badge)
            description = spec.get("description", description)
        else:
            cost, eta_min, eta_max = _FALLBACK.get(country, _FALLBACK["VN"])[method.value]

        options.append(
            {
                "method": method.value,
                "cost_krw": cost,
                "eta_min_days": eta_min,
                "eta_max_days": eta_max,
                "recommended": method is ShippingMethod.SLS,
                "fit_badge": badge,
                "description": description,
            }
        )
    return options


def rate_version(country: str) -> str:
    return str(_load(country).get("version", f"{country.lower()}-fallback"))
