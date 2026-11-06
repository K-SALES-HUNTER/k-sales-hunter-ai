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


@pytest.fixture
def memory_store(monkeypatch: pytest.MonkeyPatch) -> dict:
    """ai.jobs 대신 메모리에 잡을 저장한다. Postgres 없이 runner·dev_bff 전 구간을 돌린다.

    store 모듈의 함수만 바꿔 끼우므로 runner·runtime·dev_bff 코드는 그대로 탄다.
    """
    from types import SimpleNamespace

    from app.contracts.v1 import JobStatus
    from app.core.jobs import store
    from app.errors import JobNotFound

    rows: dict[str, SimpleNamespace] = {}

    async def create(*, job_id, job_type, request, trace_id="", countries=None):  # noqa: ANN001, ANN202
        rows[job_id] = SimpleNamespace(
            job_id=job_id,
            job_type=job_type.value,
            status=JobStatus.QUEUED.value,
            step=None,
            progress=0.0,
            country_states={
                code: {"status": "RUNNING", "step": None, "progress": 0.0}
                for code in (countries or [])
            },
            request=request,
            result=None,
            error_code=None,
            error_detail=None,
            created_at=None,
            finished_at=None,
        )

    async def patch(job_id, **fields):  # noqa: ANN001, ANN003, ANN202
        row = rows[job_id]
        for key, value in fields.items():
            setattr(row, key, value)

    async def get(job_id):  # noqa: ANN001, ANN202
        if job_id not in rows:
            raise JobNotFound(job_id)
        return store._to_state(rows[job_id])

    async def request_cancel(job_id):  # noqa: ANN001, ANN202
        row = rows[job_id]
        if JobStatus(row.status).is_terminal:
            return False
        row.status = JobStatus.CANCEL_REQUESTED.value
        return True

    async def is_cancel_requested(job_id):  # noqa: ANN001, ANN202
        return rows[job_id].status == JobStatus.CANCEL_REQUESTED.value

    monkeypatch.setattr(store, "create", create)
    monkeypatch.setattr(store, "patch", patch)
    monkeypatch.setattr(store, "get", get)
    monkeypatch.setattr(store, "request_cancel", request_cancel)
    monkeypatch.setattr(store, "is_cancel_requested", is_cancel_requested)
    #: mark_running / finish 는 patch 를 부르므로 그대로 둔다
    return rows
