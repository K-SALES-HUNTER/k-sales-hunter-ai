"""판매 정보 추천 — 카테고리·속성·옵션 (요구사항 R-003-12/13, 화면 RPT-02-02).

AI 가 먼저 채우고 사람이 확정한다 (HITL). 확정값이 상세페이지와 업로드에 그대로 쓰인다.

Shopee 제약
    옵션은 최대 2단, 조합은 최대 50개. 초과하면 등록이 안 되므로 코드가 막는다.
    카테고리는 최종 하위(leaf) 를 골라야 하고 국가마다 id 가 다르다.

구현 메모
    data/shopee_categories/{cc}.json 에서 키워드 매칭으로 후보 5개를 추린 뒤
    gpt-4o-mini 가 1개를 고르고 속성 값을 채운다. 후보를 좁혀야 환각이 줄고 싸다.

담당: 강근우   상태: stub
"""

from __future__ import annotations

from app.contracts.v1 import SalesSuggestRequest, SalesSuggestResponse

#: Shopee 제약. 검증은 Spring 과 여기 양쪽에서 한다.
MAX_OPTION_LEVELS = 2
MAX_COMBINATIONS = 50


async def suggest(request: SalesSuggestRequest) -> SalesSuggestResponse:
    # TODO(강근우): 카테고리 JSON 매칭 + gpt-4o-mini 로 교체
    return SalesSuggestResponse(category_id=request.category_id or "")
