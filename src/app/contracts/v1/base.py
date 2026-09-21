"""계약 스키마 공통 베이스.

[규칙] Python 은 snake_case, JSON 은 camelCase 로 나간다.
       직렬화할 때 반드시 by_alias=True 를 쓴다. (model_dump(by_alias=True))
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(word.capitalize() for word in tail)


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,  # snake_case 로도 만들 수 있다
        use_enum_values=False,
    )


#: 모든 최상위 메시지에 실린다. 필드 추가는 자유, 삭제·이름변경은 PR 합의.
SCHEMA_VERSION = "1.0"
