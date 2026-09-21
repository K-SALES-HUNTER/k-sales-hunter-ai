"""LLM 호출 래퍼 — 모든 LLM 호출은 여기를 거친다.

여기서 한 번에 처리하는 것:
    구조화 출력 강제 / 파싱 실패 재시도 / rate limit 백오프 / 응답 캐시 /
    llm_call_logs 기록 / 일일 토큰 예산 / FakeLLM 대체

사용법:
    from app.core.agents.schemas import MarketAxes
    from app.infra.llm import complete_json

    axes = await complete_json(
        schema=MarketAxes,
        system=load_prompt("market_axes"),
        user=f"상품: {product}\\n수집 데이터: {data}",
        model=Model.LIGHT,
        prompt_version="market_axes.v1",
        node="MARKET_EVALUATE",
    )

[철칙] core/pricing 에서는 이 모듈을 import 하지 않는다. 숫자는 코드가 계산한다.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ValidationError

from app.config import ROOT_DIR, get_settings
from app.errors import (
    BudgetExceeded,
    ExternalApiUnavailable,
    LLMRateLimited,
    LLMStructuredOutputFailed,
)
from app.observability.logging import get_logger

log = get_logger(mod="llm")

#: 구조화 출력 파싱 실패 시 오류를 프롬프트에 넣어 다시 시도하는 횟수
MAX_PARSE_RETRY = 2
#: FakeLLM 응답을 찾는 곳. {스키마이름}.json
FIXTURE_DIR = ROOT_DIR / "tests" / "fixtures" / "llm"


class Model(StrEnum):
    """용도로 고른다. 실제 모델명은 설정에서 온다."""

    #: Vision 상품 이해, 콘텐츠 생성, 시장 해설, 종합 결론
    MAIN = "MAIN"
    #: 의도 분류, Critic, 요약, 번역
    LIGHT = "LIGHT"


#: 1M 토큰당 USD. 비용 추적과 예산 차단에 쓴다.
_PRICE_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "text-embedding-3-small": (0.02, 0.0),
}


def _resolve_model(model: Model | str) -> str:
    settings = get_settings()
    if model == Model.MAIN:
        return settings.openai_model_main
    if model == Model.LIGHT:
        return settings.openai_model_light
    return str(model)


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    in_price, out_price = _PRICE_PER_1M.get(model, (0.0, 0.0))
    return (input_tokens * in_price + output_tokens * out_price) / 1_000_000


# ── OpenAI strict json_schema 변환 ──────────────────────────────────────


def _strictify(node: Any) -> Any:
    """Pydantic JSON Schema 를 OpenAI strict 모드가 받는 형태로 바꾼다.

    strict 모드 요구사항:
      - 모든 object 에 additionalProperties: false
      - properties 의 모든 키가 required 에 있어야 한다 (Optional 은 anyOf [T, null] 로)
    """
    if isinstance(node, list):
        return [_strictify(item) for item in node]
    if not isinstance(node, dict):
        return node

    result = {key: _strictify(value) for key, value in node.items()}
    if result.get("type") == "object" or "properties" in result:
        result["additionalProperties"] = False
        props = result.get("properties") or {}
        result["required"] = list(props.keys())
    #: strict 모드가 거부하는 키워드는 떼어낸다 (값 검증은 Pydantic 이 다시 한다)
    for unsupported in ("default", "minimum", "maximum", "minItems", "maxItems", "format"):
        result.pop(unsupported, None)
    return result


def build_json_schema(schema: type[BaseModel]) -> dict:
    raw = schema.model_json_schema()
    return {
        "name": schema.__name__,
        "strict": True,
        "schema": _strictify(raw),
    }


# ── FakeLLM ─────────────────────────────────────────────────────────────


def _placeholder(annotation: Any) -> Any:
    origin = getattr(annotation, "__origin__", None)
    if origin in (list, set, tuple):
        return []
    if origin is dict:
        return {}
    if annotation is int:
        return 0
    if annotation is float:
        return 0.0
    if annotation is bool:
        return False
    return ""


def fake_instance[T: BaseModel](schema: type[T]) -> T:
    """fixture 가 있으면 그걸 쓰고, 없으면 타입에 맞는 빈 값으로 채운다.

    fixture 를 추가하면 그 즉시 결정론 응답이 된다.
    tests/fixtures/llm/{스키마이름}.json
    """
    fixture = FIXTURE_DIR / f"{schema.__name__}.json"
    if fixture.exists():
        return schema.model_validate_json(fixture.read_text(encoding="utf-8"))

    values: dict[str, Any] = {}
    for name, field in schema.model_fields.items():
        if not field.is_required():
            continue
        values[name] = _placeholder(field.annotation)
    return schema.model_validate(values)


# ── 캐시 / 예산 (Redis, 없으면 조용히 넘어간다) ─────────────────────────


async def _redis():  # noqa: ANN202
    try:
        import redis.asyncio as aioredis

        return aioredis.from_url(get_settings().redis_url, decode_responses=True)
    except Exception:  # pragma: no cover - 로컬에 Redis 가 없어도 동작해야 한다
        return None


def _cache_key(model: str, prompt_version: str, system: str, user: Any, name: str) -> str:
    raw = json.dumps([model, prompt_version, system, str(user), name], ensure_ascii=False)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    #: prompt_version 을 키에 넣는다. 안 넣으면 프롬프트를 고쳐도 옛 응답이 나온다.
    return f"ai:llm:{prompt_version}:{digest}"


async def _check_budget(tokens: int) -> None:
    settings = get_settings()
    client = await _redis()
    if client is None:
        return
    key = f"ai:budget:{datetime.now(UTC):%Y%m%d}"
    try:
        used = await client.incrby(key, tokens)
        await client.expire(key, 60 * 60 * 30)
        if used > settings.daily_token_budget:
            raise BudgetExceeded(f"오늘 토큰 {used} > 상한 {settings.daily_token_budget}")
    finally:
        await client.aclose()


# ── 본체 ────────────────────────────────────────────────────────────────


def _content(user: str | list[dict]) -> Any:
    return user if isinstance(user, list) else [{"type": "text", "text": user}]


def image_part(url_or_path: str) -> dict:
    """Vision 입력 한 조각. 로컬 파일이면 base64 로 감싼다."""
    if url_or_path.startswith(("http://", "https://", "data:")):
        return {"type": "image_url", "image_url": {"url": url_or_path}}
    with open(url_or_path, "rb") as file:
        raw = base64.b64encode(file.read()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{raw}"}}


async def complete_json[T: BaseModel](
    *,
    schema: type[T],
    system: str,
    user: str | list[dict],
    model: Model | str = Model.LIGHT,
    prompt_version: str = "unversioned",
    node: str | None = None,
    job_id: str | None = None,
    trace_id: str = "",
    temperature: float = 0.0,
    cache_ttl: int | None = 86400,
) -> T:
    """구조화 출력 1회. 반환 타입은 넘긴 schema 그대로다."""
    settings = get_settings()
    model_name = _resolve_model(model)

    if settings.use_fake_llm:
        log.debug("fake llm", schema=schema.__name__, node=node)
        return fake_instance(schema)

    key = _cache_key(model_name, prompt_version, system, user, schema.__name__)
    client = await _redis() if cache_ttl else None
    if client is not None:
        try:
            cached = await client.get(key)
            if cached:
                await client.aclose()
                return schema.model_validate_json(cached)
        except Exception:
            pass

    from openai import APIStatusError, AsyncOpenAI, RateLimitError

    openai = AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.llm_timeout_sec)
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": _content(user)},
    ]

    started = time.perf_counter()
    last_error = ""
    for attempt in range(MAX_PARSE_RETRY + 1):
        try:
            response = await openai.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                response_format={
                    "type": "json_schema",
                    "json_schema": build_json_schema(schema),
                },
            )
        except RateLimitError as exc:
            await _log_call(
                model_name,
                prompt_version,
                node,
                job_id,
                trace_id,
                0,
                0,
                started,
                False,
                "LLM_RATE_LIMITED",
            )
            raise LLMRateLimited(str(exc)) from exc
        except APIStatusError as exc:
            await _log_call(
                model_name,
                prompt_version,
                node,
                job_id,
                trace_id,
                0,
                0,
                started,
                False,
                "EXTERNAL_API_UNAVAILABLE",
            )
            raise ExternalApiUnavailable(str(exc)) from exc

        usage = response.usage
        in_tok = usage.prompt_tokens if usage else 0
        out_tok = usage.completion_tokens if usage else 0
        text = response.choices[0].message.content or ""

        try:
            parsed = schema.model_validate_json(text)
        except ValidationError as exc:
            last_error = str(exc)[:800]
            log.warning("structured output 검증 실패", attempt=attempt, node=node)
            #: 지적 사항을 대화에 넣어 다시 시도한다
            messages.append({"role": "assistant", "content": text})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "스키마 검증에 실패했다. 아래 오류를 고쳐 다시 출력하라.\n" + last_error
                    ),
                }
            )
            continue

        await _log_call(
            model_name,
            prompt_version,
            node,
            job_id,
            trace_id,
            in_tok,
            out_tok,
            started,
            True,
            None,
        )
        await _check_budget(in_tok + out_tok)

        if client is not None:
            try:
                await client.set(key, parsed.model_dump_json(), ex=cache_ttl)
                await client.aclose()
            except Exception:
                pass
        return parsed

    await _log_call(
        model_name,
        prompt_version,
        node,
        job_id,
        trace_id,
        0,
        0,
        started,
        False,
        "LLM_STRUCTURED_OUTPUT_FAILED",
    )
    raise LLMStructuredOutputFailed(last_error)


async def embed(texts: list[str], *, job_id: str | None = None) -> list[list[float]]:
    """RAG 적재·검색용 임베딩. 1536차원."""
    settings = get_settings()
    if settings.use_fake_llm:
        return [[0.0] * 1536 for _ in texts]

    from openai import AsyncOpenAI

    openai = AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.llm_timeout_sec)
    started = time.perf_counter()
    response = await openai.embeddings.create(model=settings.openai_embed_model, input=texts)
    await _log_call(
        settings.openai_embed_model,
        "embed",
        "RAG_INGEST",
        job_id,
        "",
        response.usage.prompt_tokens if response.usage else 0,
        0,
        started,
        True,
        None,
    )
    return [item.embedding for item in response.data]


async def _log_call(
    model: str,
    prompt_version: str,
    node: str | None,
    job_id: str | None,
    trace_id: str,
    input_tokens: int,
    output_tokens: int,
    started: float,
    success: bool,
    error_code: str | None,
) -> None:
    """llm_call_logs 기록. 1주차부터 남긴다 — 나중에 소급이 안 된다.

    비용 관리, 논문 정량 데이터, 알고리즘 명세서 근거, 프롬프트 A/B 에 전부 쓰인다.
    DB 가 없어도 본 흐름이 죽지 않도록 실패는 삼킨다.
    """
    latency_ms = int((time.perf_counter() - started) * 1000)
    cost = estimate_cost_usd(model, input_tokens, output_tokens)
    try:
        from app.infra.db import session
        from app.infra.models import LLMCallLog

        async with session() as db:
            db.add(
                LLMCallLog(
                    trace_id=trace_id,
                    job_id=job_id,
                    node=node,
                    provider="openai",
                    model=model,
                    prompt_version=prompt_version,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost,
                    latency_ms=latency_ms,
                    success=success,
                    error_code=error_code,
                    created_at=datetime.now(UTC),
                )
            )
    except Exception as exc:  # pragma: no cover
        log.debug("llm_call_logs 기록 실패", error=str(exc))
