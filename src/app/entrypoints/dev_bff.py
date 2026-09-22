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

담당: 이동건   상태: 1차 (등록 -> 분석 폴링 -> 보고서)
"""

from __future__ import annotations

import itertools
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import get_settings
from app.contracts.v1 import (
    COUNTRY_NAMES,
    SUPPORTED_COUNTRIES,
    AnalysisCommand,
    AnalysisPreferences,
    AnalysisResult,
    CopilotRequest,
    CopilotResponse,
    CountryResult,
    CountryStatus,
    JobStatus,
    MarketProfile,
    PriceScenario,
    ProductFillRequest,
    ProductSnapshot,
    QuoteRequest,
    QuoteResponse,
)
from app.core.jobs import runner, store
from app.core.services import copilot, pricing_quote, product_fill
from app.observability.logging import get_logger

log = get_logger(mod="dev_bff")
router = APIRouter(prefix="/api/v1", tags=["dev_bff"])

# ── 메모리 저장소 ───────────────────────────────────────────────────────

_products: dict[int, dict] = {}
_jobs_by_product: dict[int, str] = {}
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
        product=ProductSnapshot(
            product_id=product_id,
            name=product["name"],
            category=product["category"],
            supply_cost_krw=product["costPrice"],
            weight_g=product["weight"],
            description=product["description"],
            selling_point=product["sellingPoints"],
            main_target=product["mainTarget"],
            image_urls=product["images"],
        ),
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


# ── 코파일럿 ────────────────────────────────────────────────────────────


@router.post("/products/{product_id}/copilot/messages")
async def copilot_message(product_id: int, body: CopilotRequest) -> CopilotResponse:
    return await copilot.answer(body)


# ── 내부 헬퍼 ───────────────────────────────────────────────────────────


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
            countries.append(
                {
                    "code": item.country,
                    "name": COUNTRY_NAMES.get(item.country, item.country),
                    "stage": "report",
                    "salesStatus": "판매전",
                    "hasDetailPage": False,
                    "hasSalesInfo": False,
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


def _band_ratio(price_krw: int, band) -> float:  # noqa: ANN001
    """권장가가 가격대 띠 위 어디쯤인지. 0~1."""
    if band is None or not band.high_krw or band.high_krw <= band.low_krw or not price_krw:
        return 0.5
    ratio = (price_krw - band.low_krw) / (band.high_krw - band.low_krw)
    return round(min(max(ratio, 0.0), 1.0), 2)


@router.get("/health")
async def dev_health() -> dict:
    return {"status": "ok", "products": len(_products), "at": datetime.now(UTC).isoformat()}
