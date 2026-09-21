"""노드 공통 런타임 — 모든 노드는 @node 데코레이터를 단다.

데코레이터가 대신 해주는 것:
    1. 취소 요청 확인 (노드 경계에서만. 실행 중인 노드는 끝까지 간다)
    2. 잡 step / progress / 국가별 상태 갱신  -> 프론트 로딩 오버레이가 이걸 본다
    3. 노드 타임아웃
    4. 실패 시 해당 국가만 중단 (다른 국가는 계속 간다)
    5. completed_nodes 누적

노드가 지켜야 할 것:
    async def run(state: CountryState) -> dict   # 변경분만 반환한다

[철칙] 이 파일을 포함해 core/ 안에서는 FastAPI 를 import 하지 않는다.
       코어는 state 를 넣으면 state 가 나오는 순수 영역이어야 한다.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from typing import Any

from app.config import get_settings
from app.contracts.v1 import (
    COUNTRY_NODE_ORDER,
    NODE_STEP,
    CountryStatus,
    ErrorCode,
    JobStep,
    NodeName,
)
from app.errors import JobCancelled, ServiceError
from app.observability.logging import get_logger

log = get_logger(mod="runtime")

#: 국가 하나가 끝까지 가는 데 필요한 노드 수 (+1 은 report_compose 몫)
_TOTAL_STEPS = len(COUNTRY_NODE_ORDER) + 1


@dataclass
class JobContext:
    """실행 중인 잡 하나. 노드는 이걸 직접 받지 않고 contextvar 로 꺼내 쓴다."""

    job_id: str
    trace_id: str = ""
    countries: list[str] = field(default_factory=list)
    #: 국가별 완료 노드 수
    done: dict[str, int] = field(default_factory=dict)
    #: 국가별 상태
    status: dict[str, CountryStatus] = field(default_factory=dict)
    #: 잡 전체 step. 가장 느린 국가 기준.
    step: JobStep | None = None
    cost_usd: float = 0.0
    #: True 면 DB 를 쓰지 않는다 (로컬 스크립트·테스트)
    detached: bool = False

    def country_progress(self, country: str) -> float:
        return min(self.done.get(country, 0) / _TOTAL_STEPS, 1.0)

    @property
    def progress(self) -> float:
        if not self.countries:
            return 0.0
        total = sum(self.country_progress(code) for code in self.countries)
        return round(total / len(self.countries), 3)

    def _slowest_step(self) -> JobStep | None:
        """가장 덜 진행된 국가의 step. 프론트는 이 단계를 '진행 중'으로 그린다."""
        pending = [
            self.done.get(code, 0)
            for code in self.countries
            if self.status.get(code) in (None, CountryStatus.RUNNING)
        ]
        index = min(pending) if pending else _TOTAL_STEPS - 1
        index = min(index, len(COUNTRY_NODE_ORDER) - 1)
        return NODE_STEP[COUNTRY_NODE_ORDER[index]]

    async def flush(self) -> None:
        """DB 에 현재 상태를 쓴다. 노드 경계마다 호출된다."""
        if self.detached:
            return
        from app.core.jobs import store

        await store.patch(
            self.job_id,
            step=(self.step or self._slowest_step() or JobStep.GATE).value,
            progress=self.progress,
            country_states={
                code: {
                    "status": self.status.get(code, CountryStatus.RUNNING).value,
                    "step": (
                        NODE_STEP[
                            COUNTRY_NODE_ORDER[
                                min(self.done.get(code, 0), len(COUNTRY_NODE_ORDER) - 1)
                            ]
                        ]
                    ).value,
                    "progress": self.country_progress(code),
                }
                for code in self.countries
            },
        )

    async def ensure_not_cancelled(self) -> None:
        if self.detached:
            return
        from app.core.jobs import store

        if await store.is_cancel_requested(self.job_id):
            raise JobCancelled(f"job {self.job_id} 취소 요청됨")

    def mark_country(self, country: str, status: CountryStatus) -> None:
        self.status[country] = status


#: 노드가 실행 중인 잡. runner 가 set 하고 노드가 get 한다.
current_job: ContextVar[JobContext | None] = ContextVar("current_job", default=None)


def get_job_context() -> JobContext | None:
    return current_job.get()


NodeFn = Callable[[dict], Awaitable[dict | None]]


def node(name: NodeName) -> Callable[[NodeFn], NodeFn]:
    """노드 함수에 단다.

    예)
        @node(NodeName.MARGIN)
        async def run(state: CountryState) -> dict:
            ...
            return {"pricing": result}
    """

    def decorate(fn: NodeFn) -> NodeFn:
        @wraps(fn)
        async def wrapper(state: dict) -> dict:
            country = state.get("country", "")
            ctx = current_job.get()
            node_log = log.bind(node=name.value, country=country)

            #: 앞선 노드에서 중단된 국가는 남은 노드를 통과만 한다.
            if state.get("halted"):
                return {}

            if ctx is not None:
                await ctx.ensure_not_cancelled()

            settings = get_settings()
            try:
                patch = await asyncio.wait_for(fn(state), timeout=settings.node_timeout_sec)
            except JobCancelled:
                raise
            except TimeoutError:
                node_log.warning("노드 타임아웃")
                return _halt(ctx, country, name, ErrorCode.JOB_TIMEOUT, "노드 타임아웃")
            except ServiceError as exc:
                node_log.warning("노드 실패", code=exc.code.value, detail=exc.detail)
                return _halt(ctx, country, name, exc.code, exc.detail)
            except Exception as exc:  # noqa: BLE001
                node_log.exception("노드 예외")
                return _halt(ctx, country, name, ErrorCode.INTERNAL_ERROR, str(exc))

            if ctx is not None:
                ctx.done[country] = ctx.done.get(country, 0) + 1
                await ctx.flush()

            result: dict[str, Any] = dict(patch or {})
            #: 국가 파이프라인 노드만 누적한다. fan-in 노드(REPORT_COMPOSE)는
            #: 부모 state 를 받으므로 이 키가 없다.
            if country:
                result["completed_nodes"] = [name.value]
            return result

        return wrapper

    return decorate


def _halt(
    ctx: JobContext | None,
    country: str,
    name: NodeName,
    code: ErrorCode,
    detail: str,
) -> dict:
    """해당 국가만 중단시킨다. 잡 전체는 계속 간다."""
    if ctx is not None:
        ctx.mark_country(country, CountryStatus.FAILED)
    return {
        "halted": True,
        "failed_nodes": [name.value],
        "error": {"code": code.value, "detail": detail},
    }
