"""진입점수 산출 — 순수 함수만 둔다.

LLM 이 점수를 직접 만들면 실행마다 값이 달라지고 근거 없는 숫자가 나온다.
그래서 평가와 계산을 나눈다.
    LLM  : 시장 3축을 0~100 으로 평가하고 근거를 인용한다 (MARKET_EVALUATE)
    코드 : 아래 공식으로 합산한다. 같은 입력이면 항상 같은 결과다.

확정 공식 (제작설계서 알고리즘 명세서)
    entry_score = 0.35*수요 + 0.25*(100-경쟁강도) + 0.25*K트렌드적합도 + 0.15*수익성
    수익성      = 0.35*단위수익성 + 0.20*비용안정성 + 0.20*가격적합성
                 + 0.15*손익분기가능성 + 0.10*리스크안정성
    등급        = 70 이상 진입 적합 / 40 이상 보통 / 그 외 신중

가중치는 임의 배분이 아니다. 축의 중요도 순위를 rank-sum 으로 환산한 뒤
1위와 4위를 5%p 완충한 값이다. 성과 데이터가 쌓이면 학습 가중치로 교체한다.

[철칙] 이 패키지에서는 LLM 을 import 하지 않는다.
담당: 이동건 (마진 메이커 R-002)
"""

from __future__ import annotations

from app.contracts.v1 import AxisGrade, EntryGrade, FitGrade

# ── 상위 4축 ────────────────────────────────────────────────────────────
W_DEMAND = 0.35
W_COMPETITION = 0.25  # 낮을수록 유리하므로 (100 - c) 로 뒤집어 쓴다
W_K_FIT = 0.25
W_PROFIT = 0.15

# ── 수익성 하위 5지표 ───────────────────────────────────────────────────
PROFIT_SUB_WEIGHTS: dict[str, float] = {
    "unit_margin": 0.35,  # 개당 얼마가 남는가            (마진 메이커)
    "cost_stability": 0.20,  # 환율·수수료가 흔들려도 남는가  (마진 메이커)
    "price_fit": 0.20,  # 남는 가격이 팔리는 가격인가    (경쟁가 밴드)
    "bep_feasibility": 0.15,  # 손익분기에 닿을 수 있는가      (마진 + 시장)
    "risk_stability": 0.10,  # 잔여 리스크                   (리스크 매니저)
}

#: 등급 경계. 테스트가 이 값을 고정한다.
ENTRY_FIT_MIN = 70
ENTRY_NORMAL_MIN = 40
AXIS_HIGH_MIN = 70
AXIS_MID_MIN = 40


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """LLM 출력을 0~100 으로 방어한다. 조용한 오계산을 막는다."""
    return max(low, min(high, float(value)))


def market_partial_score(demand: float, competition: float, k_fit: float) -> float:
    """시장 3축 부분 가중합. 최대 85점 (수익성 15점은 나중에 더한다)."""
    return round(
        W_DEMAND * clamp(demand)
        + W_COMPETITION * (100.0 - clamp(competition))
        + W_K_FIT * clamp(k_fit),
        2,
    )


def profitability_score(sub_scores: dict[str, float], *, prohibited: bool = False) -> float:
    """수익성 점수. 금지품목 국가는 가중합과 무관하게 0점이다 (하드 컷).

    하위 지표가 하나라도 없으면 KeyError 로 즉시 터뜨린다. 조용히 0 으로 깎지 않는다.
    """
    if prohibited:
        return 0.0
    return round(
        sum(weight * clamp(sub_scores[key]) for key, weight in PROFIT_SUB_WEIGHTS.items()),
        2,
    )


def entry_score(market_partial: float, profit_score: float) -> int:
    return int(round(market_partial + W_PROFIT * clamp(profit_score)))


def entry_grade(score: int) -> EntryGrade:
    if score >= ENTRY_FIT_MIN:
        return EntryGrade.FIT
    if score >= ENTRY_NORMAL_MIN:
        return EntryGrade.NORMAL
    return EntryGrade.CAUTION


def axis_grade(score: float) -> AxisGrade:
    if score >= AXIS_HIGH_MIN:
        return AxisGrade.HIGH
    if score >= AXIS_MID_MIN:
        return AxisGrade.MID
    return AxisGrade.LOW


def fit_grade(rank: int, grade: EntryGrade) -> FitGrade:
    """프론트 국가 카드 뱃지. 1위이면서 진입 적합이면 '매우 적합'."""
    if grade is EntryGrade.FIT:
        return FitGrade.VERY_FIT if rank == 1 else FitGrade.PARTIAL_FIT
    if grade is EntryGrade.NORMAL:
        return FitGrade.NORMAL
    return FitGrade.CAUTION


# ── 하위 5지표 산출 (임시 규칙) ─────────────────────────────────────────
# TODO(이동건): 마진·리스크 실제 산출값으로 정교화한다.


def unit_margin_score(margin_rate: float) -> float:
    """마진율 0 이면 0점, 30% 이상이면 100점 선형."""
    return clamp(margin_rate / 0.30 * 100)


def cost_stability_score(margin_rate: float, margin_rate_fx_down: float) -> float:
    """환율이 10% 불리해졌을 때 마진율이 얼마나 버티는가."""
    if margin_rate <= 0:
        return 0.0
    kept = max(0.0, margin_rate_fx_down) / margin_rate
    return clamp(kept * 100)


def price_fit_score(price_krw: int, band: dict | None) -> float:
    """추천가가 경쟁가 밴드 안이면 100점, 벗어난 만큼 깎는다."""
    if not band:
        return 50.0
    low, high = band.get("low_krw", 0), band.get("high_krw", 0)
    if not high or low >= high:
        return 50.0
    if low <= price_krw <= high:
        return 100.0
    gap = (low - price_krw) if price_krw < low else (price_krw - high)
    return clamp(100 - (gap / high) * 100)


def bep_feasibility_score(break_even_units: int | None) -> float:
    """손익분기 수량이 없으면 '추정' 취급해 중립값을 준다."""
    if break_even_units is None:
        return 50.0
    if break_even_units <= 300:
        return 100.0
    if break_even_units >= 3000:
        return 0.0
    return clamp(100 - (break_even_units - 300) / 27)


def risk_stability_score(customs_level: str) -> float:
    return {
        "ALLOWED": 100.0,
        "RESTRICTED": 60.0,
        "UNKNOWN": 40.0,
        "PROHIBITED": 0.0,
    }.get(customs_level, 40.0)
