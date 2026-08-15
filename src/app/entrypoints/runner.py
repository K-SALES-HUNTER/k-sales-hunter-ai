"""긴 작업 실행기. (구현 예시)

기술결정서 2-1 결정:
    별도 워커 프로세스와 브로커 없이 asyncio.create_task + Semaphore 로 시작한다.
    프로세스가 재시작되면 실행 중 잡은 사라지지만, LangGraph checkpoint 가 남아 있어
    Spring 이 retry 를 걸면 완료 노드를 재사용하고 이어서 실행된다.

    부하가 문제되면 이 파일 옆에 worker.py 를 추가해 ARQ 로 옮긴다.
    core/ 가 엔트리포인트에서 격리되어 있으므로 교체 범위가 여기로 한정된다.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.config import get_settings
from app.contracts.v1 import AnalysisCommand, ErrorCode, JobStatus, NodeStatus
from app.errors import JobAlreadyRunning, JobCancelled, ServiceError
from app.infra import redis_bus, spring_client
from app.observability.logging import get_logger

_settings = get_settings()
_semaphore = asyncio.Semaphore(_settings.max_concurrent_jobs)
_running: dict[int, asyncio.Task] = {}


async def submit(command: AnalysisCommand) -> None:
    """잡을 백그라운드로 띄운다. 즉시 반환한다.

    같은 jobId 가 이미 실행 중이면 거부한다.
    """
    if not await redis_bus.acquire_job_lock(command.job_id):
        raise JobAlreadyRunning(f"job {command.job_id} is already running")

    task = asyncio.create_task(_run_guarded(command))
    _running[command.job_id] = task
    task.add_done_callback(lambda _: _running.pop(command.job_id, None))


async def _run_guarded(command: AnalysisCommand) -> None:
    """동시 실행 수를 제한하고, 어떤 경우에도 결과를 Spring 에 전달한다."""
    log = get_logger(job_id=command.job_id, trace_id=command.trace_id)
    publisher = redis_bus.EventPublisher(command.job_id, command.trace_id)
    started_at = datetime.now(UTC)

    async with _semaphore:
        try:
            await publisher.emit(job_status=JobStatus.RUNNING, progress=0.0)
            payload = await asyncio.wait_for(
                _execute(command, publisher),
                timeout=_settings.job_timeout_sec,
            )
            status = JobStatus.COMPLETED

        except JobCancelled:
            log.info("job cancelled")
            status = JobStatus.CANCELLED
            payload = _empty_payload(command, status, started_at)

        except TimeoutError:
            log.warning("job timeout")
            status = JobStatus.FAILED
            payload = _empty_payload(command, status, started_at, ErrorCode.JOB_TIMEOUT)

        except ServiceError as exc:
            log.warning("job failed", code=exc.code.value)
            status = JobStatus.FAILED
            payload = _empty_payload(command, status, started_at, exc.code)

        except Exception:
            log.exception("job crashed")
            status = JobStatus.FAILED
            payload = _empty_payload(command, status, started_at, ErrorCode.INTERNAL_ERROR)

        finally:
            await redis_bus.release_job_lock(command.job_id)

    await publisher.emit(job_status=status, progress=1.0)

    # 결과는 유실 불가. 콜백 실패 시 DB 에 보관하고 Spring 이 회수한다.
    delivered = await spring_client.deliver_result(
        command.job_id, command.command_id, payload, command.trace_id
    )
    if not delivered:
        await spring_client.stash_result(command.job_id, command.command_id, payload)


async def _execute(command: AnalysisCommand, publisher: redis_bus.EventPublisher) -> dict:
    """그래프를 실행하고 계약 스키마(AnalysisResult)로 변환해 반환한다."""
    raise NotImplementedError


def _empty_payload(
    command: AnalysisCommand,
    status: JobStatus,
    started_at: datetime,
    code: ErrorCode | None = None,
) -> dict:
    """결과를 못 만든 경우에도 Spring 이 상태를 확정할 수 있게 최소 페이로드를 만든다."""
    raise NotImplementedError


async def emit_node(
    publisher: redis_bus.EventPublisher,
    *,
    job_id: int,
    country: str,
    node: str,
    status: NodeStatus,
    progress: float,
) -> None:
    """노드 경계에서 호출한다. 취소 확인과 이벤트 발행을 함께 처리한다."""
    if await redis_bus.is_cancelled(job_id):
        raise JobCancelled()
    await publisher.emit(country=country, node=node, node_status=status, progress=progress)
