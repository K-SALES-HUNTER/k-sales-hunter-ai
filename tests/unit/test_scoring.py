"""진입점수 공식 고정.

이 테스트가 깨지면 명세서와 코드가 어긋난 것이다. 값을 고치기 전에 문서를 먼저 확인한다.
"""

from __future__ import annotations

import pytest

from app.contracts.v1 import AxisGrade, EntryGrade, FitGrade
from app.core.pricing import scoring


def test_시장_3축_가중합_공식():
    # 0.35*80 + 0.25*(100-40) + 0.25*90 = 28 + 15 + 22.5 = 65.5
    assert scoring.market_partial_score(80, 40, 90) == pytest.approx(65.5)


def test_시장_부분점수는_최대_85점():
    assert scoring.market_partial_score(100, 0, 100) == pytest.approx(85.0)


def test_경쟁강도는_낮을수록_유리():
    낮은_경쟁 = scoring.market_partial_score(50, 10, 50)
    높은_경쟁 = scoring.market_partial_score(50, 90, 50)
    assert 낮은_경쟁 > 높은_경쟁


def test_수익성_하위_5지표_가중합():
    sub = {
        "unit_margin": 100,
        "cost_stability": 100,
        "price_fit": 100,
        "bep_feasibility": 100,
        "risk_stability": 100,
    }
    assert scoring.profitability_score(sub) == pytest.approx(100.0)


def test_금지품목_국가는_수익성_0점_하드컷():
    sub = dict.fromkeys(scoring.PROFIT_SUB_WEIGHTS, 100.0)
    assert scoring.profitability_score(sub, prohibited=True) == 0.0


def test_하위지표가_빠지면_조용히_넘어가지_않는다():
    with pytest.raises(KeyError):
        scoring.profitability_score({"unit_margin": 50})


def test_진입점수는_부분합에_수익성_15퍼센트를_더한다():
    # 65.5 + 0.15*80 = 77.5 -> 78
    assert scoring.entry_score(65.5, 80) == 78


def test_LLM_출력이_범위를_벗어나도_방어된다():
    assert scoring.clamp(150) == 100.0
    assert scoring.clamp(-20) == 0.0


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (70, EntryGrade.FIT),
        (69, EntryGrade.NORMAL),
        (40, EntryGrade.NORMAL),
        (39, EntryGrade.CAUTION),
    ],
)
def test_진입등급_경계값(score: int, expected: EntryGrade):
    assert scoring.entry_grade(score) is expected


@pytest.mark.parametrize(
    ("score", "expected"),
    [(70, AxisGrade.HIGH), (69, AxisGrade.MID), (40, AxisGrade.MID), (39, AxisGrade.LOW)],
)
def test_축등급_경계값(score: int, expected: AxisGrade):
    assert scoring.axis_grade(score) is expected


def test_1위이면서_진입적합이면_매우적합():
    assert scoring.fit_grade(1, EntryGrade.FIT) is FitGrade.VERY_FIT
    assert scoring.fit_grade(2, EntryGrade.FIT) is FitGrade.PARTIAL_FIT
    assert scoring.fit_grade(1, EntryGrade.CAUTION) is FitGrade.CAUTION


def test_추천가가_경쟁가_밴드_안이면_만점():
    band = {"low_krw": 5000, "high_krw": 30000}
    assert scoring.price_fit_score(20000, band) == 100.0
    assert scoring.price_fit_score(50000, band) < 100.0


def test_손익분기_수량이_없으면_중립값():
    """고정비 미입력은 '나쁨'이 아니라 '모름'이다."""
    assert scoring.bep_feasibility_score(None) == 50.0
