"""dev_bff — Spring 이 완성되기 전까지 프론트가 붙는 임시 백엔드.

프론트는 .env 의 VITE_API_BASE_URL 만 http://localhost:8000/api/v1 로 바꾸면 된다.
Spring 이 뜨면 주소만 되돌린다. 경로와 응답 모양이 같아서 프론트 코드는 손대지 않는다.

[Spring 담당자에게] 이 파일이 곧 실행되는 API 명세다.
    컨트롤러를 만들 때 응답 JSON 을 그대로 맞추면 된다.
    특히 _to_total_report / _to_country_report 의 매핑 규칙을 옮겨야 한다.
    AI 는 숫자와 통화 코드만 주고, 표시용 문자열은 여기서 만든다.
    라우트별 담당은 docs/ONBOARDING.md §5 참조.

[한계] 저장은 메모리다. 서버를 재시작하면 등록한 상품이 사라진다.
       잡 상태와 결과만 ai.jobs 에 남는다. 임시 도구라 이 정도로 둔다.

담당: 이동건 (등록 -> 분석 폴링 -> 보고서) · 강근우 (판매 정보 · 상세페이지 · 이미지)
"""

from __future__ import annotations

import itertools
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.config import get_settings
from app.contracts.v1 import (
    COUNTRY_CURRENCY,
    COUNTRY_LOCALE,
    COUNTRY_NAMES,
    SUPPORTED_COUNTRIES,
    AnalysisCommand,
    AnalysisDigest,
    AnalysisPreferences,
    AnalysisResult,
    ContentCommand,
    ContentResult,
    CopilotRequest,
    CopilotResponse,
    CountryResult,
    CountryStatus,
    ImageCommand,
    ImageMode,
    ImageResult,
    ImageTarget,
    JobStatus,
    MarketProfile,
    OptionSpec,
    Packaging,
    PriceScenario,
    ProductFillRequest,
    ProductSnapshot,
    QuoteRequest,
    QuoteResponse,
    SalesInfoSnapshot,
    SalesSuggestRequest,
    SalesSuggestResponse,
    ShippingMethod,
)
from app.core.catalog import shopee_categories
from app.core.jobs import runner, store
from app.core.pricing import fee_schedule
from app.core.services import (
    content_edit,
    copilot,
    pricing_quote,
    product_fill,
    sales_suggest,
)
from app.observability.logging import get_logger

log = get_logger(mod="dev_bff")
router = APIRouter(prefix="/api/v1", tags=["dev_bff"])

# ── 메모리 저장소 ───────────────────────────────────────────────────────

_products: dict[int, dict] = {}
_jobs_by_product: dict[int, str] = {}
#: (productId, 국가) -> AI 추천값. 판매 정보 화면 첫 진입 때 한 번 만든다.
_sales_suggestions: dict[tuple[int, str], SalesSuggestResponse] = {}
#: (productId, 국가) -> 셀러가 확정한 판매 정보
_sales_infos: dict[tuple[int, str], dict] = {}
#: (productId, 국가) -> 상세페이지 생성 잡
_detail_jobs: dict[tuple[int, str], str] = {}
#: (productId, 국가) -> 완성된 상세페이지 (AI 결과 + 셀러 수정 + 이미지)
_detail_pages: dict[tuple[int, str], dict] = {}
_product_seq = itertools.count(1)
_job_seq = itertools.count(1)

#: 프론트 드롭다운 11종
CATEGORIES = [
    "뷰티",
    "패션",
    "액세서리",
    "생활용품",
    "주방용품",
    "문구·취미",
    "캐릭터·굿즈",
    "디지털 액세서리",
    "반려동물용품",
    "식품",
    "기타",
]

CURRENCY_SYMBOL = {"VN": "₫", "SG": "S$", "TH": "฿"}
GRADE_KO = {"HIGH": "높음", "MID": "보통", "LOW": "낮음"}
FIT_KO = {
    "VERY_FIT": "매우 적합",
    "PARTIAL_FIT": "일부 적합",
    "NORMAL": "보통",
    "CAUTION": "유의",
}
TIER_ID = {"LOW": "low", "MID": "mid", "HIGH": "high"}
TIER_LABEL = {"LOW": "Low", "MID": "추천 (Mid)", "HIGH": "High"}
METHOD_ID = {"DIRECT": "direct", "SLS": "sls"}
METHOD_NAME = {"DIRECT": "직접 배송", "SLS": "Shopee SLS"}
AXIS_LABEL = {
    "demand": "수요",
    "competition": "경쟁 강도",
    "k_fit": "K-트렌드 적합도",
    "profitability": "수익성",
}


def won(value: float | int) -> str:
    return f"₩{int(value):,}"


def local_price_text(country: str, amount: float) -> str:
    symbol = CURRENCY_SYMBOL.get(country, "")
    #: VND 는 소수점을 쓰지 않는다
    if country == "VN":
        return f"{symbol}{int(round(amount)):,}"
    return f"{symbol}{amount:,.2f}"


def signed(amount: int) -> str:
    return f"{'+' if amount >= 0 else '-'}₩{abs(int(amount)):,}"


# ── 요청 모델 ───────────────────────────────────────────────────────────


class LoginBody(BaseModel):
    email: str
    password: str = ""


class JoinBody(BaseModel):
    email: str
    marketName: str = ""
    password: str = ""
    businessNumber: str = ""


class ProductBody(BaseModel):
    name: str
    category: str = ""
    costPrice: int = 0
    weight: int = 0
    description: str = ""
    sellingPoints: str = ""
    mainTarget: str = ""
    imageUrls: list[str] = []


class OptionBody(BaseModel):
    name: str = ""
    label: str = ""
    values: list[str] = []


class StockRowBody(BaseModel):
    option1: str = ""
    option2: str = ""
    qty: int = 0
    extraPrice: int = 0


class SalesInfoBody(BaseModel):
    selectedTier: str = "mid"
    finalPrice: int = 0
    shippingMethod: str = "sls"
    category: str = ""
    attrs: dict[str, str] = {}
    useOptions: bool = True
    option1: OptionBody | None = None
    option2: OptionBody | None = None
    stock: list[StockRowBody] = []
    packaging: dict | None = None


class DetailContentBody(BaseModel):
    name: str
    description: str
    #: true 면 현지어본도 다시 옮긴다
    retranslate: bool = True


class GenerateImageBody(BaseModel):
    target: str = "detail"
    prompt: str
    mode: str = "basic"
    modelId: str | None = None
    referenceIds: list[str] = []


class GeneratedImageBody(BaseModel):
    #: 이미지 잡 id (GET /image-jobs/{jobId} 결과의 id)
    generatedImageId: str
    target: str = "detail"
    replaceImageId: str | None = None


class MainImageBody(BaseModel):
    imageId: str


class SuggestBody(BaseModel):
    category: str | None = Field(default=None, description="고른 카테고리. 없으면 AI 가 고른다")


# ── 인증 (목) ───────────────────────────────────────────────────────────


@router.post("/auth/login")
async def login(body: LoginBody) -> dict:
    return {"accessToken": f"dev-{uuid.uuid4().hex[:12]}", "email": body.email}


@router.post("/auth/join")
async def join(body: JoinBody) -> dict:
    return {"email": body.email}


# ── 상품 ────────────────────────────────────────────────────────────────


@router.get("/products/categories")
async def categories() -> list[dict]:
    return [{"value": name, "label": name} for name in CATEGORIES]


@router.post("/uploads/images")
async def upload_image(file: UploadFile = File(...)) -> dict:
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = (file.filename or "img.png").split(".")[-1]
    name = f"{uuid.uuid4().hex}.{suffix}"
    (settings.upload_dir / name).write_bytes(await file.read())
    return {"id": name, "url": f"/api/v1/uploads/{name}"}


@router.post("/products/ai-fill")
async def ai_fill(body: ProductFillRequest) -> dict:
    result = await product_fill.fill(body)
    return result.model_dump(by_alias=True)


@router.get("/products")
async def list_products() -> list[dict]:
    return [_to_product_card(item) for item in _products.values()]


@router.get("/products/{product_id}")
async def get_product(product_id: int) -> dict:
    return _to_product_card(_require_product(product_id))


@router.post("/products", status_code=201)
async def create_product(body: ProductBody) -> dict:
    product_id = next(_product_seq)
    _products[product_id] = {
        "id": product_id,
        "name": body.name,
        "category": body.category,
        "costPrice": body.costPrice,
        "weight": body.weight,
        "description": body.description,
        "sellingPoints": body.sellingPoints,
        "mainTarget": body.mainTarget,
        "images": body.imageUrls,
        "registeredAt": date.today().isoformat(),
        "revenue": None,
        "result": None,
    }
    job_id = await _start_analysis(product_id)
    return {"productId": product_id, "analysisJobId": job_id}


# ── 분석 잡 ─────────────────────────────────────────────────────────────


async def _start_analysis(product_id: int) -> str:
    product = _products[product_id]
    job_id = f"a_{product_id}_{next(_job_seq)}"
    command = AnalysisCommand(
        job_id=job_id,
        trace_id=uuid.uuid4().hex,
        countries=list(SUPPORTED_COUNTRIES),
        product=_snapshot(product),
        market_profile=MarketProfile(),
        preferences=AnalysisPreferences(),
    )
    await runner.submit_analysis(command)
    _jobs_by_product[product_id] = job_id
    return job_id


@router.get("/products/{product_id}/analysis")
async def analysis_status(product_id: int) -> dict:
    job_id = _jobs_by_product.get(product_id)
    if job_id is None:
        raise HTTPException(status_code=404, detail="분석 이력이 없습니다")

    state = await store.get(job_id)
    #: 완료되면 결과를 상품에 붙여 둔다. 보고서 조회가 이걸 읽는다.
    if state.status is JobStatus.COMPLETED and state.result:
        _products[product_id]["result"] = state.result

    return {
        "jobId": state.job_id,
        "status": state.status.value,
        "step": state.step.value if state.step else None,
        "progress": state.progress,
        "countries": {
            code: {
                "status": value.status.value,
                "step": value.step.value if value.step else None,
                "progress": value.progress,
            }
            for code, value in state.countries.items()
        },
        "errorCode": state.error.code.value if state.error else None,
    }


@router.post("/products/{product_id}/analysis/cancel", status_code=204)
async def cancel_analysis(product_id: int) -> None:
    job_id = _jobs_by_product.get(product_id)
    if job_id:
        await runner.cancel(job_id)


# ── 보고서 ──────────────────────────────────────────────────────────────


@router.get("/products/{product_id}/report")
async def total_report(product_id: int):  # noqa: ANN201
    _require_product(product_id)
    result = await _ensure_result(product_id)
    if result is None:
        return _pending(product_id)
    return _to_total_report(result)


@router.get("/products/{product_id}/report/{country_code}")
async def country_report(product_id: int, country_code: str):  # noqa: ANN201
    _require_product(product_id)
    result = await _ensure_result(product_id)
    if result is None:
        return _pending(product_id)

    entry = _find_country(_parse(result), country_code.upper())
    if entry is None:
        raise HTTPException(status_code=404, detail="해당 국가 분석 결과가 없습니다")
    return _to_country_report(entry)


@router.post("/products/{product_id}/countries/{country_code}/pricing/quote")
async def quote(product_id: int, country_code: str, body: QuoteRequest) -> QuoteResponse:
    return await pricing_quote.quote(body)


# ── 판매 정보 ───────────────────────────────────────────────────────────


@router.get("/shopee/categories")
async def shopee_category_list(country: str = Query("VN")) -> list[dict]:
    catalog = shopee_categories.load(country.upper())
    return [
        {"value": item.id, "label": item.label, "labelLocal": item.label_local}
        for item in catalog.categories.values()
    ]


@router.get("/shopee/categories/{category_id}/attributes")
async def shopee_category_attributes(category_id: str, country: str = Query("VN")) -> list[dict]:
    catalog = shopee_categories.load(country.upper())
    category = catalog.get(category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="카테고리를 찾을 수 없습니다")
    return [attr.model_dump(by_alias=True) for attr in catalog.attribute_schema(category)]


@router.get("/products/{product_id}/countries/{country_code}/sales-info")
async def sales_info(product_id: int, country_code: str):  # noqa: ANN201
    """판매 정보 입력 화면 초기값. 분석 결과 + AI 추천값 + 저장값."""
    product = _require_product(product_id)
    result = await _ensure_result(product_id)
    if result is None:
        return _pending(product_id)

    code = country_code.upper()
    entry = _find_country(_parse(result), code)
    if entry is None:
        raise HTTPException(status_code=404, detail="해당 국가 분석 결과가 없습니다")

    key = (product_id, code)
    if key not in _sales_suggestions:
        _sales_suggestions[key] = await sales_suggest.suggest(
            SalesSuggestRequest(country=code, product=_snapshot(product))
        )
    return _to_sales_info(product, entry, _sales_suggestions[key], _sales_infos.get(key))


@router.post("/products/{product_id}/countries/{country_code}/sales-info/suggest")
async def sales_info_suggest(product_id: int, country_code: str, body: SuggestBody) -> dict:
    """카테고리를 바꾸면 그 카테고리 기준으로 속성·옵션을 다시 채운다."""
    product = _require_product(product_id)
    code = country_code.upper()
    suggestion = await sales_suggest.suggest(
        SalesSuggestRequest(country=code, product=_snapshot(product), category_id=body.category)
    )
    _sales_suggestions[(product_id, code)] = suggestion
    return _suggestion_fields(suggestion)


@router.put("/products/{product_id}/countries/{country_code}/sales-info")
async def save_sales_info(product_id: int, country_code: str, body: SalesInfoBody) -> dict:
    _require_product(product_id)
    code = country_code.upper()

    use = body.useOptions
    option1 = OptionSpec(**body.option1.model_dump()) if use and body.option1 else None
    option2 = OptionSpec(**body.option2.model_dump()) if use and body.option2 else None
    problems = sales_suggest.validate_options(option1, option2)
    if shopee_categories.load(code).get(body.category) is None:
        problems.append("카테고리를 선택하세요")
    if problems:
        raise HTTPException(status_code=422, detail=problems)

    saved = body.model_dump()
    saved["savedAt"] = datetime.now(UTC).isoformat()
    _sales_infos[(product_id, code)] = saved
    return {"saved": saved, "hasSalesInfo": True}


# ── 상세 페이지 ─────────────────────────────────────────────────────────


@router.post("/products/{product_id}/countries/{country_code}/detail-page", status_code=202)
async def create_detail_page(product_id: int, country_code: str) -> dict:
    """판매 정보가 확정돼야 만들 수 있다. 다시 누르면 새로 만든다 (셀러 수정본은 버린다)."""
    product = _require_product(product_id)
    code = country_code.upper()
    saved = _sales_infos.get((product_id, code))
    if saved is None:
        raise HTTPException(status_code=409, detail="판매 정보를 먼저 저장하세요")

    result = await _ensure_result(product_id)
    entry = _find_country(_parse(result), code) if result else None
    if entry is None:
        raise HTTPException(status_code=404, detail="해당 국가 분석 결과가 없습니다")

    job_id = f"c_{product_id}_{code}_{next(_job_seq)}"
    await runner.submit_content(_content_command(job_id, product, entry, saved))
    _detail_jobs[(product_id, code)] = job_id
    _detail_pages.pop((product_id, code), None)
    return {"jobId": job_id}


@router.get("/products/{product_id}/countries/{country_code}/detail-page")
async def detail_page(product_id: int, country_code: str):  # noqa: ANN201
    from fastapi.responses import JSONResponse

    product = _require_product(product_id)
    code = country_code.upper()
    page = await _ensure_detail(product_id, code)
    if page is not None:
        return _to_detail_page(product, code, page)

    job_id = _detail_jobs.get((product_id, code))
    if job_id is None:
        raise HTTPException(status_code=404, detail="상세 페이지가 없습니다")
    state = await store.get(job_id)
    if state.status in (JobStatus.FAILED, JobStatus.CANCELLED):
        return {
            "status": "FAILED",
            "jobId": job_id,
            "errorCode": state.error.code.value if state.error else None,
        }
    return JSONResponse(
        status_code=202,
        content={
            "status": "GENERATING",
            "jobId": job_id,
            "step": state.step.value if state.step else None,
            "progress": state.progress,
        },
    )


@router.patch("/products/{product_id}/countries/{country_code}/detail-page/content")
async def update_detail_content(
    product_id: int, country_code: str, body: DetailContentBody
) -> dict:
    """셀러가 고친 한국어 상품명·설명. 사람이 고친 값은 이후 AI 가 덮어쓰지 않는다."""
    product = _require_product(product_id)
    code = country_code.upper()
    page = await _ensure_detail(product_id, code)
    if page is None:
        raise HTTPException(status_code=404, detail="상세 페이지가 없습니다")

    ko, local = page["ko"], page["local"]
    if body.retranslate and local is not None:
        translated = await content_edit.retranslate(
            country=code,
            locale=page["locale"],
            name=body.name,
            description=body.description,
            previous_name=local["name"],
            previous_description=local["description"],
        )
        local.update(name=translated.name, description=translated.description)
    ko.update(name=body.name, description=body.description)
    page["edited"] = True
    return _to_detail_page(product, code, page)


# ── 상세 페이지 이미지 ──────────────────────────────────────────────────


@router.get("/uploads/{name}")
async def serve_upload(name: str):  # noqa: ANN201
    """업로드·생성 이미지 서빙. 업로드 응답의 url 이 이 경로를 가리킨다."""
    from fastapi.responses import FileResponse

    path = get_settings().upload_dir / Path(name).name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="파일이 없습니다")
    return FileResponse(path)


@router.post("/products/{product_id}/countries/{country_code}/detail-page/images")
async def upload_detail_image(
    product_id: int,
    country_code: str,
    file: UploadFile = File(...),
    target: str = Form("detail"),
) -> dict:
    page = await _require_detail(product_id, country_code)
    uploaded = await upload_image(file)
    return _add_image(page, target, uploaded["url"])


@router.post("/products/{product_id}/countries/{country_code}/detail-page/images/generated")
async def save_generated_image(
    product_id: int, country_code: str, body: GeneratedImageBody
) -> dict:
    """AI 생성 결과 확정. replaceImageId 가 있으면 그 자리를 바꾼다 (재생성 시 원본 id 유지)."""
    page = await _require_detail(product_id, country_code)
    state = await store.get(body.generatedImageId)
    if state.status is not JobStatus.COMPLETED or not state.result:
        raise HTTPException(status_code=409, detail="이미지 생성이 끝나지 않았습니다")
    image = ImageResult.model_validate(state.result)

    if body.replaceImageId:
        for key in ("productImages", "detailImages"):
            for item in page[key]:
                if item["id"] == body.replaceImageId:
                    item.update(src=image.image_url, prompt=image.prompt)
                    return item
    return _add_image(page, body.target, image.image_url, prompt=image.prompt)


@router.delete(
    "/products/{product_id}/countries/{country_code}/detail-page/images/{image_id}",
    status_code=204,
)
async def delete_detail_image(product_id: int, country_code: str, image_id: str) -> None:
    page = await _require_detail(product_id, country_code)
    for key in ("productImages", "detailImages"):
        page[key] = [item for item in page[key] if item["id"] != image_id]
    if page["mainImageId"] == image_id:
        page["mainImageId"] = page["productImages"][0]["id"] if page["productImages"] else None


@router.put("/products/{product_id}/countries/{country_code}/detail-page/images/main")
async def set_main_image(product_id: int, country_code: str, body: MainImageBody) -> dict:
    page = await _require_detail(product_id, country_code)
    if not any(item["id"] == body.imageId for item in page["productImages"]):
        raise HTTPException(status_code=404, detail="상품 이미지가 아닙니다")
    page["mainImageId"] = body.imageId
    return {"mainImageId": body.imageId}


@router.post(
    "/products/{product_id}/countries/{country_code}/detail-page/images/generate",
    status_code=202,
)
async def generate_detail_image(
    product_id: int, country_code: str, body: GenerateImageBody
) -> dict:
    """프론트 GenerateImageParams 그대로. referenceIds 는 보유 사진 id 또는 업로드 id."""
    page = await _require_detail(product_id, country_code)
    references = [_reference_url(page, ref_id) for ref_id in body.referenceIds]
    references = [url for url in references if url]
    if not references:
        raise HTTPException(status_code=422, detail="참고 사진을 1장 이상 고르세요")

    job_id = f"i_{product_id}_{next(_job_seq)}"
    await runner.submit_image(
        ImageCommand(
            job_id=job_id,
            trace_id=uuid.uuid4().hex,
            target=ImageTarget(body.target.upper()),
            prompt=body.prompt,
            mode=ImageMode(body.mode.upper()),
            model_id=body.modelId,
            reference_urls=references,
        )
    )
    return {"jobId": job_id}


@router.get("/image-jobs/{job_id}")
async def image_job(job_id: str) -> dict:
    state = await store.get(job_id)
    status = {
        JobStatus.COMPLETED: "DONE",
        JobStatus.FAILED: "FAILED",
        JobStatus.CANCELLED: "CANCELLED",
    }.get(state.status, "RUNNING")
    result = None
    if state.status is JobStatus.COMPLETED and state.result:
        image = ImageResult.model_validate(state.result)
        result = {"id": job_id, "src": image.image_url, "prompt": image.prompt}
    return {
        "status": status,
        "progress": state.progress,
        "result": result,
        "errorCode": state.error.code.value if state.error else None,
    }


@router.post("/image-jobs/{job_id}/cancel", status_code=204)
async def cancel_image_job(job_id: str) -> None:
    await runner.cancel(job_id)


# ── 코파일럿 ────────────────────────────────────────────────────────────


@router.post("/products/{product_id}/copilot/messages")
async def copilot_message(product_id: int, body: CopilotRequest) -> CopilotResponse:
    return await copilot.answer(body)


# ── 내부 헬퍼 ───────────────────────────────────────────────────────────


def _snapshot(product: dict) -> ProductSnapshot:
    packaging = product.get("packaging")
    return ProductSnapshot(
        product_id=product["id"],
        name=product["name"],
        category=product["category"],
        supply_cost_krw=product["costPrice"],
        weight_g=product["weight"],
        description=product["description"],
        selling_point=product["sellingPoints"],
        main_target=product["mainTarget"],
        packaging=Packaging(**packaging) if packaging else None,
        image_urls=product["images"],
    )


def _require_product(product_id: int) -> dict:
    product = _products.get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다")
    return product


async def _ensure_result(product_id: int) -> dict | None:
    """저장된 결과가 없으면 잡 상태를 한 번 확인한다."""
    product = _products[product_id]
    if product.get("result"):
        return product["result"]

    job_id = _jobs_by_product.get(product_id)
    if not job_id:
        return None
    state = await store.get(job_id)
    if state.status is JobStatus.COMPLETED and state.result:
        product["result"] = state.result
        return state.result
    return None


def _pending(product_id: int):  # noqa: ANN201
    """분석이 아직이면 202. 프론트는 2초마다 다시 부른다."""
    from fastapi.responses import JSONResponse

    job_id = _jobs_by_product.get(product_id)
    return JSONResponse(status_code=202, content={"status": "RUNNING", "jobId": job_id})


def _parse(result: dict) -> AnalysisResult:
    """잡 결과 JSON 을 계약 모델로 되돌린다.

    [중요] 저장된 JSON 은 camelCase 다. dict 로 직접 키를 뒤지면 kFit / priceKrw 같은
           키를 snake_case 로 잘못 읽어 값이 조용히 0 이 된다. 모델로 파싱해 속성으로 쓴다.
           Spring 도 같은 이유로 DTO 로 역직렬화한 뒤 매핑해야 한다.
    """
    return AnalysisResult.model_validate(result)


def _find_country(result: AnalysisResult, code: str) -> CountryResult | None:
    return next((item for item in result.countries if item.country == code), None)


def _visible_countries(result: AnalysisResult) -> list[CountryResult]:
    """판매 불가·실패 국가는 화면에서 뺀다. 사유는 결과에 남아 있다."""
    hidden = (CountryStatus.FILTERED_OUT, CountryStatus.FAILED)
    visible = [item for item in result.countries if item.status not in hidden]
    return sorted(visible, key=lambda item: item.scores.rank if item.scores else 99)


def _recommended(entry: CountryResult) -> PriceScenario | None:
    scenarios = entry.pricing.scenarios if entry.pricing else []
    if not scenarios:
        return None
    return next((item for item in scenarios if item.recommended), scenarios[0])


def _to_product_card(product: dict) -> dict:
    """프론트 Product 타입. countries 는 분석 결과에서 만든다."""
    countries = []
    if product.get("result"):
        for item in _visible_countries(_parse(product["result"])):
            has_sales_info = (product["id"], item.country) in _sales_infos
            has_detail = (product["id"], item.country) in _detail_pages
            countries.append(
                {
                    "code": item.country,
                    "name": COUNTRY_NAMES.get(item.country, item.country),
                    "stage": (
                        "detail" if has_detail else "sales-info" if has_sales_info else "report"
                    ),
                    "salesStatus": "판매전",
                    "hasDetailPage": has_detail,
                    "hasSalesInfo": has_sales_info,
                }
            )
    return {
        "id": product["id"],
        "name": product["name"],
        "image": (product["images"] or [""])[0],
        "images": product["images"],
        "category": product["category"],
        "costPrice": product["costPrice"],
        "weight": product["weight"],
        "description": product["description"],
        "sellingPoints": product["sellingPoints"],
        "mainTarget": product["mainTarget"],
        "revenue": product["revenue"],
        "registeredAt": product["registeredAt"],
        "countries": countries,
    }


def _axis_rows(scores, *, with_comment: bool) -> list[dict]:  # noqa: ANN001
    """4축 지표 행. 경쟁 강도만 색 의미를 뒤집는다."""
    if scores is None:
        return []
    rows = []
    for key in ("demand", "competition", "k_fit", "profitability"):
        axis = getattr(scores, key)
        row = {
            "label": AXIS_LABEL[key],
            "grade": GRADE_KO.get(axis.grade.value, "보통"),
            "score": axis.score,
        }
        if with_comment:
            row["comment"] = axis.comment
        if key == "competition":
            row["invert"] = True
        rows.append(row)
    return rows


def _to_total_report(raw: dict) -> dict:
    """AI 결과 -> 프론트 TotalReport.

    지표 4축은 1순위 국가 값을 쓴다. 평균을 내면 어느 국가 얘기인지 알 수 없어진다.
    """
    result = _parse(raw)
    visible = _visible_countries(result)
    top = visible[0] if visible else None

    countries = []
    for item in visible:
        recommended = _recommended(item)
        countries.append(
            {
                "code": item.country,
                "rank": item.scores.rank if item.scores else 0,
                "fitGrade": FIT_KO.get(
                    item.scores.fit_grade.value if item.scores else "NORMAL", "보통"
                ),
                "priceLocalText": local_price_text(
                    item.country, recommended.price_local if recommended else 0
                ),
                "priceKrw": recommended.price_krw if recommended else 0,
            }
        )

    return {
        "conclusionTitle": result.global_.conclusion_title,
        "conclusionBody": result.global_.conclusion_body,
        "metrics": _axis_rows(top.scores if top else None, with_comment=False),
        "countries": countries,
        "investigation": {
            "summary": result.global_.investigation_summary,
            "countries": [COUNTRY_NAMES.get(item.country, item.country) for item in visible],
            "criteria": list(AXIS_LABEL.values()),
            "platforms": ["Shopee"],
        },
        "nextAction": result.global_.next_action,
        #: 판매 이력은 주문 집계라 AI 산출값이 아니다. Spring 이 채운다.
        "sales": None,
    }


def _to_country_report(entry: CountryResult) -> dict:
    """AI 결과 -> 프론트 CountryReport."""
    code = entry.country
    insight = entry.insight
    competition = entry.competition
    pricing = entry.pricing
    recommended = _recommended(entry)

    band = competition.price_band_krw if competition else None
    weights = band.weights if band else [1, 1, 1]
    tiers = [
        {"label": f"{won(band.low_krw if band else 0)} (저가형)", "weight": weights[0]},
        {"label": f"{won(band.mid_krw if band else 0)} (중간형)", "weight": weights[1]},
        {"label": f"{won(band.high_krw if band else 0)}+ (프리미엄)", "weight": weights[2]},
    ]

    options = [
        {
            "id": METHOD_ID.get(option.method.value, "direct"),
            "name": METHOD_NAME.get(option.method.value, option.method.value),
            "costText": f"{won(option.cost_krw)}/개",
            "periodText": f"{option.eta_min_days}~{option.eta_max_days}일",
            "fitBadge": option.fit_badge,
            "recommended": option.recommended,
            "description": option.description,
        }
        for option in (entry.logistics.options if entry.logistics else [])
    ]

    scenarios = [
        {
            "id": TIER_ID.get(scenario.tier.value, "mid"),
            "label": TIER_LABEL.get(scenario.tier.value, scenario.tier.value),
            "price": scenario.price_krw,
            "priceLocalText": local_price_text(code, scenario.price_local),
            "netProfit": scenario.net_profit_krw,
            "marginRate": round(scenario.margin_rate * 100, 1),
            "breakevenUnits": scenario.break_even_units or 0,
            "badge": scenario.badge,
            "recommended": scenario.recommended,
            "summary": scenario.summary,
            "costRows": [
                {
                    "label": row.label,
                    "amountText": signed(row.amount_krw),
                    **({"emphasis": True} if row.key in ("salePrice", "netProfit") else {}),
                }
                for row in scenario.cost_rows
            ],
        }
        for scenario in (pricing.scenarios if pricing else [])
    ]

    packaging = entry.logistics.packaging_used if entry.logistics else None
    price_krw = recommended.price_krw if recommended else 0
    return {
        "code": code,
        "name": COUNTRY_NAMES.get(code, code),
        "currency": CURRENCY_SYMBOL.get(code, ""),
        "conclusion": {
            "title": insight.conclusion_title if insight else "",
            "body": insight.conclusion_body if insight else "",
            "positioning": insight.positioning_label if insight else "",
            "priceText": (
                f"{won(price_krw)} "
                f"({local_price_text(code, recommended.price_local if recommended else 0)})"
            ),
            "profitText": f"{won(recommended.net_profit_krw if recommended else 0)} / 개당",
        },
        "analysis": {
            "summary": insight.summary if insight else "",
            "metrics": _axis_rows(entry.scores, with_comment=True),
        },
        "competition": {
            "summary": competition.summary if competition else "",
            "stats": [
                {
                    "label": stat.label,
                    "value": stat.value,
                    **({"tone": "bad"} if stat.tone == "bad" else {}),
                }
                for stat in (competition.stats if competition else [])
            ],
            "priceTiers": tiers,
            "priceMarker": {
                "label": f"{won(price_krw)} 권장가",
                "ratio": _band_ratio(price_krw, band),
            },
            "table": [
                {
                    "type": row.type,
                    "priceRange": row.price_range,
                    "strength": row.strength,
                    "weakness": row.weakness,
                    "strategy": row.strategy,
                }
                for row in (competition.table if competition else [])
            ],
        },
        "shipping": {
            "options": options,
            #: 근거 조항을 문장 뒤에 붙인다 (R-004-03)
            "warnings": [
                f"{item.text} (근거: {item.source})" if item.source else item.text
                for item in (entry.risk.warnings if entry.risk else [])
            ],
        },
        "packaging": {
            "width": int(packaging.width_mm / 10) if packaging else 0,
            "depth": int(packaging.depth_mm / 10) if packaging else 0,
            "height": int(packaging.height_mm / 10) if packaging else 0,
        },
        "pricing": {
            "scenarios": scenarios,
            "appliedBadges": pricing.applied_badges if pricing else [],
        },
    }


def _option_fields(option: OptionSpec | None) -> dict | None:
    if option is None:
        return None
    return {"name": option.name, "label": option.label or option.name, "values": option.values}


def _suggestion_fields(suggestion: SalesSuggestResponse) -> dict:
    """AI 추천값 -> 프론트 판매 정보 필드."""
    return {
        "shopeeCategoryOptions": suggestion.category_options,
        "shopeeCategoryDefault": suggestion.category_id,
        "categoryAttrs": [attr.model_dump(by_alias=True) for attr in suggestion.category_attrs],
        "optionLevel1": _option_fields(suggestion.option1),
        "optionLevel2": _option_fields(suggestion.option2),
        "stockHint": suggestion.stock_hint,
    }


def _to_sales_info(
    product: dict,
    entry: CountryResult,
    suggestion: SalesSuggestResponse,
    saved: dict | None,
) -> dict:
    """AI 결과 + 추천값 -> 프론트 판매 정보 화면 (mocks/sales.ts 형태)."""
    code = entry.country
    fee = fee_schedule.load(code)
    pricing = entry.pricing
    fx = pricing.fx.krw_per_local if pricing and pricing.fx else 0.0

    price_scenarios = [
        {
            "id": TIER_ID.get(scenario.tier.value, "mid"),
            "label": TIER_LABEL.get(scenario.tier.value, scenario.tier.value),
            "price": scenario.price_krw,
            "badge": scenario.badge,
            **({"recommended": True} if scenario.recommended else {}),
        }
        for scenario in (pricing.scenarios if pricing else [])
    ]
    shipping_methods = [
        {
            "id": METHOD_ID.get(option.method.value, "direct"),
            "name": METHOD_NAME.get(option.method.value, option.method.value),
            "cost": f"{won(option.cost_krw)}/개",
            "costKrw": option.cost_krw,
            "period": f"{option.eta_min_days}~{option.eta_max_days}일",
            "note": option.fit_badge,
            **({"aiRecommended": True} if option.recommended else {}),
        }
        for option in (entry.logistics.options if entry.logistics else [])
    ]

    packaging = entry.logistics.packaging_used if entry.logistics else None
    return {
        "priceScenarios": price_scenarios,
        "shippingMethods": shipping_methods,
        "marginBasis": {
            "dutyRate": float(fee.duty_rate),
            "vatRate": float(fee.vat_rate),
            "shopeeFeeRate": float(fee.platform_fee_rate),
            "paymentFeeRate": float(fee.payment_fee_rate),
            "fixedCostKrw": 0,
            "fxNote": f"1 {fee.currency} = {fx:g}원" if fx else "",
            "taxBase": fee.tax_base,
        },
        "appliedBadges": pricing.applied_badges if pricing else [],
        "packaging": {
            "weight": packaging.weight_g if packaging else product["weight"],
            "width": int(packaging.width_mm / 10) if packaging else 0,
            "depth": int(packaging.depth_mm / 10) if packaging else 0,
            "height": int(packaging.height_mm / 10) if packaging else 0,
        },
        **_suggestion_fields(suggestion),
        "stockRows": [],
        "saved": saved,
    }


#: 상세페이지 플랫폼 문구. Spring 이 판매정보로 채우는 부분이다 (AI 산출 아님).
PDP_TEXT = {
    "ko": {
        "region": "{country} 전 지역 배송",
        "fee": "무료배송 · {method}",
        "eta": "{min} ~ {max}일 이내",
        "stock": "재고 {count}개 남음",
    },
    "vi": {
        "region": "Giao hàng toàn quốc Việt Nam",
        "fee": "Miễn phí vận chuyển · {method}",
        "eta": "Trong {min} ~ {max} ngày",
        "stock": "Còn {count} sản phẩm",
    },
    "en": {
        "region": "Island-wide delivery in Singapore",
        "fee": "Free shipping · {method}",
        "eta": "{min} ~ {max} days",
        "stock": "{count} left in stock",
    },
    "th": {
        "region": "จัดส่งทั่วประเทศไทย",
        "fee": "ส่งฟรี · {method}",
        "eta": "ภายใน {min} ~ {max} วัน",
        "stock": "เหลือ {count} ชิ้น",
    },
}


def _content_command(
    job_id: str, product: dict, entry: CountryResult, saved: dict
) -> ContentCommand:
    """확정 판매정보 + 분석 요약 -> 상세페이지 잡 입력."""
    code = entry.country
    category = shopee_categories.load(code).get(saved.get("category"))
    fx = entry.pricing.fx.krw_per_local if entry.pricing and entry.pricing.fx else 0.0
    final_price = int(saved.get("finalPrice") or 0)
    method = (saved.get("shippingMethod") or "").upper()
    use_options = saved.get("useOptions", True)

    return ContentCommand(
        job_id=job_id,
        trace_id=uuid.uuid4().hex,
        country=code,
        locale=COUNTRY_LOCALE.get(code, "en"),
        product=_snapshot(product),
        sales_info=SalesInfoSnapshot(
            category_id=saved.get("category", ""),
            category_label=category.label if category else "",
            attributes=saved.get("attrs") or {},
            option1=saved.get("option1") if use_options else None,
            option2=saved.get("option2") if use_options else None,
            final_price_krw=final_price,
            final_price_local=round(final_price / fx, 2) if fx else 0.0,
            currency=COUNTRY_CURRENCY.get(code, ""),
            shipping_method=(
                ShippingMethod(method) if method in ShippingMethod.__members__ else None
            ),
            stock_total=sum(int(row.get("qty") or 0) for row in saved.get("stock") or []),
        ),
        analysis=AnalysisDigest(
            positioning=entry.insight.positioning.value if entry.insight else "",
            positioning_label=entry.insight.positioning_label if entry.insight else "",
            risk_flags=[item.text for item in (entry.risk.warnings if entry.risk else [])],
        ),
        market_profile=MarketProfile(),
    )


async def _ensure_detail(product_id: int, code: str) -> dict | None:
    """잡이 끝났으면 결과를 상세페이지 상태로 옮겨 둔다. 이후 수정은 여기에 쌓인다."""
    key = (product_id, code)
    if key in _detail_pages:
        return _detail_pages[key]
    job_id = _detail_jobs.get(key)
    if job_id is None:
        return None
    state = await store.get(job_id)
    if state.status is not JobStatus.COMPLETED or not state.result:
        return None

    result = ContentResult.model_validate(state.result)
    product = _products[product_id]
    _detail_pages[key] = {
        "status": result.status.value,
        "qualityScore": result.quality_score,
        "qualityIssues": [issue.model_dump(by_alias=True) for issue in result.quality_issues],
        "locale": result.locale,
        "ko": result.ko.model_dump(by_alias=True) if result.ko else None,
        "local": result.local.model_dump(by_alias=True) if result.local else None,
        "edited": False,
        "productImages": [
            {"id": f"pi_{index}", "label": f"기본 {index}", "src": url}
            for index, url in enumerate(product["images"], start=1)
        ],
        "detailImages": [],
        "mainImageId": "pi_1" if product["images"] else None,
    }
    return _detail_pages[key]


def _pdp(draft: dict, *, lang: str, code: str, saved: dict, entry: CountryResult | None) -> dict:
    """AI 초안 + 판매정보 -> 프론트 PdpContent."""
    text = PDP_TEXT.get(lang, PDP_TEXT["en"])
    method = (saved.get("shippingMethod") or "sls").upper()
    option = next(
        (
            item
            for item in (entry.logistics.options if entry and entry.logistics else [])
            if item.method.value == method
        ),
        None,
    )
    fx = entry.pricing.fx.krw_per_local if entry and entry.pricing and entry.pricing.fx else 0.0
    price_local = (saved.get("finalPrice") or 0) / fx if fx else 0.0
    price = local_price_text(code, price_local)
    if lang == "vi":
        #: 베트남 표기는 천 단위 마침표
        price = price.replace(",", ".")
    stock = sum(int(row.get("qty") or 0) for row in saved.get("stock") or [])

    return {
        "breadcrumb": draft["breadcrumb"],
        "name": draft["name"],
        "price": price,
        "usps": draft["usps"],
        "shipping": {
            "region": text["region"].format(country=COUNTRY_NAMES.get(code, code)),
            "fee": text["fee"].format(method=METHOD_NAME.get(method, method)),
            "eta": text["eta"].format(
                min=option.eta_min_days if option else "-",
                max=option.eta_max_days if option else "-",
            ),
        },
        "options": draft.get("options") or [],
        "stockNote": text["stock"].format(count=stock),
        "specs": draft["specs"],
        "description": draft["description"],
    }


def _to_detail_page(product: dict, code: str, page: dict) -> dict:
    saved = _sales_infos.get((product["id"], code)) or {}
    result = product.get("result")
    entry = _find_country(_parse(result), code) if result else None
    content = {
        "ko": _pdp(page["ko"], lang="ko", code=code, saved=saved, entry=entry),
        "local": (
            _pdp(page["local"], lang=page["locale"], code=code, saved=saved, entry=entry)
            if page["local"]
            else None
        ),
    }
    return {
        "status": page["status"],
        "qualityScore": page["qualityScore"],
        "qualityIssues": page["qualityIssues"],
        "edited": page["edited"],
        "content": content,
        "seller": {
            "name": "내 마켓",
            "meta": "온라인 · 5분 이내 응답",
            "rating": "—",
            "response": "—",
            "followers": "—",
        },
        "productImages": page["productImages"],
        "mainImageId": page["mainImageId"],
        "detailImages": page["detailImages"],
        "locale": page["locale"],
    }


async def _require_detail(product_id: int, country_code: str) -> dict:
    _require_product(product_id)
    page = await _ensure_detail(product_id, country_code.upper())
    if page is None:
        raise HTTPException(status_code=404, detail="상세 페이지를 먼저 생성하세요")
    return page


def _add_image(page: dict, target: str, src: str, *, prompt: str | None = None) -> dict:
    """상품 이미지(기본 N) / 상세 이미지(상세 이미지 N) 목록 끝에 붙인다."""
    is_product = target.lower() == "product"
    key = "productImages" if is_product else "detailImages"
    index = len(page[key]) + 1
    item = {
        "id": f"{'pi' if is_product else 'di'}_{uuid.uuid4().hex[:8]}",
        "label": f"기본 {index}" if is_product else f"상세 이미지 {index}",
        "src": src,
        "prompt": prompt,
    }
    page[key].append(item)
    if is_product and page["mainImageId"] is None:
        page["mainImageId"] = item["id"]
    return item


def _reference_url(page: dict, ref_id: str) -> str | None:
    """참고 사진 id -> URL. 상세페이지 이미지 id 이거나 /uploads/images 응답 id 다."""
    for key in ("productImages", "detailImages"):
        for item in page[key]:
            if item["id"] == ref_id:
                return item["src"]
    if (get_settings().upload_dir / Path(ref_id).name).is_file():
        return f"/api/v1/uploads/{Path(ref_id).name}"
    return None


def _band_ratio(price_krw: int, band) -> float:  # noqa: ANN001
    """권장가가 가격대 띠 위 어디쯤인지. 0~1."""
    if band is None or not band.high_krw or band.high_krw <= band.low_krw or not price_krw:
        return 0.5
    ratio = (price_krw - band.low_krw) / (band.high_krw - band.low_krw)
    return round(min(max(ratio, 0.0), 1.0), 2)


@router.get("/health")
async def dev_health() -> dict:
    return {"status": "ok", "products": len(_products), "at": datetime.now(UTC).isoformat()}
