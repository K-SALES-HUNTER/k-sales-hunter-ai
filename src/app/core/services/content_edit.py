"""상세페이지 텍스트 수정 반영 — 재번역 (요구사항 F-25, 화면 DTL-01-01 편집 패널).

셀러가 한국어 상품명·상세 설명을 고치고 저장하면 현지어본에도 반영한다.
PATCH .../detail-page/content {name, description, retranslate: true} 에서 부른다.

사람이 고친 값이 우선이다. 한국어본은 셀러 입력을 그대로 저장하고(AI 가 다듬지 않는다)
현지어본만 gpt-4o-mini 로 다시 옮긴다. 이후 재생성해도 셀러 수정값을 덮어쓰지 않는 것은
Spring/dev_bff 가 저장 시 'edited' 표시로 지킨다.

담당: 강근우 (콘텐츠 아키텍트 R-003)
"""

from __future__ import annotations

import json

from app.core.agents import prompts
from app.core.agents.schemas import TranslatedText
from app.core.content import culture
from app.infra.llm import Model, complete_json


async def retranslate(
    *,
    country: str,
    locale: str,
    name: str,
    description: str,
    previous_name: str = "",
    previous_description: str = "",
) -> TranslatedText:
    rules = culture.load(country)
    payload = {
        "target": {"locale": locale, "guidelines": list(rules.guidelines)},
        "ko": {"name": name, "description": description},
        "previous": {"name": previous_name, "description": previous_description},
    }
    prompt = prompts.load("content_retranslate")
    result = await complete_json(
        schema=TranslatedText,
        system=prompt.body,
        user=json.dumps(payload, ensure_ascii=False, indent=2),
        model=Model.LIGHT,
        prompt_version=prompt.version,
        node="CONTENT_RETRANSLATE",
    )
    return TranslatedText(
        name=culture.sanitize(rules, result.name),
        description=culture.sanitize(rules, result.description),
    )
