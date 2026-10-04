"""문화·표현 필터 사전 (R-003 culture_filter).

data/culture/common.yaml (한국어 공통) + data/culture/{cc}.yaml (현지어·국가 금기) 를 합쳐 쓴다.

하는 일은 두 가지뿐이다.
    find()     금지어·상표·과장 표현을 찾는다. 품질 검수가 감점과 하드 컷에 쓴다
    sanitize() replace 가 정해진 과장 표현만 바로 바꾼다. 나머지는 재생성 지시로 돌린다

LLM 을 부르지 않는다. 사전에 없는 미묘한 표현은 초안 프롬프트의 guidelines 로 막는다.

담당: 강근우 (콘텐츠 아키텍트 R-003)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import yaml

from app.config import DATA_DIR

#: 품질 검수 이슈 종류 (contracts.v1.QualityIssue.kind)
BANNED = "BANNED_WORD"
TRADEMARK = "TRADEMARK"
EXAGGERATION = "EXAGGERATION"

_SECTION_KIND = {"banned": BANNED, "trademark": TRADEMARK, "exaggeration": EXAGGERATION}


@dataclass(frozen=True)
class Term:
    term: str
    kind: str
    reason: str
    #: None 이면 자동 치환하지 않는다. "" 이면 지운다.
    replace: str | None
    pattern: re.Pattern[str]

    @property
    def hard_block(self) -> bool:
        return self.kind in (BANNED, TRADEMARK)


@dataclass(frozen=True)
class Hit:
    term: Term
    #: 걸린 필드. 예) name, usps[2], description
    field: str


@dataclass(frozen=True)
class CultureRules:
    country: str
    version: str
    terms: tuple[Term, ...]
    guidelines: tuple[str, ...]


def _compile(term: str) -> re.Pattern[str]:
    """영문은 단어 경계로, 나머지(한글·태국어·베트남어 구절)는 부분 문자열로 찾는다."""
    escaped = re.escape(term)
    if term.isascii():
        return re.compile(rf"(?<![A-Za-z]){escaped}(?![A-Za-z])", re.IGNORECASE)
    return re.compile(escaped, re.IGNORECASE)


def _read(name: str) -> dict:
    path = DATA_DIR / "culture" / f"{name}.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@lru_cache
def load(country: str) -> CultureRules:
    common, local = _read("common"), _read(country.upper())
    terms = []
    for raw in (common, local):
        for section, kind in _SECTION_KIND.items():
            for item in raw.get(section) or []:
                text = str(item["term"])
                terms.append(
                    Term(
                        term=text,
                        kind=kind,
                        reason=str(item.get("reason", "")),
                        replace=item.get("replace"),
                        pattern=_compile(text),
                    )
                )
    version = f"{common.get('version', 'common')}+{local.get('version', country.lower())}"
    return CultureRules(
        country=country.upper(),
        version=version,
        terms=tuple(terms),
        guidelines=tuple(local.get("guidelines") or []),
    )


def find(rules: CultureRules, fields: dict[str, str]) -> list[Hit]:
    """필드별로 걸린 표현을 모두 찾는다. 같은 필드·같은 표현은 한 번만."""
    hits = []
    for field, text in fields.items():
        if not text:
            continue
        for term in rules.terms:
            if term.pattern.search(text):
                hits.append(Hit(term=term, field=field))
    return hits


def sanitize(rules: CultureRules, text: str) -> str:
    """replace 가 정해진 표현만 바꾼다. 하드 컷 표현은 건드리지 않는다 (사람이 봐야 한다)."""
    for term in rules.terms:
        if term.replace is None or term.hard_block:
            continue
        text = term.pattern.sub(term.replace, text)
    #: 지워서 생긴 이중 공백 정리
    return re.sub(r"[ \t]{2,}", " ", text).strip()
