"""ExchangeRate-API 환율 프로바이더 (R-002-04).

FX_PROVIDER=exchangerate 일 때 쓴다. 테스트·오프라인은 MockFxProvider.
Redis 에 1시간 캐싱하고 기준 시각을 같이 남긴다. 결과의 fx.asOf 로 나간다.

왜 1시간인가
    ExchangeRate-API 무료 플랜은 하루 단위로 갱신되고 호출 수 제한이 있다.
    분석 1건(3개국)·화면 재계산마다 부르면 금방 한도에 닿는다.
    1시간이면 같은 날 안에서 값이 사실상 같고 호출은 시간당 통화 3개로 끝난다.

실패하면
    HTTP 오류는 그대로 올린다(raise_for_status). 노드 데코레이터가 해당 국가만 실패 처리하고
    다른 국가는 계속 간다. 오래된 값을 조용히 쓰지 않는다.

담당: 이동건 (마진 메이커 R-002)
"""

from __future__ import annotations

import httpx
import redis.asyncio as aioredis

from app.config import get_settings


class ExchangeRateProvider:
    TTL = 3600  # 1시간

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.exchange_rate_api_key
        self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    async def rate(self, currency: str) -> float:
        """현지통화 1단위당 KRW."""
        key = f"ai:fx:{currency}"
        if cached := await self._redis.get(key):
            return float(cached)
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"https://v6.exchangerate-api.com/v6/{self._api_key}/pair/{currency}/KRW"
            )
        resp.raise_for_status()
        data = resp.json()
        rate = float(data["conversion_rate"])
        await self._redis.set(key, rate, ex=self.TTL)
        await self._redis.set(f"{key}:as_of", data["time_last_update_utc"], ex=self.TTL)
        return rate

    async def as_of(self, currency: str) -> str:
        """rate() 가 쓴 환율의 기준 시각."""
        return await self._redis.get(f"ai:fx:{currency}:as_of") or ""
