"""FastAPI 앱 — Spring 이 호출하는 내부 API.

    POST /internal/ai/analysis-jobs          분석 잡 등록 (202 즉시)
    GET  /internal/ai/analysis-jobs/{id}     폴링
    POST /internal/ai/analysis-jobs/{id}/cancel
    POST /internal/ai/content-jobs           상세페이지 생성 잡
    POST /internal/ai/image-jobs             이미지 생성 잡
    POST /internal/ai/product-fill           상품 등록 자동 채우기 (동기)
    POST /internal/ai/pricing/quote          마진 재계산 (동기, LLM 없음)
    POST /internal/ai/sales-info/suggest     판매 정보 추천 (동기)
    POST /internal/ai/copilot/messages       AI 패널 (동기)
    GET  /internal/ai/health

인증은 공유 시크릿 헤더 X-Internal-Token + 네트워크 격리다. mTLS 는 과하다.

Swagger: http://localhost:8000/docs  (백엔드가 계약을 눈으로 확인하는 용도)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.contracts.v1 import (
    AnalysisCommand,
    ContentCommand,
    CopilotRequest,
    CopilotResponse,
    ImageCommand,
    JobAccepted,
    JobState,
    JobType,
    ProductFillRequest,
    ProductFillResponse,
    QuoteRequest,
    QuoteResponse,
    SalesSuggestRequest,
    SalesSuggestResponse,
)
from app.core.jobs import runner, store
from app.core.services import copilot, pricing_quote, product_fill, sales_suggest
from app.errors import ServiceError
from app.observability.logging import configure_logging, get_logger

log = get_logger(mod="http")


async def verify_token(x_internal_token: str = Header(default="")) -> None:
    """Spring 과 공유하는 시크릿. 로컬 기본값이면 검사를 건너뛴다."""
    settings = get_settings()
    if settings.app_env == "local" and settings.internal_token == "dev-internal-token":
        return
    if x_internal_token != settings.internal_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


internal = APIRouter(prefix="/internal/ai", tags=["internal"], dependencies=[Depends(verify_token)])


# ── 잡 ──────────────────────────────────────────────────────────────────


@internal.post("/analysis-jobs", status_code=202, response_model=JobAccepted)
async def create_analysis_job(command: AnalysisCommand) -> JobAccepted:
    await runner.submit_analysis(command)
    return JobAccepted(job_id=command.job_id, job_type=JobType.ANALYSIS)


@internal.post("/content-jobs", status_code=202, response_model=JobAccepted)
async def create_content_job(command: ContentCommand) -> JobAccepted:
    await runner.submit_content(command)
    return JobAccepted(job_id=command.job_id, job_type=JobType.CONTENT)


@internal.post("/image-jobs", status_code=202, response_model=JobAccepted)
async def create_image_job(command: ImageCommand) -> JobAccepted:
    await runner.submit_image(command)
    return JobAccepted(job_id=command.job_id, job_type=JobType.IMAGE)


@internal.get("/jobs/{job_id}", response_model=JobState)
@internal.get("/analysis-jobs/{job_id}", response_model=JobState)
@internal.get("/content-jobs/{job_id}", response_model=JobState)
@internal.get("/image-jobs/{job_id}", response_model=JobState)
async def get_job(job_id: str) -> JobState:
    return await store.get(job_id)


@internal.post("/jobs/{job_id}/cancel", status_code=204)
@internal.post("/analysis-jobs/{job_id}/cancel", status_code=204)
@internal.post("/content-jobs/{job_id}/cancel", status_code=204)
@internal.post("/image-jobs/{job_id}/cancel", status_code=204)
async def cancel_job(job_id: str) -> None:
    await runner.cancel(job_id)


# ── 동기 서비스 ─────────────────────────────────────────────────────────


@internal.post("/product-fill", response_model=ProductFillResponse)
async def post_product_fill(request: ProductFillRequest) -> ProductFillResponse:
    return await product_fill.fill(request)


@internal.post("/pricing/quote", response_model=QuoteResponse)
async def post_quote(request: QuoteRequest) -> QuoteResponse:
    return await pricing_quote.quote(request)


@internal.post("/sales-info/suggest", response_model=SalesSuggestResponse)
async def post_sales_suggest(request: SalesSuggestRequest) -> SalesSuggestResponse:
    return await sales_suggest.suggest(request)


@internal.post("/copilot/messages", response_model=CopilotResponse)
async def post_copilot(request: CopilotRequest) -> CopilotResponse:
    return await copilot.answer(request)


@internal.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "env": settings.app_env,
        "llm": "fake" if settings.use_fake_llm else settings.openai_model_main,
        "marketProvider": settings.market_provider,
    }


# ── 앱 ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    try:
        reaped = await store.reap_interrupted()
        log.info("기동", reaped_jobs=reaped)
    except Exception as exc:  # noqa: BLE001
        #: DB 가 아직 안 떠 있어도 서버는 뜨게 한다. /docs 로 계약은 볼 수 있어야 한다.
        log.warning("기동 시 DB 접근 실패", error=str(exc))
    yield
    from app.infra.db import dispose_engine

    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="K-Sales Hunter AI",
        version="0.1.0",
        description="Spring 이 호출하는 AI 내부 API. 계약은 docs/API_SPEC_FE기준.md.",
        lifespan=lifespan,
    )

    @app.exception_handler(ServiceError)
    async def handle_service_error(_, exc: ServiceError) -> JSONResponse:  # noqa: ANN001
        """프론트는 자연어가 아니라 code 로 분기한다."""
        http_status = {
            "JOB_NOT_FOUND": 404,
            "JOB_ALREADY_RUNNING": 409,
            "INVALID_COMMAND_SCHEMA": 400,
            "DAILY_BUDGET_EXCEEDED": 429,
            "LLM_RATE_LIMITED": 429,
        }.get(exc.code.value, 500)
        return JSONResponse(
            status_code=http_status,
            content={"code": exc.code.value, "detail": exc.detail, "retryable": exc.retryable},
        )

    app.include_router(internal)

    #: Spring 이 완성되기 전까지 프론트가 붙을 임시 백엔드
    if settings.dev_bff_enabled:
        from app.entrypoints.dev_bff import router as dev_router

        app.include_router(dev_router)
        log.info("dev_bff 활성화됨 — 프론트는 /api/v1 로 붙는다")

    return app


app = create_app()
