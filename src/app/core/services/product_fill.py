"""상품 등록 'AI 자동 채우기' (요구사항 R-001-02, 화면 PRD-01-02).

프론트는 비어 있는 항목에만 이 값을 채운다. 사용자가 입력한 값은 덮어쓰지 않는다.
사용자가 나중에 수정하면 'AI가 채움' 표시가 해제된다.

구현 메모
    gpt-4o vision 1회. 이미지는 최대 4장, 1024px 로 리사이즈해 보낸다 (비용·지연 절감).
    category 는 프론트 드롭다운 11종 중 하나여야 한다. enum 으로 강제한다.
    selling_points 는 "A · B · C" 형식으로 만든다 (프론트 표기 규칙).
    이미지를 못 받으면 텍스트만으로 진행하고 image_used=False 를 남긴다.
    응답 10초 이내. 캐시 키는 입력 해시.

담당: 강근우   상태: stub
"""

from __future__ import annotations

from app.contracts.v1 import ProductFillRequest, ProductFillResponse

#: 프론트 드롭다운과 같은 목록. 이 밖의 값을 내면 화면에서 선택이 안 된다.
CATEGORIES = [
    "뷰티",
    "패션",
    "액세서리",
    "생활용품",
    "주방용품",
    "문구·취미",
    "캐릭터·굿즈",
    "디지털 액세서리",
    "반려동물용품",
    "식품",
    "기타",
]


async def fill(request: ProductFillRequest) -> ProductFillResponse:
    # TODO(강근우): gpt-4o vision + agents.schemas.ProductUnderstanding 으로 교체
    return ProductFillResponse(
        category=request.category or "",
        description=request.description or "",
        selling_points=request.selling_points or "",
        main_target=request.main_target or "",
        image_used=False,
    )
