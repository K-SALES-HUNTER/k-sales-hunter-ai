"""잡 실행기.

별도 워커 프로세스와 메시지 브로커를 두지 않는다.
FastAPI 프로세스 안에서 asyncio.create_task + Semaphore 로 돌린다. 인프라 추가가 0이다.

    POST /internal/ai/analysis-jobs  ──▶ submit()  ──▶ 202 즉시 반환
                                              └─ 백그라운드 태스크
                                                   ai.jobs 에 step/progress 갱신
    GET  /internal/ai/analysis-jobs/{id} ──▶ store.get()  (프론트가 2초마다 폴링)

동시 실행 3개 제한은 LLM rate limit 보호용이다. 초과 요청은 대기한다.
부하가 문제되면 이 파일 옆에 worker.py 를 두고 ARQ 로 옮긴다. core/ 가 격리돼 있어
교체 범위가 여기로 한정된다.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.config import get_settings
from app.contracts.v1 import (
    AnalysisCommand,
    ContentCommand,
    CountryStatus,
    ErrorCode,
    ImageCommand,
    JobStatus,
    JobStep,
    JobType,
)
from app.core.graph.runtime import JobContext, current_job
from app.core.jobs import store
from app.errors import JobCancelled, ServiceError
from app.observability.logging import bind_job, clear_job, get_logger

log = get_logger(mod="runner")

_semaphore: asyncio.Semaphore | None = None
_running: dict[str, asyncio.Task] = {}


def _get_semaphore() -> asyncio.Semaphore:
    """이벤트 루프가 뜬 뒤에 만든다. 모듈 로드 시점에 만들면 루프가 어긋난다."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_settings().max_concurrent_jobs)
    return _semaphore


# ── 등록 ────────────────────────────────────────────────────────────────


async def submit_analysis(command: AnalysisCommand) -> None:
    await store.create(
        job_id=command.job_id,
        job_type=JobType.ANALYSIS,
        request=command.model_dump(by_alias=True, mode="json"),
        trace_id=command.trace_id,
        countries=command.countries,
    )
    _spawn(command.job_id, _run_analysis(command))


async def submit_content(command: ContentCommand) -> None:
    await store.create(
        job_id=command.job_id,
        job_type=JobType.CONTENT,
        request=command.model_dump(by_alias=True, mode="json"),
        trace_id=command.trace_id,
    )
    _spawn(command.job_id, _run_content(command))


async def submit_image(command: ImageCommand) -> None:
    await store.create(
        job_id=command.job_id,
        job_type=JobType.IMAGE,
        request=command.model_dump(by_alias=True, mode="json"),
        trace_id=command.trace_id,
    )
    _spawn(command.job_id, _run_image(command))


def _spawn(job_id: str, coro) -> None:  # noqa: ANN001
    task = asyncio.create_task(coro, name=f"job:{job_id}")
    _running[job_id] = task
    task.add_done_callback(lambda _: _running.pop(job_id, None))


async def cancel(job_id: str) -> bool:
    """취소 요청만 남긴다. 실행 중인 노드는 끝까지 간다.

    프론트에는 '취소 요청됨 -> 취소됨' 2단계로 보인다. 최대 한 노드 실행 시간만큼 지연된다.
    """
    return await store.request_cancel(job_id)


# ── 실행 ────────────────────────────────────────────────────────────────


async def _run_analysis(command: AnalysisCommand) -> None:
    from app.core.graph.analysis import build_analysis_graph

    ctx = JobContext(
        job_id=command.job_id,
        trace_id=command.trace_id,
        countries=list(command.countries),
    )

    async def execute() -> dict:
        graph = build_analysis_graph()
        state = await graph.ainvoke(
            {
                "meta": {"job_id": command.job_id, "trace_id": command.trace_id},
                "countries": command.countries,
                "product": command.product.model_dump(),
                "market_profile": (
                    command.market_profile.model_dump() if command.market_profile else None
                ),
                "preferences": command.preferences.model_dump(),
                "country_results": [],
                "previous_result": (command.partial.previous_result if command.partial else None),
                "changed_fields": (command.partial.changed_fields if command.partial else []),
            }
        )
        return _assemble_analysis(command.job_id, state)

    await _guard(command.job_id, ctx, execute, final_step=JobStep.REPORT)


async def _run_content(command: ContentCommand) -> None:
    ctx = JobContext(job_id=command.job_id, trace_id=command.trace_id)

    async def execute() -> dict:
        # TODO(강근우): content_graph 로 교체
        from app.contracts.v1 import ContentResult

        return ContentResult(job_id=command.job_id, locale=command.locale).model_dump(
            by_alias=True, mode="json"
        )

    await _guard(command.job_id, ctx, execute, final_step=JobStep.LOCALIZE)


async def _run_image(command: ImageCommand) -> None:
    ctx = JobContext(job_id=command.job_id, trace_id=command.trace_id)

    async def execute() -> dict:
        # TODO(강근우): image_gen 서비스로 교체
        from app.contracts.v1 import ImageResult

        return ImageResult(job_id=command.job_id, prompt=command.prompt).model_dump(
            by_alias=True, mode="json"
        )

    await _guard(command.job_id, ctx, execute, final_step=JobStep.GENERATE)


async def _guard(
    job_id: str,
    ctx: JobContext,
    execute,  # noqa: ANN001
    *,
    final_step: JobStep,
) -> None:
    """어떤 경우에도 잡을 종결 상태로 만든다. 상태가 RUNNING 으로 남으면 프론트가 영원히 돈다."""
    settings = get_settings()
    bind_job(job_id, ctx.trace_id)
    token = current_job.set(ctx)

    async with _get_semaphore():
        try:
            await store.mark_running(job_id)
            await ctx.flush()
            result = await asyncio.wait_for(execute(), timeout=settings.job_timeout_sec)
            await store.patch(job_id, step=final_step.value)
            await store.finish(
                job_id, status=JobStatus.COMPLETED, result=result, cost_usd=ctx.cost_usd
            )
            log.info("잡 완료")

        except JobCancelled:
            log.info("잡 취소됨")
            await store.finish(
                job_id, status=JobStatus.CANCELLED, error_code=ErrorCode.JOB_CANCELLED
            )
        except TimeoutError:
            log.warning("잡 타임아웃")
            await store.finish(job_id, status=JobStatus.FAILED, error_code=ErrorCode.JOB_TIMEOUT)
        except ServiceError as exc:
            log.warning("잡 실패", code=exc.code.value)
            await store.finish(
                job_id,
                status=JobStatus.FAILED,
                error_code=exc.code,
                error_detail=exc.detail,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("잡 예외")
            await store.finish(
                job_id,
                status=JobStatus.FAILED,
                error_code=ErrorCode.INTERNAL_ERROR,
                error_detail=str(exc),
            )
        finally:
            current_job.reset(token)
            clear_job()


# ── 결과 조립 ───────────────────────────────────────────────────────────


def _assemble_analysis(job_id: str, state: dict[str, Any]) -> dict:
    """그래프 state 를 계약 스키마(AnalysisResult)로 바꾼다.

    REPORT_COMPOSE 가 점수를 확정한 scored 목록이 있으면 그걸 쓴다.
    (원본 country_results 에는 진입점수·랭킹이 아직 없다)
    """
    from app.contracts.v1 import AnalysisResult

    global_result = dict(state.get("global_result") or {})
    countries = global_result.pop("scored", None) or list(state.get("country_results") or [])

    for item in countries:
        item.setdefault("status", CountryStatus.DONE.value)

    return AnalysisResult.model_validate(
        {
            "jobId": job_id,
            "global": global_result,
            "countries": countries,
        }
    ).model_dump(by_alias=True, mode="json")
