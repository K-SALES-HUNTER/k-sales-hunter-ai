"""CUSTOMS_GATE — 통관·금지품목 선검증 게이트 (요구사항 R-004-03/04).

파이프라인 최상단에서 판매 가능 여부를 먼저 판정한다.
PROHIBITED 면 이후 노드를 실행하지 않고 그 국가만 조기 종료한다 (R-000-02).
불필요한 LLM 호출 비용을 막는 것이 이 노드의 존재 이유다.

판정 규칙
    금지품목 매치        -> PROHIBITED  (판매 불가)
    인증·신고 의무 미충족 -> RESTRICTED  (조건부 가능)
    해당 없음            -> ALLOWED
    근거 문서 0건        -> UNKNOWN     (판매 가능으로 추정하지 않는다)

구현 메모
    VN 은 RAG(VERIFIED 문서), SG/TH 는 문서가 적어 data/policies/quick_rules/{cc}.yaml 우선.
    관세·VAT 율은 data/fee_schedules/{cc}.yaml 에서 읽어 pricing 으로 넘긴다.

담당: 권수현 (크로스보더 통관 R-004)   상태: stub
"""

from __future__ import annotations

from app.contracts.v1 import CustomsLevel, NodeName
from app.core.graph.nodes import _stubs
from app.core.graph.runtime import node
from app.core.graph.state import CountryState


@node(NodeName.CUSTOMS_GATE)
async def run(state: CountryState) -> dict:
    country = state.get("country", "")

    # TODO(권수현): rag.retriever + rag.gate_rules 로 교체. 아래는 임시값.
    tax = _stubs.TAX.get(country, {"duty_rate": 0.0, "vat_rate": 0.0, "tariff_mode": "MFN"})
    level = CustomsLevel.ALLOWED

    blocked = level is CustomsLevel.PROHIBITED
    return {
        "customs": {
            "level": level.value,
            "sellable": not blocked,
            "evidence": [],
            "structural_barriers": [],
            **tax,
        },
        #: PROHIBITED 면 이후 노드를 건너뛴다
        "filtered_out": blocked,
        "halted": blocked,
    }
