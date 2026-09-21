"""테스트 공통 설정.

[원칙] 기본은 LLM 을 부르지 않는다. FakeLLM 이 결정론 응답을 돌려준다.
       실제 LLM 을 부르는 테스트는 @pytest.mark.live 로 표시하고 CI 에서 뺀다.
"""

from __future__ import annotations

import os

import pytest

#: import 전에 걸어야 Settings 캐시에 반영된다
os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ.setdefault("MARKET_PROVIDER", "mock")
os.environ.setdefault("FX_PROVIDER", "mock")
os.environ.setdefault("APP_ENV", "test")

from app.contracts.v1 import (  # noqa: E402
    AnalysisPreferences,
    MarketProfile,
    Packaging,
    ProductSnapshot,
)


@pytest.fixture
def product() -> ProductSnapshot:
    """골든 상품. 프론트 목 데이터와 같은 값."""
    return ProductSnapshot(
        product_id=1,
        name="제주 화산송이 클렌저 150ml",
        category="뷰티",
        supply_cost_krw=12800,
        weight_g=220,
        description="제주 화산송이 성분으로 모공 속 노폐물을 관리하는 클렌저.",
        selling_point="제주 화산송이 원료 · 저자극 약산성 · 비건 인증",
        main_target="20~30대 스킨케어에 관심 많은 여성",
        packaging=Packaging(weight_g=320, width_mm=180, depth_mm=80, height_mm=80),
    )


@pytest.fixture
def analysis_input(product: ProductSnapshot) -> dict:
    return {
        "meta": {"job_id": "test-1", "trace_id": "test"},
        "countries": ["VN", "SG", "TH"],
        "product": product.model_dump(),
        "market_profile": MarketProfile().model_dump(),
        "preferences": AnalysisPreferences().model_dump(),
        "country_results": [],
    }
