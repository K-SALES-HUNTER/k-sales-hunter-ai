"""Redis 기반 진행 이벤트 발행과 취소 플래그. (구현 예시)

키 프리픽스 규약 (Spring 과 공유하는 Redis)
    app:*            Spring 소유 (세션, 환율 캐시, rate limit)
    ai:*             Python 소유 (시장/LLM 캐시, 잡 락)
    job:{id}:events  공용 (진행 이벤트 채널)
    job:{id}:cancel  공용 (취소 플래그)

진행 이벤트는 유실 허용이다. 최종 결과는 절대 이 채널로 보내지 않는다.
"""

from __future__ import annotations

from datetime import UTC, datetime

import redis.asyncio as aioredis

from app.config import get_settings
from app.contracts.v1 import ProgressEvent, cancel_key_for, channel_for

_settings = get_settings()
_client: aioredis.Redis | None = None


def get_client() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(_settings.redis_url, decode_responses=True)
    return _client


class EventPublisher:
    """잡 하나당 하나씩 만든다. seq 를 단조 증가시킨다.

    Pub/Sub 은 순서 보장이 약하다. Spring 은 seq 가 역행하면 그 이벤트를 버린다.
    """

    def __init__(self, job_id: int, trace_id: str) -> None:
        self._job_id = job_id
        self._trace_id = trace_id
        self._seq = 0

    async def emit(self, **fields) -> None:  # noqa: ANN003
        event = ProgressEvent(
            job_id=self._job_id,
            trace_id=self._trace_id,
            seq=self._seq,
            occurred_at=datetime.now(UTC),
            **fields,
        )
        self._seq += 1
        await get_client().publish(
            channel_for(self._job_id),
            event.model_dump_json(by_alias=True, exclude_none=True),
        )


async def is_cancelled(job_id: int) -> bool:
    """노드 경계에서 호출한다.

    노드 '내부'에서 LLM 호출이 진행 중이면 막지 못한다.
    즉 취소 응답 지연은 최대 한 노드 실행 시간이다.
    """
    return bool(await get_client().exists(cancel_key_for(job_id)))


async def acquire_job_lock(job_id: int, ttl_sec: int = 900) -> bool:
    """같은 jobId 로 두 번 들어오는 것을 막는다."""
    return bool(await get_client().set(f"ai:joblock:{job_id}", "1", nx=True, ex=ttl_sec))


async def release_job_lock(job_id: int) -> None:
    await get_client().delete(f"ai:joblock:{job_id}")
