"""MARKET_RESEARCH — 국가별 시장 데이터 수집 (요구사항 R-001-03).

수요·트렌드·경쟁 상품 가격·키워드를 모은다. 판단은 하지 않는다.

구현 메모
    providers.MarketDataProvider 인터페이스 뒤에 둔다. mock -> tavily 순서로 붙인다.
    TikTok Creative Center 와 Google Trends 는 공식 API 가 없어 후순위.
    결과는 Redis ai:market:* 6시간 캐시 + market_data_cache 테이블에 영구 보관한다.

담당: 차은호 (트렌드 헌터 R-001)   상태: stub
"""

from __future__ import annotations

from app.contracts.v1 import NodeName
from app.core.graph.runtime import node
from app.core.graph.state import CountryState
from app.core.providers import get_market_provider


@node(NodeName.MARKET_RESEARCH)
async def run(state: CountryState) -> dict:
    provider = get_market_provider()
    raw = await provider.fetch(
        country=state.get("country", ""),
        product=state.get("product") or {},
        features=state.get("product_features") or {},
    )
    return {"market_raw": raw}
