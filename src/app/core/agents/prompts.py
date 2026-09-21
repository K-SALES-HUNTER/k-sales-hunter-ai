"""프롬프트 로더.

프롬프트는 .md 파일로 둔다. 코드 문자열로 박으면 diff 가 안 읽히고 버전 추적이 안 된다.

파일 형식 (core/agents/prompts/*.md)
    <!-- version: market_axes.v3 -->
    당신은 동남아 이커머스 시장분석가입니다.
    ...

첫 줄의 version 을 파싱해 LLM 호출의 prompt_version 으로 쓴다.
캐시 키에 prompt_version 이 들어가므로, 프롬프트를 고치면 version 도 반드시 올린다.
안 올리면 프롬프트를 고쳤는데 옛날 응답이 계속 나온다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).parent / "prompts"
_VERSION_RE = re.compile(r"<!--\s*version:\s*(?P<version>[\w.\-]+)\s*-->")


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    body: str

    def format(self, **values: object) -> str:
        return self.body.format(**values)


@lru_cache
def load(name: str) -> Prompt:
    path = PROMPT_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"프롬프트 파일이 없다: {path}")

    raw = path.read_text(encoding="utf-8")
    match = _VERSION_RE.search(raw)
    version = match.group("version") if match else f"{name}.v0"
    body = _VERSION_RE.sub("", raw, count=1).strip()
    return Prompt(name=name, version=version, body=body)


def all_prompts() -> list[Prompt]:
    """기동 시 prompt_versions 테이블에 upsert 하려고 전부 읽는다."""
    if not PROMPT_DIR.exists():
        return []
    return [load(path.stem) for path in sorted(PROMPT_DIR.glob("*.md"))]
