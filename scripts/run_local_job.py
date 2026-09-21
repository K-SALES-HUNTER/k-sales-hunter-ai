"""HTTP·DB 없이 분석 그래프만 돌린다.

개발 중 대부분은 이걸로 확인한다. 서버를 띄우고 프론트를 붙이는 것보다 훨씬 빠르다.

    make demo-job
    python scripts/run_local_job.py --countries VN
    python scripts/run_local_job.py --out out/result.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.contracts.v1 import (  # noqa: E402
    SUPPORTED_COUNTRIES,
    AnalysisPreferences,
    MarketProfile,
    Packaging,
    ProductSnapshot,
)
from app.core.graph.runtime import JobContext, current_job  # noqa: E402
from app.observability.logging import configure_logging  # noqa: E402

#: 골든 상품. 프론트 목 데이터와 같은 값이라 화면과 비교하기 좋다.
SAMPLE = ProductSnapshot(
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


async def run(countries: list[str]) -> dict:
    from app.core.graph.analysis import build_analysis_graph
    from app.core.jobs.runner import _assemble_analysis

    job_id = "local-1"
    #: detached=True 면 DB 를 쓰지 않는다
    ctx = JobContext(job_id=job_id, countries=countries, detached=True)
    token = current_job.set(ctx)
    try:
        graph = build_analysis_graph()
        state = await graph.ainvoke(
            {
                "meta": {"job_id": job_id, "trace_id": "local"},
                "countries": countries,
                "product": SAMPLE.model_dump(),
                "market_profile": MarketProfile(brand_direction="K-트렌드").model_dump(),
                "preferences": AnalysisPreferences().model_dump(),
                "country_results": [],
            }
        )
        return _assemble_analysis(job_id, state)
    finally:
        current_job.reset(token)


def main() -> None:
    parser = argparse.ArgumentParser(description="분석 잡 로컬 실행")
    parser.add_argument("--countries", nargs="*", default=list(SUPPORTED_COUNTRIES))
    parser.add_argument("--out", default="out/analysis_result.json")
    args = parser.parse_args()

    configure_logging()
    result = asyncio.run(run(args.countries))

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n결과 저장: {out_path.relative_to(ROOT)}")
    for item in result.get("countries", []):
        scores = item.get("scores") or {}
        print(
            f"  {item['country']}  진입점수 {scores.get('entryScore')}"
            f"  등급 {scores.get('entryGrade')}  순위 {scores.get('rank')}"
            f"  상태 {item.get('status')}"
        )
    print(f"  결론: {result.get('global', {}).get('conclusionTitle') or '(LLM 미연결)'}")


if __name__ == "__main__":
    main()
