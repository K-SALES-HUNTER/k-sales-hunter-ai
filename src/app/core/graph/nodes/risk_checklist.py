"""RISK_CHECKLIST — 통관 주의사항 · 반품 리스크 · 운영 체크리스트 (R-004-05~08).

통관 경고는 반드시 근거 조항과 기준일을 함께 낸다. 근거 없이 판정하지 않는다.
프론트 '통관 처리 시 주의사항' 영역에 그대로 들어간다.

구현 메모
    RAG 로 반품 정책·플랫폼 정책·통관 가이드 문서를 top-3 뽑고 gpt-4o-mini 로 요약한다.
    면책 문구는 고정 상수로 붙인다 (정책은 바뀔 수 있고 법적 효력이 없다).

담당: 차은호   상태: stub
"""

from __future__ import annotations

from app.contracts.v1 import NodeName, RiskDifficulty
from app.core.graph.runtime import node
from app.core.graph.state import CountryState

DISCLAIMER = "정책 원문 기준일 시점의 정보이며 법적 효력이 없습니다. 최종 확인은 셀러 책임입니다."


@node(NodeName.RISK_CHECKLIST)
async def run(state: CountryState) -> dict:
    # TODO(차은호): rag.retriever + gpt-4o-mini 요약으로 교체. 아래는 임시값.
    return {
        "risk": {
            "warnings": [],
            "checklist": [],
            "difficulty": RiskDifficulty.MID.value,
            "disclaimer": DISCLAIMER,
        }
    }
