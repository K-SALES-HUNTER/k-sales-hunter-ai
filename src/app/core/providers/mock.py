"""Mock 어댑터 — 외부 API 없이 전 구간을 돌린다.

테스트와 오프라인 데모에서 쓴다. 값이 항상 같아 결과를 비교하기 좋다.
"""

from __future__ import annotations

from datetime import UTC, datetime

#: 현지통화 1단위당 원화. 실제 환율은 ExchangeRateProvider 가 가져온다.
MOCK_RATES: dict[str, float] = {
    "VND": 0.055,
    "SGD": 1160.5,
    "THB": 39.0,
    "KRW": 1.0,
}

#: 국가별 경쟁 상품 가격 샘플 (KRW). 밴드 계산 입력.
_PRICE_SAMPLES: dict[str, list[int]] = {
    "VN": [4800, 6200, 8900, 10500, 12000, 15800, 22000, 28000, 34000],
    "SG": [9800, 12400, 16000, 19800, 23000, 27500, 33000, 39000, 45000],
    "TH": [3900, 5100, 6800, 8200, 9900, 13000, 18000, 24000, 31000],
}


class MockMarketProvider:
    async def fetch(self, *, country: str, product: dict, features: dict) -> dict:
        return {
            "source": "mock",
            "collected_at": datetime.now(UTC).isoformat(),
            "demand_signals": [
                {"keyword": product.get("category", ""), "trend_index": 62, "growth_rate": 0.12}
            ],
            "competitors": [],
            "price_samples_krw": _PRICE_SAMPLES.get(country, _PRICE_SAMPLES["VN"]),
            "trend_snippets": [],
        }


class MockFxProvider:
    async def rate(self, currency: str) -> float:
        return MOCK_RATES.get(currency, 1.0)
