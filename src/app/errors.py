"""서비스 예외.

[규칙] 프론트는 자연어 메시지가 아니라 ErrorCode 로 분기한다.
       새 실패 유형이 생기면 ErrorCode 에 먼저 추가하고 여기서 던진다.
"""

from __future__ import annotations

from app.contracts.v1.enums import ErrorCode


class ServiceError(Exception):
    """계약된 오류 코드를 가진 예외. 잡 결과·HTTP 응답에 그대로 실린다."""

    #: 하위 클래스가 기본 코드를 정한다.
    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    #: 재시도하면 달라질 수 있는 오류인지. Spring 이 재시도 판단에 쓴다.
    retryable: bool = False

    def __init__(
        self,
        detail: str = "",
        *,
        code: ErrorCode | None = None,
        retryable: bool | None = None,
    ) -> None:
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable
        self.detail = detail or self.code.value
        super().__init__(self.detail)

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.detail}"


class InvalidCommand(ServiceError):
    code = ErrorCode.INVALID_COMMAND_SCHEMA


class JobAlreadyRunning(ServiceError):
    code = ErrorCode.JOB_ALREADY_RUNNING


class JobNotFound(ServiceError):
    code = ErrorCode.JOB_NOT_FOUND


class JobCancelled(ServiceError):
    """취소 플래그를 본 노드가 던진다. 완료된 노드 결과는 보존한다."""

    code = ErrorCode.JOB_CANCELLED


class JobTimeout(ServiceError):
    code = ErrorCode.JOB_TIMEOUT


class LLMStructuredOutputFailed(ServiceError):
    code = ErrorCode.LLM_STRUCTURED_OUTPUT_FAILED


class LLMRateLimited(ServiceError):
    code = ErrorCode.LLM_RATE_LIMITED
    retryable = True


class ExternalApiUnavailable(ServiceError):
    code = ErrorCode.EXTERNAL_API_UNAVAILABLE
    retryable = True


class BudgetExceeded(ServiceError):
    code = ErrorCode.DAILY_BUDGET_EXCEEDED


class CustomsBlocked(ServiceError):
    """판매 불가 판정. 해당 국가 파이프라인만 종료하고 잡은 성공으로 끝난다."""

    code = ErrorCode.CUSTOMS_BLOCKED
