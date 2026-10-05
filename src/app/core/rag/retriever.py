"""정책 문서 검색 (R-004-03 / R-004-08) — pgvector.

국가로 먼저 거르고, VERIFIED 문서만 코사인 거리 순으로 top-k 를 돌려준다.
근거 없는 판정을 막기 위해 출처·기준일을 같이 돌려준다.

코파일럿 search_policy 도구와 통관 게이트가 같은 함수를 쓴다.
담당: 권수현 (크로스보더 통관 R-004) · 코파일럿 연동 이동건
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from app.infra.db import session
from app.infra.llm import embed
from app.infra.models import RagDocument


@dataclass(frozen=True)
class PolicyHit:
    content_ko: str
    publisher: str
    source_url: str
    effective_from: str


async def search(*, country: str, query: str, top_k: int = 3) -> list[PolicyHit]:
    """질문을 임베딩해 같은 국가의 검수 완료(VERIFIED) 문서 중 가장 가까운 top_k 를 돌려준다.

    DRAFT 문서는 판정 근거로 쓰지 않는다. 근거가 0건이면 빈 리스트를 돌려주고,
    호출하는 쪽(코파일럿·통관 게이트)이 '확인 필요'로 답한다. 판매 가능으로 추정하지 않는다.
    """
    [vector] = await embed([query])
    stmt = (
        select(RagDocument)
        .where(RagDocument.country == country, RagDocument.review_status == "VERIFIED")
        .order_by(RagDocument.embedding.cosine_distance(vector))
        .limit(top_k)
    )
    async with session() as db:
        rows = (await db.scalars(stmt)).all()
    return [
        PolicyHit(
            content_ko=row.content_ko,
            publisher=row.publisher or "",
            source_url=row.source_url,
            effective_from=row.effective_from.isoformat(),
        )
        for row in rows
    ]
