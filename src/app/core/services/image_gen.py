"""상품·상세 이미지 AI 생성 (화면 DTL-01-02).

1회 요청에 1장. 20~40초 걸려 잡으로 돌리고 프론트가 폴링한다.

입력
    참고 사진      사용자가 고른 보유 상품 사진 + 업로드한 레퍼런스
    생성 방식      기본 컷 / 모델 컷 (모델 컷은 기본 모델 4종 중 선택)
    요청 내용      자연어 한 문장

흐름
    1. 프롬프트 조립: 대상 스타일 + 생성 방식 + (모델 페르소나) + 가드레일 + 사용자 요청
       (data/models.yaml)
    2. 같은 요청을 이미 만든 적이 있으면 그 파일을 그대로 준다 (리허설·재시연용 캐시)
    3. 일일 상한(DAILY_IMAGE_BUDGET) 확인
    4. 참고 사진이 있으면 images.edit(gpt-image-1, 다중 입력), 없으면 images.generate. 1024x1024
    5. uploads/ 에 PNG 로 저장하고 URL 을 돌려준다

FakeLLM 모드(키 없음)에서는 API 를 부르지 않고 첫 참고 사진을 결과로 복사한다.
화면 흐름은 그대로 돌고 비용은 0 이다.

비용은 장당 $0.05~0.2. 상한을 넘으면 DAILY_BUDGET_EXCEEDED 로 실패한다.

담당: 강근우 (콘텐츠 아키텍트 R-003)
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import httpx
import yaml

from app.config import DATA_DIR, get_settings
from app.contracts.v1 import ErrorCode, ImageCommand, ImageMode, ImageResult, JobStep
from app.core.graph.runtime import current_job
from app.errors import BudgetExceeded, ExternalApiUnavailable, ServiceError
from app.observability.logging import get_logger

log = get_logger(mod="image_gen")

#: 참고 사진 최대 장수. 많을수록 느리고 비싸다.
MAX_REFERENCES = 4
IMAGE_SIZE = "1024x1024"
#: dev_bff 가 서빙하는 업로드 경로. 이 접두사면 로컬 파일로 읽는다.
UPLOAD_URL_PREFIX = "/api/v1/uploads/"

#: Redis 가 없을 때 쓰는 프로세스 내 일일 카운터
_local_budget: dict[str, int] = {}


@lru_cache
def _catalog() -> dict:
    return yaml.safe_load((DATA_DIR / "models.yaml").read_text(encoding="utf-8")) or {}


def build_prompt(command: ImageCommand) -> str:
    """gpt-image-1 에 보낼 실제 프롬프트. 결과 화면에는 사용자 요청만 보인다."""
    catalog = _catalog()
    parts = [
        catalog["targets"][command.target.value],
        catalog["modes"][command.mode.value],
    ]
    if command.mode is ImageMode.MODEL:
        model = catalog["models"].get(command.model_id or "") or next(
            iter(catalog["models"].values())
        )
        parts.append(f"Model: {model['persona']}")
    parts.append(catalog["guardrails"])
    parts.append(f"Seller request (may be Korean): {command.prompt.strip()}")
    return "\n".join(part.strip() for part in parts)


def _cache_key(command: ImageCommand, prompt: str) -> str:
    raw = json.dumps(
        [
            _catalog().get("version"),
            #: fake 결과(참고 사진 복사)가 실제 생성 캐시로 쓰이지 않게 분리한다
            get_settings().use_fake_llm,
            prompt,
            sorted(command.reference_urls),
        ],
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _public_url(name: str) -> str:
    return f"{UPLOAD_URL_PREFIX}{name}"


async def _read_reference(url: str) -> tuple[str, bytes]:
    """참고 사진 하나를 바이트로. 로컬 업로드 · data URI · http(s) 를 받는다."""
    settings = get_settings()
    if url.startswith(UPLOAD_URL_PREFIX):
        name = Path(url[len(UPLOAD_URL_PREFIX) :]).name
        path = settings.upload_dir / name
        return name, path.read_bytes()
    if url.startswith("data:"):
        header, _, data = url.partition(",")
        suffix = "png" if "png" in header else "jpg"
        return f"reference.{suffix}", base64.b64decode(data)
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url)
        response.raise_for_status()
    return Path(url.split("?")[0]).name or "reference.png", response.content


async def _consume_budget() -> None:
    """오늘 생성 장수를 1 올린다. 상한을 넘으면 막는다."""
    settings = get_settings()
    key = f"ai:image_budget:{datetime.now(UTC):%Y%m%d}"
    used: int | None = None
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            used = await client.incr(key)
            await client.expire(key, 60 * 60 * 30)
        finally:
            await client.aclose()
    except Exception:  # noqa: BLE001 - Redis 가 없어도 상한은 지킨다
        _local_budget[key] = _local_budget.get(key, 0) + 1
        used = _local_budget[key]
    if used > settings.daily_image_budget:
        raise BudgetExceeded(f"오늘 이미지 {used}장 > 상한 {settings.daily_image_budget}장")


async def _call_openai(prompt: str, references: list[tuple[str, bytes]]) -> bytes:
    from openai import APIStatusError, AsyncOpenAI

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=120)
    try:
        if references:
            response = await client.images.edit(
                model=settings.openai_image_model,
                image=references,
                prompt=prompt,
                size=IMAGE_SIZE,
            )
        else:
            response = await client.images.generate(
                model=settings.openai_image_model, prompt=prompt, size=IMAGE_SIZE
            )
    except APIStatusError as exc:
        raise ExternalApiUnavailable(str(exc)) from exc
    return base64.b64decode(response.data[0].b64_json)


async def _step(progress: float) -> None:
    ctx = current_job.get()
    if ctx is not None:
        await ctx.ensure_not_cancelled()
        await ctx.report_step(JobStep.GENERATE, progress)


async def generate(command: ImageCommand) -> ImageResult:
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_prompt(command)
    name = f"gen_{_cache_key(command, prompt)}.png"
    target = settings.upload_dir / name

    def result(*, cached: bool) -> ImageResult:
        return ImageResult(
            job_id=command.job_id,
            image_url=_public_url(name),
            prompt=command.prompt,
            resolved_prompt=prompt,
            cached=cached,
        )

    await _step(0.1)
    if target.exists():
        log.info("이미지 캐시 사용", file=name)
        return result(cached=True)

    references = []
    for url in command.reference_urls[:MAX_REFERENCES]:
        try:
            references.append(await _read_reference(url))
        except Exception as exc:  # noqa: BLE001
            log.warning("참고 사진을 못 읽었다, 건너뜀", url=url, error=str(exc))

    if settings.use_fake_llm:
        if not references:
            raise ServiceError(
                "FakeLLM 모드는 참고 사진이 1장 이상 필요하다", code=ErrorCode.IMAGE_FETCH_FAILED
            )
        log.info("fake 이미지 생성 (첫 참고 사진 복사)")
        target.write_bytes(references[0][1])
        return result(cached=False)

    await _consume_budget()
    await _step(0.3)
    image = await _call_openai(prompt, references)
    #: 생성 중 취소됐으면 저장하지 않는다
    await _step(0.95)
    target.write_bytes(image)
    return result(cached=False)
