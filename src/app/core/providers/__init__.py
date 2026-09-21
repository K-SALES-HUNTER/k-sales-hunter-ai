"""외부 데이터 어댑터.

[규칙] 데이터 소스 확보가 전체 일정을 잡지 않도록 Mock 을 먼저 만들고 파이프라인을 완성한다.
       그 다음 실제 소스를 같은 인터페이스로 갈아 끼운다.
       설정 MARKET_PROVIDER / FX_PROVIDER 로 고른다.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from app.config import get_settings


class MarketDataProvider(Protocol):
    """국가별 시장 데이터 수집 (R-001-03)."""

    async def fetch(self, *, country: str, product: dict, features: dict) -> dict: ...


class FxProvider(Protocol):
    """환율. 현지통화 1단위당 원화를 돌려준다 (R-002-04)."""

    async def rate(self, currency: str) -> float: ...


@lru_cache
def get_market_provider() -> MarketDataProvider:
    name = get_settings().market_provider
    if name == "tavily":
        from app.core.providers.tavily import TavilyMarketProvider

        return TavilyMarketProvider()
    from app.core.providers.mock import MockMarketProvider

    return MockMarketProvider()


@lru_cache
def get_fx_provider() -> FxProvider:
    name = get_settings().fx_provider
    if name == "exchangerate":
        from app.core.providers.fx import ExchangeRateProvider

        return ExchangeRateProvider()
    from app.core.providers.mock import MockFxProvider

    return MockFxProvider()
