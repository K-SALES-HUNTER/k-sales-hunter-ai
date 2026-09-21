"""구조화 로깅.

[규칙] 모든 로그에 trace_id 와 job_id 를 실어 나른다.
       trace_id 는 Spring 이 만들어 command 에 실어 보내고 Python 은 그대로 전달한다.

사용법:
    log = get_logger(job_id="a_12_1", node="MARGIN")
    log.info("margin calculated", margin_rate=0.249)
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.config import get_settings

_configured = False


def configure_logging() -> None:
    """앱 기동 시 1회. 로컬은 사람이 읽는 형식, 그 외는 JSON."""
    global _configured
    if _configured:
        return

    settings = get_settings()
    is_local = settings.app_env == "local"

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )

    renderer = (
        structlog.dev.ConsoleRenderer(colors=True)
        if is_local
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(**bound: Any) -> structlog.stdlib.BoundLogger:
    configure_logging()
    return structlog.get_logger().bind(**bound)


def bind_job(job_id: str, trace_id: str = "") -> None:
    """잡 실행 전체에 식별자를 건다. 이후 모든 로그에 자동으로 붙는다."""
    configure_logging()
    structlog.contextvars.bind_contextvars(job_id=job_id, trace_id=trace_id)


def clear_job() -> None:
    structlog.contextvars.clear_contextvars()
