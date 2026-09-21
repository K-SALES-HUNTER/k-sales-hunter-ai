"""잡 상태 저장소 (ai.jobs).

콜백이 없으므로 여기가 유일한 진실이다. Spring 은 GET 으로 폴링해 가져간다.
프로세스가 죽어도 결과가 남아 있다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update

from app.contracts.v1 import (
    CountryProgress,
    ErrorCode,
    JobError,
    JobState,
    JobStatus,
    JobStep,
    JobType,
)
from app.errors import JobAlreadyRunning, JobNotFound
from app.infra.db import session
from app.infra.models import Job
from app.observability.logging import get_logger

log = get_logger(mod="job_store")


def _now() -> datetime:
    return datetime.now(UTC)


async def create(
    *,
    job_id: str,
    job_type: JobType,
    request: dict,
    trace_id: str = "",
    countries: list[str] | None = None,
) -> None:
    """같은 job_id 가 이미 진행 중이면 거부한다 (중복 실행 방지)."""
    async with session() as db:
        existing = await db.get(Job, job_id)
        if existing is not None:
            if not JobStatus(existing.status).is_terminal:
                raise JobAlreadyRunning(f"job {job_id} 는 이미 실행 중이다")
            await db.delete(existing)
            await db.flush()

        db.add(
            Job(
                job_id=job_id,
                job_type=job_type.value,
                status=JobStatus.QUEUED.value,
                step=None,
                progress=0.0,
                trace_id=trace_id,
                country_states={
                    code: {"status": "RUNNING", "step": None, "progress": 0.0}
                    for code in (countries or [])
                },
                request=request,
                result=None,
                llm_cost_usd=0.0,
                created_at=_now(),
            )
        )


async def patch(job_id: str, **fields: Any) -> None:
    """부분 갱신. 노드 경계마다 호출된다."""
    if not fields:
        return
    async with session() as db:
        await db.execute(update(Job).where(Job.job_id == job_id).values(**fields))


async def mark_running(job_id: str) -> None:
    await patch(job_id, status=JobStatus.RUNNING.value, started_at=_now())


async def finish(
    job_id: str,
    *,
    status: JobStatus,
    result: dict | None = None,
    error_code: ErrorCode | None = None,
    error_detail: str = "",
    cost_usd: float = 0.0,
) -> None:
    await patch(
        job_id,
        status=status.value,
        progress=1.0,
        result=result,
        error_code=error_code.value if error_code else None,
        error_detail=error_detail or None,
        llm_cost_usd=cost_usd,
        finished_at=_now(),
    )


async def request_cancel(job_id: str) -> bool:
    """취소 요청만 남긴다. 실제 중단은 다음 노드 경계에서 일어난다.

    노드 실행 중에는 즉시 멈추지 않는다. 프론트는 '취소 요청됨 -> 취소됨' 2단계로 표시한다.
    """
    async with session() as db:
        row = await db.get(Job, job_id)
        if row is None:
            raise JobNotFound(job_id)
        if JobStatus(row.status).is_terminal:
            return False
        row.status = JobStatus.CANCEL_REQUESTED.value
        return True


async def is_cancel_requested(job_id: str) -> bool:
    async with session() as db:
        status = await db.scalar(select(Job.status).where(Job.job_id == job_id))
    return status == JobStatus.CANCEL_REQUESTED.value


async def get(job_id: str) -> JobState:
    async with session() as db:
        row = await db.get(Job, job_id)
    if row is None:
        raise JobNotFound(job_id)
    return _to_state(row)


async def reap_interrupted() -> int:
    """기동 시 호출. 프로세스가 죽어 RUNNING 으로 남은 잡을 정리한다.

    체크포인트 재개는 하지 않는다. Spring 이 다시 요청하면 새로 돈다.
    """
    async with session() as db:
        result = await db.execute(
            update(Job)
            .where(Job.status.in_([JobStatus.RUNNING.value, JobStatus.QUEUED.value]))
            .values(
                status=JobStatus.FAILED.value,
                error_code=ErrorCode.JOB_INTERRUPTED.value,
                error_detail="서버 재시작으로 중단됨",
                finished_at=_now(),
            )
        )
    count = result.rowcount or 0
    if count:
        log.warning("중단된 잡 정리", count=count)
    return count


def _to_state(row: Job) -> JobState:
    countries = {
        code: CountryProgress(
            status=value.get("status", "RUNNING"),
            step=JobStep(value["step"]) if value.get("step") else None,
            progress=value.get("progress", 0.0),
        )
        for code, value in (row.country_states or {}).items()
    }
    error = (
        JobError(code=ErrorCode(row.error_code), detail=row.error_detail or "")
        if row.error_code
        else None
    )
    return JobState(
        job_id=row.job_id,
        job_type=JobType(row.job_type),
        status=JobStatus(row.status),
        step=JobStep(row.step) if row.step else None,
        progress=row.progress,
        countries=countries,
        result=row.result,
        error=error,
        created_at=row.created_at.isoformat() if row.created_at else None,
        finished_at=row.finished_at.isoformat() if row.finished_at else None,
    )
