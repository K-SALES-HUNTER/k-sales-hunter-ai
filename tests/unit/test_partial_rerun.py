"""부분 재실행 (R-000-05) — 바뀐 필드만큼만 다시 돈다.

시장 수집 프로바이더를 '부르면 실패'로 바꿔 끼워, 재실행이 시장 노드를 건너뛰는지 확인한다.
"""

from __future__ import annotations

import copy

import pytest

from app.contracts.v1 import CountryStatus, NodeName
from app.core.graph import rerun_map
from app.core.graph.analysis import build_analysis_graph
from app.core.graph.nodes import market_research
from app.core.graph.runtime import JobContext, current_job
from app.core.jobs.runner import _assemble_analysis


async def _run(payload: dict) -> dict:
    ctx = JobContext(job_id="test-1", countries=list(payload["countries"]), detached=True)
    token = current_job.set(ctx)
    try:
        state = await build_analysis_graph().ainvoke(payload)
        return _assemble_analysis("test-1", state)
    finally:
        current_job.reset(token)


def _country(result: dict, code: str) -> dict:
    return next(item for item in result["countries"] if item["country"] == code)


def _mid_profit(entry: dict) -> int:
    scenario = next(item for item in entry["pricing"]["scenarios"] if item["tier"] == "MID")
    return scenario["netProfitKrw"]


@pytest.fixture
def forbid_market(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """시장 수집을 부르면 그 국가가 실패한다. 호출된 국가를 기록한다."""
    called: list[str] = []

    class Boom:
        async def fetch(self, *, country, product, features):  # noqa: ANN001, ANN202
            called.append(country)
            raise RuntimeError("부분 재실행인데 시장 수집을 불렀다")

    monkeypatch.setattr(market_research, "get_market_provider", lambda: Boom())
    return called


# ── 판정 ────────────────────────────────────────────────────────────────


def test_camelCase_필드도_읽는다():
    assert rerun_map.normalize("product.supplyCostKrw") == "product.supply_cost_krw"
    assert rerun_map.start_node(["product.supplyCostKrw"]) is NodeName.MARGIN


def test_여러_필드면_가장_앞_노드부터():
    fields = ["product.supplyCostKrw", "product.packaging.widthMm"]
    assert rerun_map.start_node(fields) is NodeName.LOGISTICS_ESTIMATE
    assert rerun_map.start_node(["marketProfile.brandTone"]) is NodeName.MARKET_INSIGHT


def test_모르는_필드나_빈_목록은_처음부터():
    assert rerun_map.start_node(["product.somethingNew"]) is rerun_map.FULL
    assert rerun_map.start_node(["product.category"]) is rerun_map.FULL
    assert rerun_map.start_node([]) is rerun_map.FULL


def test_복원할_값이_없으면_None():
    previous = {"country": "VN", "status": "DONE", "customs": {"level": "ALLOWED"}}
    assert rerun_map.restore(previous, NodeName.MARGIN) is None


# ── 그래프 ──────────────────────────────────────────────────────────────


async def test_원가만_바꾸면_마진부터_다시_돈다(analysis_input: dict, forbid_market: list[str]):
    #: 첫 분석은 시장 수집이 정상이어야 하므로 기록만 비우고 직접 돌린다
    forbid_market.clear()
    first = await _run_with_real_market(analysis_input)

    payload = copy.deepcopy(analysis_input)
    payload["product"]["supply_cost_krw"] += 5000
    payload["changed_fields"] = ["product.supplyCostKrw"]
    payload["previous_result"] = first
    second = await _run(payload)

    assert forbid_market == []
    vn_before, vn_after = _country(first, "VN"), _country(second, "VN")
    assert vn_after["status"] == CountryStatus.DONE.value
    assert len(vn_after["completedNodes"]) == 8
    #: 복원한 시장 점수는 그대로, 원가가 오른 만큼 순이익은 준다
    assert vn_after["scores"]["demand"] == vn_before["scores"]["demand"]
    assert _mid_profit(vn_after) < _mid_profit(vn_before)
    assert sorted(item["scores"]["rank"] for item in second["countries"]) == [1, 2, 3]


async def test_이전_결과가_불완전하면_처음부터_돈다(analysis_input: dict, forbid_market: list[str]):
    first = await _run_with_real_market(analysis_input)
    for item in first["countries"]:
        item["marketRaw"] = None  # 필드가 생기기 전 결과

    payload = copy.deepcopy(analysis_input)
    payload["changed_fields"] = ["marketProfile.brandTone"]
    payload["previous_result"] = first
    second = await _run(payload)

    #: MARKET_INSIGHT 부터 돌 수 없어 처음부터 → 시장 수집을 불러 실패한다
    assert sorted(forbid_market) == ["SG", "TH", "VN"]
    assert all(item["status"] == CountryStatus.FAILED.value for item in second["countries"])


async def test_통관에서_막힌_국가는_다시_돌리지_않는다(
    analysis_input: dict, forbid_market: list[str]
):
    first = await _run_with_real_market(analysis_input)
    th = _country(first, "TH")
    th["status"] = CountryStatus.FILTERED_OUT.value
    th["customs"]["level"] = "PROHIBITED"

    payload = copy.deepcopy(analysis_input)
    payload["changed_fields"] = ["product.weightG"]
    payload["previous_result"] = first
    second = await _run(payload)

    th_after = _country(second, "TH")
    assert th_after["status"] == CountryStatus.FILTERED_OUT.value
    assert th_after["customs"]["level"] == "PROHIBITED"
    assert forbid_market == []


async def test_새로_추가된_국가는_처음부터_돈다(analysis_input: dict, forbid_market: list[str]):
    first = await _run_with_real_market({**analysis_input, "countries": ["VN", "SG"]})

    payload = copy.deepcopy(analysis_input)  # VN·SG·TH
    payload["changed_fields"] = ["product.supplyCostKrw"]
    payload["previous_result"] = first
    second = await _run(payload)

    assert forbid_market == ["TH"]
    assert _country(second, "VN")["status"] == CountryStatus.DONE.value


async def _run_with_real_market(payload: dict) -> dict:
    """forbid_market 를 잠시 풀고 첫 분석을 돌린다."""
    from app.core.providers import get_market_provider

    patched = market_research.get_market_provider
    market_research.get_market_provider = get_market_provider
    try:
        return await _run(copy.deepcopy(payload))
    finally:
        market_research.get_market_provider = patched
