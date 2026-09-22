"""수수료·관세·VAT 스케줄 로더.

[규칙] 수수료를 코드 상수로 박지 않는다. 유효일자와 버전을 가진 데이터로 둔다.
       계산 결과에 fee_schedule_version 을 실어 "어떤 요율로 뽑은 숫자인지" 남긴다.

data/fee_schedules/{VN,SG,TH}.yaml 예시

    version: vn-shopee-2026.09
    effective_from: 2026-09-01
    source: Shopee VN 셀러센터 수수료 공지
    currency: VND
    commission_rate: 0.04      # 카테고리별 4~9%
    transaction_fee_rate: 0.05
    payment_fee_rate: 0.02
    infra_fee_local: 3000      # 주문당 고정
    duty_rate: 0.06
    vat_rate: 0.10
    tax_base: CIF              # CIF | SALE_PRICE
    tariff_mode: MFN           # MFN | VKFTA | NONE

담당: 이동건 (마진 메이커 R-002). 관세·VAT 값은 권수현이 조사해 넘긴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache

import yaml

from app.config import DATA_DIR
from app.observability.logging import get_logger

log = get_logger(mod="fee_schedule")

#: YAML 이 아직 없을 때 쓰는 임시값. 프론트 목 데이터와 같은 숫자라 화면이 비슷하게 뜬다.
#: TODO(이동건): data/fee_schedules/*.yaml 작성 후 이 표를 지운다.
_FALLBACK: dict[str, dict] = {
    "VN": {
        "version": "vn-fallback",
        "currency": "VND",
        "commission_rate": 0.04,
        "transaction_fee_rate": 0.032,
        "payment_fee_rate": 0.02,
        "infra_fee_local": 0,
        "duty_rate": 0.06,
        "vat_rate": 0.10,
        "tax_base": "CIF",
        "tariff_mode": "MFN",
    },
    "SG": {
        "version": "sg-fallback",
        "currency": "SGD",
        "commission_rate": 0.05,
        "transaction_fee_rate": 0.02,
        "payment_fee_rate": 0.02,
        "infra_fee_local": 0,
        "duty_rate": 0.00,
        "vat_rate": 0.09,
        "tax_base": "SALE_PRICE",
        "tariff_mode": "GST",
    },
    "TH": {
        "version": "th-fallback",
        "currency": "THB",
        "commission_rate": 0.05,
        "transaction_fee_rate": 0.03,
        "payment_fee_rate": 0.02,
        "infra_fee_local": 0,
        "duty_rate": 0.10,
        "vat_rate": 0.07,
        "tax_base": "CIF",
        "tariff_mode": "MFN",
    },
}


@dataclass(frozen=True)
class FeeSchedule:
    country: str
    version: str
    currency: str
    commission_rate: Decimal
    transaction_fee_rate: Decimal
    payment_fee_rate: Decimal
    infra_fee_local: Decimal
    duty_rate: Decimal
    vat_rate: Decimal
    #: CIF = (원가+배송비) 기준 과세, SALE_PRICE = 판매가 기준 과세
    tax_base: str
    tariff_mode: str

    @property
    def platform_fee_rate(self) -> Decimal:
        """플랫폼 수수료 스택 합계. 커미션 + 거래 수수료."""
        return self.commission_rate + self.transaction_fee_rate


@lru_cache
def load(country: str) -> FeeSchedule:
    path = DATA_DIR / "fee_schedules" / f"{country}.yaml"
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        log.warning("요율 파일 없음, 임시값 사용", country=country, expected=str(path))
        raw = _FALLBACK.get(country, _FALLBACK["VN"])

    def dec(key: str, default: str = "0") -> Decimal:
        return Decimal(str(raw.get(key, default)))

    return FeeSchedule(
        country=country,
        version=str(raw.get("version", "unknown")),
        currency=str(raw.get("currency", "VND")),
        commission_rate=dec("commission_rate"),
        transaction_fee_rate=dec("transaction_fee_rate"),
        payment_fee_rate=dec("payment_fee_rate"),
        infra_fee_local=dec("infra_fee_local"),
        duty_rate=dec("duty_rate"),
        vat_rate=dec("vat_rate"),
        tax_base=str(raw.get("tax_base", "CIF")),
        tariff_mode=str(raw.get("tariff_mode", "MFN")),
    )
