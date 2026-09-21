"""잡 등록·폴링 계약.

콜백은 쓰지 않는다. Spring 이 GET 으로 상태를 가져가고, 결과는 ai.jobs 에 남아 있다.
"""

from __future__ import annotations

from pydantic import Field

from app.contracts.v1.base import SCHEMA_VERSION, CamelModel
from app.contracts.v1.enums import (
    CountryStatus,
    ErrorCode,
    JobStatus,
    JobStep,
    JobType,
)


class JobAccepted(CamelModel):
    """POST /internal/ai/*-jobs 응답 (202)."""

    schema_version: str = SCHEMA_VERSION
    job_id: str
    job_type: JobType
    status: JobStatus = JobStatus.QUEUED


class CountryProgress(CamelModel):
    status: CountryStatus = CountryStatus.RUNNING
    step: JobStep | None = None
    progress: float = 0.0


class JobError(CamelModel):
    code: ErrorCode
    detail: str = ""


class JobState(CamelModel):
    """GET /internal/ai/*-jobs/{jobId} 응답.

    프론트 로딩 오버레이는 step 으로 단계를 그리고 progress 로 막대를 채운다.
    """

    schema_version: str = SCHEMA_VERSION
    job_id: str
    job_type: JobType
    status: JobStatus
    step: JobStep | None = None
    progress: float = 0.0
    #: 국가 코드 -> 진행 상태. 분석 잡에서만 채워진다.
    countries: dict[str, CountryProgress] = Field(default_factory=dict)
    #: 남은 예상 시간. 노드별 평균 소요로 계산한 어림값.
    eta_seconds: int | None = None
    #: status 가 COMPLETED 일 때만 채워진다.
    result: dict | None = None
    error: JobError | None = None
    created_at: str | None = None
    finished_at: str | None = None
