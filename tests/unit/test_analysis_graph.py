"""분석 그래프가 끝까지 도는지 확인한다.

LLM 과 외부 API 는 Fake/Mock 이라 비용이 들지 않고 결과가 항상 같다.
"""

from __future__ import annotations

import pytest

from app.contracts.v1 import AnalysisResult, CountryStatus, CustomsLevel, NodeName
from app.core.graph.analysis import build_analysis_graph
from app.core.graph.runtime import JobContext, current_job, node
from app.core.jobs.runner import _assemble_analysis


async def _run(payload: dict) -> dict:
    ctx = JobContext(job_id="test-1", countries=list(payload["countries"]), detached=True)
    token = current_job.set(ctx)
    try:
        state = await build_analysis_graph().ainvoke(payload)
        return _assemble_analysis("test-1", state)
    finally:
        current_job.reset(token)


async def test_3개국이_모두_끝까지_돈다(analysis_input: dict):
    result = await _run(analysis_input)
    countries = {item["country"] for item in result["countries"]}
    assert countries == {"VN", "SG", "TH"}
    assert all(item["status"] == CountryStatus.DONE.value for item in result["countries"])


async def test_결과가_계약_스키마를_만족한다(analysis_input: dict):
    """Spring 이 그대로 역직렬화할 수 있어야 한다."""
    result = await _run(analysis_input)
    parsed = AnalysisResult.model_validate(result)
    assert parsed.job_id == "test-1"
    assert len(parsed.countries) == 3


async def test_모든_노드를_거친다(analysis_input: dict):
    result = await _run(analysis_input)
    vn = next(item for item in result["countries"] if item["country"] == "VN")
    assert set(vn["completedNodes"]) == {
        NodeName.PRODUCT_UNDERSTANDING.value,
        NodeName.CUSTOMS_GATE.value,
        NodeName.MARKET_RESEARCH.value,
        NodeName.MARKET_EVALUATE.value,
        NodeName.MARKET_INSIGHT.value,
        NodeName.LOGISTICS_ESTIMATE.value,
        NodeName.MARGIN.value,
        NodeName.RISK_CHECKLIST.value,
    }


async def test_진입점수와_순위가_확정된다(analysis_input: dict):
    result = await _run(analysis_input)
    ranks = sorted(item["scores"]["rank"] for item in result["countries"])
    assert ranks == [1, 2, 3]

    #: 순위가 높을수록 진입점수가 높아야 한다
    ordered = sorted(result["countries"], key=lambda item: item["scores"]["rank"])
    scores = [item["scores"]["entryScore"] for item in ordered]
    assert scores == sorted(scores, reverse=True)


async def test_통관_차단이면_이후_노드를_건너뛴다(analysis_input: dict, monkeypatch):
    """게이트 우선 원칙 (R-000-02). 판매 불가 국가에 LLM 비용을 쓰지 않는다."""
    from app.core.graph.nodes import customs_gate

    async def blocked(state):  # noqa: ANN001, ANN202
        return {
            "customs": {"level": CustomsLevel.PROHIBITED.value, "sellable": False},
            "filtered_out": True,
            "halted": True,
        }

    monkeypatch.setattr(customs_gate, "run", node(NodeName.CUSTOMS_GATE)(blocked))

    result = await _run({**analysis_input, "countries": ["VN"]})
    vn = result["countries"][0]
    assert vn["status"] == CountryStatus.FILTERED_OUT.value
    #: 게이트 이후 노드는 실행되지 않는다
    assert NodeName.MARKET_RESEARCH.value not in vn["completedNodes"]
    assert vn["pricing"] is None


async def test_국가_하나가_실패해도_나머지는_끝난다(analysis_input: dict, monkeypatch):
    from app.core.graph.nodes import market_research

    original = market_research.run

    async def flaky(state):  # noqa: ANN001, ANN202
        if state.get("country") == "SG":
            raise RuntimeError("외부 API 장애")
        return await original(state)

    #: 데코레이터를 그대로 씌워야 실패가 해당 국가만 중단시킨다
    monkeypatch.setattr(market_research, "run", node(NodeName.MARKET_RESEARCH)(flaky))

    result = await _run(analysis_input)
    by_code = {item["country"]: item for item in result["countries"]}
    assert by_code["SG"]["status"] == CountryStatus.FAILED.value
    assert by_code["VN"]["status"] == CountryStatus.DONE.value
    assert by_code["TH"]["status"] == CountryStatus.DONE.value


@pytest.mark.parametrize("country", ["VN", "SG", "TH"])
async def test_국가별_비용_구조가_프론트_표_순서와_같다(analysis_input: dict, country: str):
    result = await _run({**analysis_input, "countries": [country]})
    scenario = next(
        item for item in result["countries"][0]["pricing"]["scenarios"] if item["recommended"]
    )
    keys = [row["key"] for row in scenario["costRows"]]
    assert keys == [
        "salePrice",
        "supplyCost",
        "platformFee",
        "shipping",
        "duty",
        "vat",
        "netProfit",
    ]
