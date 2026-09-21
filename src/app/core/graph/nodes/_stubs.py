"""stub 노드가 돌려주는 임시 값.

[삭제 예정] 각 노드가 실제 구현되면 해당 항목을 여기서 지운다.
            프론트 목 데이터와 비슷한 값을 넣어 두어 연동 화면이 그럴듯하게 뜬다.
담당: 차은호 (노드 구현하면서 하나씩 제거)
"""

from __future__ import annotations

#: 국가별 임시 축 점수 (프론트 mocks/report.ts 값과 맞춤)
AXES: dict[str, dict[str, int]] = {
    "VN": {"demand": 87, "competition": 58, "k_fit": 84, "profitability": 71},
    "SG": {"demand": 66, "competition": 78, "k_fit": 81, "profitability": 83},
    "TH": {"demand": 82, "competition": 74, "k_fit": 88, "profitability": 64},
}

#: 국가별 임시 관세·VAT (data/fee_schedules/*.yaml 이 생기면 제거)
TAX: dict[str, dict] = {
    "VN": {"duty_rate": 0.06, "vat_rate": 0.10, "tariff_mode": "MFN"},
    "SG": {"duty_rate": 0.00, "vat_rate": 0.09, "tariff_mode": "GST"},
    "TH": {"duty_rate": 0.10, "vat_rate": 0.07, "tariff_mode": "MFN"},
}

#: 국가별 임시 경쟁가 밴드 (원화)
PRICE_BAND: dict[str, dict] = {
    "VN": {"low_krw": 5000, "mid_krw": 10000, "high_krw": 30000, "weights": [162, 243, 162]},
    "SG": {"low_krw": 10000, "mid_krw": 20000, "high_krw": 40000, "weights": [132, 268, 168]},
    "TH": {"low_krw": 5000, "mid_krw": 10000, "high_krw": 30000, "weights": [210, 232, 126]},
}

POSITIONING: dict[str, tuple[str, str]] = {
    "VN": ("PREMIUM", "프리미엄형"),
    "SG": ("GIFT", "선물형"),
    "TH": ("ENTRY", "입문형"),
}
