r"""content_graph — 현지화 상세페이지 생성 (요구사항 R-003-06/11, 화면 DTL-01-01).

    START ─▶ draft_ko ─▶ culture_filter ─▶ quality_check ─┬─ 통과 ──────────────▶ localize ─▶ END
                ▲                                         ├─ 미달 & 재생성 < 2 ─┐
                └──────────────── 지적 사항 주입 ─────────┘                      │
                                                          └─ 미달 & 2회 소진 ─▶ localize
                                                                                 (NEEDS_REVIEW)

단계별 역할
    draft_ko        gpt-4o. 확정 판매정보 + 분석 요약으로 한국어 초안 (상품명·USP 4개·본문 4단락)
    culture_filter  코드. 사전에 replace 가 있는 과장 표현만 바로 고친다
    quality_check   코드. 0~100점. 70점 미만이거나 하드 컷이면 지적 사항을 넣어 다시 쓴다
    localize        gpt-4o. 같은 구조의 현지어본 (vi / en / th). 현지어 사전으로 한 번 더 거른다

LLM 이 만들지 않는 것
    사양 표의 기본 행(카테고리·속성·무게·발송지·재고)과 breadcrumb 는 확정 판매정보에서
    코드가 만든다. LLM 은 사양 표에 없는 항목을 최대 3개 덧붙일 수만 있다.
    가격·배송·옵션·재고 문구는 Spring/dev_bff 가 판매정보로 채운다 (PdpContent).

미달로 끝나도 결과는 준다. status=NEEDS_REVIEW 와 지적 사항을 함께 보내고
셀러가 편집 화면에서 고친다. 하드 컷(금지어·상표)은 사람 승인 전 업로드 불가.

담당: 강근우 (콘텐츠 아키텍트 R-003)
"""

from __future__ import annotations

import json
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.contracts.v1 import (
    COUNTRY_NAMES,
    ContentCommand,
    ContentResult,
    ContentStatus,
    JobStep,
    PdpDraft,
    QualityIssue,
)
from app.core.agents import prompts
from app.core.agents.schemas import PdpCopyKo, PdpCopyLocal
from app.core.catalog import shopee_categories
from app.core.content import culture, quality
from app.core.graph.runtime import current_job
from app.core.graph.state import ContentState
from app.infra.llm import Model, complete_json
from app.observability.logging import get_logger

log = get_logger(mod="content_graph")

#: 품질 미달 시 자동 재생성 최대 횟수 (R-003-11)
MAX_REGENERATION = 2
#: LLM 이 덧붙일 수 있는 사양 행 수
MAX_EXTRA_SPECS = 3
MAX_USPS = 6
SHIP_FROM = "대한민국"
HOME_KO = "홈"

DRAFT_KO = "draft_ko"
CULTURE_FILTER = "culture_filter"
QUALITY_CHECK = "quality_check"
LOCALIZE = "localize"


# ── 진행 상태 ───────────────────────────────────────────────────────────


async def _enter(step: JobStep, progress: float) -> None:
    """노드 경계마다 취소를 확인하고 단계를 갱신한다. 프론트 오버레이가 이걸 본다."""
    ctx = current_job.get()
    if ctx is None:
        return
    await ctx.ensure_not_cancelled()
    await ctx.report_step(step, progress)


# ── 코드가 만드는 부분 ──────────────────────────────────────────────────


def base_specs(command: ContentCommand) -> list[list[str]]:
    """확정 판매정보로 사양 표 기본 행을 만든다. 빈 속성은 뺀다."""
    sales = command.sales_info
    catalog = shopee_categories.load(command.country)
    category = catalog.get(sales.category_id)

    rows: list[list[str]] = []
    label = category.label if category else sales.category_label
    if label:
        rows.append(["카테고리", label])
    for key, value in sales.attributes.items():
        text = str(value).strip()
        if text:
            rows.append([catalog.attr_label(key), text])
    if command.product.weight_g:
        rows.append(["무게", f"{command.product.weight_g} g"])
    rows.append(["발송지", SHIP_FROM])
    if sales.stock_total:
        rows.append(["재고", f"{sales.stock_total}개"])
    return rows


def breadcrumbs(command: ContentCommand) -> tuple[list[str], list[str]]:
    catalog = shopee_categories.load(command.country)
    category = catalog.get(command.sales_info.category_id)
    if category is None:
        path = [part.strip() for part in command.sales_info.category_label.split("›") if part]
        return [HOME_KO, *path], [catalog.home_label, *path]
    return [HOME_KO, *category.path], [catalog.home_label, *category.path_local]


def option_rows(command: ContentCommand) -> list[dict]:
    """판매정보 옵션 -> 상세페이지 옵션 표기. 이름은 짧은 name 을 쓴다 (프론트 목 기준)."""
    rows = []
    for option in (command.sales_info.option1, command.sales_info.option2):
        if option and option.get("values"):
            rows.append({"label": option.get("name", ""), "values": list(option["values"])})
    return rows


def _merge_specs(base: list[list[str]], extra: list[Any]) -> list[list[str]]:
    labels = {row[0] for row in base}
    merged = [list(row) for row in base]
    for row in extra[:MAX_EXTRA_SPECS]:
        if row.label and row.value and row.label not in labels:
            merged.append([row.label, row.value])
            labels.add(row.label)
    return merged


# ── 노드 ────────────────────────────────────────────────────────────────


async def draft_ko(state: ContentState) -> dict:
    regenerating = state.get("copy_ko") is not None
    count = state.get("regeneration_count", 0) + (1 if regenerating else 0)
    await _enter(JobStep.DRAFT, 0.1 + 0.15 * count)

    command: ContentCommand = state["command"]
    rules = culture.load(command.country)

    revision = []
    if command.revision_instruction:
        revision.append(f"셀러 요청: {command.revision_instruction}")
    if regenerating:
        revision.extend(issue["detail"] for issue in state.get("quality_issues") or [])

    sales = command.sales_info
    payload = {
        "market": {
            "country": COUNTRY_NAMES.get(command.country, command.country),
            "guidelines": list(rules.guidelines),
        },
        "product": {
            "name": command.product.name,
            "description": command.product.description,
            "sellingPoints": command.product.selling_point,
            "mainTarget": command.product.main_target,
        },
        "salesInfo": {
            "category": sales.category_label,
            "options": option_rows(command),
            "finalPriceKrw": sales.final_price_krw,
            "shippingMethod": sales.shipping_method.value if sales.shipping_method else None,
            "stockTotal": sales.stock_total,
        },
        "specs": state["specs"],
        "analysis": command.analysis.model_dump(by_alias=True),
        "brand": command.market_profile.model_dump(by_alias=True)
        if command.market_profile
        else None,
        "revision": revision,
    }

    prompt = prompts.load("content_draft")
    copy = await complete_json(
        schema=PdpCopyKo,
        system=prompt.body,
        user=json.dumps(payload, ensure_ascii=False, indent=2),
        model=Model.MAIN,
        prompt_version=prompt.version,
        node="CONTENT_DRAFT",
        job_id=command.job_id,
        trace_id=command.trace_id,
        temperature=0.4 if regenerating else 0.2,
        #: 재생성은 지적 사항이 달라 캐시 키도 다르다. 첫 초안만 캐시한다.
        cache_ttl=None if regenerating else 86400,
    )

    return {
        "regeneration_count": count,
        "copy_ko": {
            "name": copy.name.strip(),
            "usps": [item.strip() for item in copy.usps if item.strip()][:MAX_USPS],
            "sections": [
                copy.intro.strip(),
                copy.features.strip(),
                copy.benefits.strip(),
                copy.call_to_action.strip(),
            ],
            "specs": _merge_specs(state["specs"], copy.extra_specs),
        },
    }


async def culture_filter(state: ContentState) -> dict:
    command: ContentCommand = state["command"]
    rules = culture.load(command.country)
    copy = dict(state["copy_ko"])
    copy["name"] = culture.sanitize(rules, copy["name"])
    copy["usps"] = [culture.sanitize(rules, item) for item in copy["usps"]]
    copy["sections"] = [culture.sanitize(rules, item) for item in copy["sections"]]
    return {"copy_ko": copy}


async def quality_check(state: ContentState) -> dict:
    await _enter(JobStep.REVIEW, 0.55)
    command: ContentCommand = state["command"]
    report = quality.evaluate(
        state["copy_ko"],
        culture.load(command.country),
        keywords=command.analysis.keywords,
    )
    log.info(
        "품질 검수",
        score=report.score,
        passed=report.passed,
        regeneration=state.get("regeneration_count", 0),
    )
    return {
        "quality_score": report.score,
        "quality_issues": [issue.model_dump() for issue in report.issues],
        "quality_passed": report.passed,
    }


def _after_quality(state: ContentState) -> str:
    if state.get("quality_passed"):
        return LOCALIZE
    if state.get("regeneration_count", 0) < MAX_REGENERATION:
        return DRAFT_KO
    return LOCALIZE


async def localize(state: ContentState) -> dict:
    await _enter(JobStep.LOCALIZE, 0.75)
    command: ContentCommand = state["command"]
    rules = culture.load(command.country)
    copy_ko = state["copy_ko"]
    options = option_rows(command)

    payload = {
        "target": {
            "country": COUNTRY_NAMES.get(command.country, command.country),
            "locale": command.locale,
            "guidelines": list(rules.guidelines),
        },
        "ko": {
            "name": copy_ko["name"],
            "usps": copy_ko["usps"],
            "intro": copy_ko["sections"][0],
            "features": copy_ko["sections"][1],
            "benefits": copy_ko["sections"][2],
            "call_to_action": copy_ko["sections"][3],
        },
        "specs": copy_ko["specs"],
        "options": options,
        "keywords": command.analysis.keywords,
    }

    prompt = prompts.load("content_localize")
    local = await complete_json(
        schema=PdpCopyLocal,
        system=prompt.body,
        user=json.dumps(payload, ensure_ascii=False, indent=2),
        model=Model.MAIN,
        prompt_version=prompt.version,
        node="CONTENT_LOCALIZE",
        job_id=command.job_id,
        trace_id=command.trace_id,
    )

    issues = list(state.get("quality_issues") or [])
    specs = [[row.label, row.value] for row in local.specs]
    if len(specs) != len(copy_ko["specs"]):
        issues.append(
            QualityIssue(
                kind=quality.MISSING_SECTION,
                detail=f"현지어 사양 표 행 수가 한국어본과 다릅니다 "
                f"({len(specs)} / {len(copy_ko['specs'])})",
            ).model_dump()
        )

    local_options = [{"label": row.label, "values": row.values} for row in local.options]
    if [len(row["values"]) for row in local_options] != [len(row["values"]) for row in options]:
        #: 옵션값 개수가 어긋나면 재고 매트릭스와 맞지 않는다. 원문을 쓴다.
        local_options = options

    copy_local = {
        "name": culture.sanitize(rules, local.name.strip()),
        "usps": [culture.sanitize(rules, item.strip()) for item in local.usps if item.strip()],
        "sections": [
            culture.sanitize(rules, text.strip())
            for text in (local.intro, local.features, local.benefits, local.call_to_action)
        ],
        "specs": specs,
        "options": local_options,
    }
    for hit in culture.find(rules, quality.text_fields(copy_local)):
        issues.append(
            QualityIssue(
                kind=hit.term.kind,
                detail=f"현지어본 '{hit.term.term}' 표현 확인 필요 "
                f"({hit.term.reason}, 위치: {hit.field})",
                hard_block=hit.term.hard_block,
            ).model_dump()
        )

    return {"copy_local": copy_local, "quality_issues": issues}


# ── 조립 ────────────────────────────────────────────────────────────────


def build_content_graph():  # noqa: ANN201
    graph = StateGraph(ContentState)
    graph.add_node(DRAFT_KO, draft_ko)
    graph.add_node(CULTURE_FILTER, culture_filter)
    graph.add_node(QUALITY_CHECK, quality_check)
    graph.add_node(LOCALIZE, localize)

    graph.add_edge(START, DRAFT_KO)
    graph.add_edge(DRAFT_KO, CULTURE_FILTER)
    graph.add_edge(CULTURE_FILTER, QUALITY_CHECK)
    graph.add_conditional_edges(
        QUALITY_CHECK, _after_quality, {DRAFT_KO: DRAFT_KO, LOCALIZE: LOCALIZE}
    )
    graph.add_edge(LOCALIZE, END)
    return graph.compile()


def _to_draft(copy: dict, breadcrumb: list[str], options: list[dict]) -> PdpDraft:
    return PdpDraft(
        name=copy["name"],
        usps=copy["usps"],
        #: 소개·특징·혜택·구매유도. 프론트는 빈 줄로 단락을 나눈다.
        description="\n\n".join(section for section in copy["sections"] if section),
        specs=copy["specs"],
        breadcrumb=breadcrumb,
        options=options,
    )


async def run_content(command: ContentCommand) -> ContentResult:
    """runner 가 부른다. 그래프를 돌리고 계약 스키마로 바꾼다."""
    breadcrumb_ko, breadcrumb_local = breadcrumbs(command)
    state = await build_content_graph().ainvoke(
        {
            "command": command,
            "specs": base_specs(command),
            "regeneration_count": 0,
        },
        #: 초안 3회 + 검수 3회 + 현지화 1회를 넉넉히 넘기게
        {"recursion_limit": 25},
    )

    issues = [QualityIssue.model_validate(item) for item in state.get("quality_issues") or []]
    passed = bool(state.get("quality_passed")) and not any(item.hard_block for item in issues)
    copy_local = state.get("copy_local")
    return ContentResult(
        job_id=command.job_id,
        status=ContentStatus.DONE if passed else ContentStatus.NEEDS_REVIEW,
        ko=_to_draft(state["copy_ko"], breadcrumb_ko, option_rows(command)),
        local=_to_draft(copy_local, breadcrumb_local, copy_local["options"])
        if copy_local
        else None,
        locale=command.locale,
        quality_score=state.get("quality_score", 0),
        quality_issues=issues,
        regeneration_count=state.get("regeneration_count", 0),
        rules_version=culture.load(command.country).version,
    )
