"""전략 고도화 코파일럿 — AI 패널 (요구사항 R-005).

모든 2 Depth 화면 우측에 붙어 있고, 대화는 페이지를 옮겨도 이어진다.

설계
    gpt-4o 도구 호출로 답한다. 의도 분류를 위한 별도 LLM 호출을 두지 않는다.
    도구 목록과 구조화 출력(CopilotAnswer)을 한 호출에 같이 넘긴다.
    도구가 더 필요 없으면 그 호출이 바로 구조화 답변을 낸다.

    pricing_quote(price_krw, shipping_method)  가격을 바꿨을 때의 손익 (마진 엔진, LLM 아님)
    search_policy(query)                       관세·규정 근거 문서 (pgvector)
    get_report_section(section)                컨텍스트가 클 때 필요한 부분만

    보고서에 영향을 주는 명령은 3종뿐이다. 그 외 요청은 답변만 한다.
    명령이면 action 을 채워 돌려준다. 잡을 만드는 것은 Spring 이 한다.
    Python 이 직접 재실행하지 않는 이유는 버전 관리와 이력이 Spring 소유이기 때문이다.

    답변은 600자 이내. 프론트 패널 폭이 320px 다.

담당: 이동건 (전략 고도화 코파일럿 R-005)
"""

from __future__ import annotations

import json

from app.config import get_settings
from app.contracts.v1 import (
    COUNTRY_NAMES,
    CopilotAction,
    CopilotActionPlan,
    CopilotIntent,
    CopilotRequest,
    CopilotResponse,
    ErrorCode,
    QuoteRequest,
)
from app.core.agents import prompts
from app.core.agents.schemas import CopilotAnswer
from app.core.services import pricing_quote
from app.errors import ServiceError
from app.infra.llm import build_json_schema

#: 프론트가 화면마다 보여주는 추천 프롬프트 12종. 골든 테스트 케이스로 쓴다.
GOLDEN_PROMPTS: dict[str, list[str]] = {
    "TOTAL_REPORT": ["필리핀도 분석해줘", "가장 마진 높은 국가?", "현지 경쟁사 가격대 알려줘"],
    "COUNTRY_REPORT": ["이 국가 관세 알려줘", "가격 낮추면 마진 어떻게 돼?", "경쟁사 대비 강점은?"],
    "SALES_INFO": ["추천 가격 근거 알려줘", "옵션 구성 추천해줘", "재고는 얼마나 준비할까?"],
    "DETAIL_PAGE": ["더 고급스럽게 만들어줘", "상품 정보 더 자세하게", "이 정보 반영해줘"],
    "SALES_OPS": ["요즘 판매 추세 어때?", "재고 얼마나 버틸까?", "가격 조정해도 될까?"],
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "pricing_quote",
            "description": "가격·배송방식을 바꿨을 때의 순이익·마진율·BEP 를 즉시 계산한다",
            "parameters": {
                "type": "object",
                "properties": {
                    "price_krw": {"type": "integer"},
                    "shipping_method": {"type": "string", "enum": ["DIRECT", "SLS"]},
                },
                "required": ["price_krw"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_policy",
            "description": "현재 국가의 통관·관세·규정 근거 문서를 검색한다 (출처·기준일 포함)",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_report_section",
            "description": "현재 화면 보고서에서 필요한 부분만 가져온다",
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "enum": ["scores", "competition", "pricing", "risk"],
                    }
                },
                "required": ["section"],
            },
        },
    },
]
ACTION_TEXT = {
    CopilotAction.ADD_COUNTRY: "{country} 분석을 시작했어요",
    CopilotAction.REANALYZE: "보고서를 다시 분석하고 있어요",
    CopilotAction.REGENERATE_DETAIL: "{country} 상세페이지를 다시 만들고 있어요",
}
MAX_TOOL_ROUNDS = 3
MAX_ANSWER_CHARS = 600

_PLACEHOLDER = "코파일럿이 오프라인 모드입니다. OPENAI_API_KEY 를 설정하면 실제 답변으로 바뀝니다."


async def answer(req: CopilotRequest) -> CopilotResponse:
    """AI 패널 질문 하나에 답한다.

    흐름
        1. 시스템 프롬프트(화면 종류·브랜드 톤) + 최근 10턴 + 이번 질문으로 메시지를 만든다
        2. gpt-4o 에 도구 목록과 응답 스키마(CopilotAnswer)를 함께 준다
        3. 도구를 부르면 실행 결과를 붙여 다시 묻는다 (최대 3회)
        4. 도구가 더 필요 없으면 같은 호출이 스키마에 맞춘 최종 답을 낸다
        5. 명령 3종이면 action 을 만들어 돌려준다. 잡 생성은 Spring 이 한다
    """
    settings = get_settings()
    if settings.use_fake_llm:  # 키가 없으면 결정론 응답 (테스트·오프라인 데모)
        return CopilotResponse(answer=_PLACEHOLDER, intent=CopilotIntent.QUERY)

    from openai import AsyncOpenAI

    openai = AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.llm_timeout_sec)
    prompt = prompts.load("copilot")  # 600자 · 숫자는 도구 결과만
    messages: list[dict] = [
        {"role": "system", "content": prompt.format(page=req.page.value, brand=req.market_profile)},
        *[
            {"role": "assistant" if t.role == "ai" else "user", "content": t.text}
            for t in req.history[-10:]
        ],
        {"role": "user", "content": req.message},
    ]
    sources: list[dict] = []
    for _ in range(MAX_TOOL_ROUNDS + 1):  # 도구가 필요 없어지면 같은 호출이 구조화 답변을 낸다
        resp = await openai.chat.completions.create(
            model=settings.openai_model_main,
            messages=messages,
            tools=TOOLS,
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": build_json_schema(CopilotAnswer),
            },
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            final = CopilotAnswer.model_validate_json(msg.content or "{}")
            break
        messages.append(msg.model_dump(exclude_none=True))
        for call in msg.tool_calls:
            out = await _run_tool(
                call.function.name, json.loads(call.function.arguments), req, sources
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(out, ensure_ascii=False, default=str),
                }
            )
    else:
        raise ServiceError("도구 호출 한도 초과", code=ErrorCode.COPILOT_INTENT_UNCLEAR)

    action = None
    # LLM 이 명령 3종 밖의 값을 내면 무시한다 (보고서를 바꾸는 행동은 정해진 3종뿐)
    if final.action_type in CopilotAction.__members__:  # 명령 3종만. 잡 생성은 Spring 이 한다
        kind = CopilotAction(final.action_type)
        country = COUNTRY_NAMES.get(final.action_country, final.action_country)
        action = CopilotActionPlan(
            type=kind,
            params={"country": final.action_country},
            description=ACTION_TEXT[kind].format(country=country),
        )
    intent = final.intent if final.intent in CopilotIntent.__members__ else "QUERY"
    return CopilotResponse(
        answer=final.answer[:MAX_ANSWER_CHARS],
        intent=CopilotIntent(intent),
        action=action,
        sources=sources,
    )


async def _run_tool(name: str, args: dict, req: CopilotRequest, sources: list[dict]):  # noqa: ANN202
    """LLM 이 고른 도구를 실행한다. 숫자는 여기서만 나온다 (LLM 은 이 결과를 인용만 한다).

    country_code 가 없는 화면(글로벌 보고서)에서는 1순위 시장인 VN 으로 계산한다.
    search_policy 의 출처는 sources 에 모아 응답에 같이 싣는다 (R-004-08 근거 표시).
    """
    country = req.country_code or "VN"
    if name == "pricing_quote":  # 숫자는 마진 엔진이 계산한다
        if req.product is None:
            return {"error": "상품 정보가 없어 계산할 수 없습니다"}
        result = await pricing_quote.quote(
            QuoteRequest(
                country=country,
                supply_cost_krw=req.product.supply_cost_krw,
                weight_g=req.product.weight_g,
                packaging=req.product.packaging,
                **args,
            )
        )
        return result.model_dump(by_alias=True, mode="json")["quote"]
    if name == "search_policy":
        from app.core.rag import retriever

        hits = await retriever.search(country=country, query=args["query"], top_k=3)
        sources += [
            {"source": h.publisher, "url": h.source_url, "effectiveFrom": h.effective_from}
            for h in hits
        ]
        return [h.content_ko for h in hits]
    return req.context.get(args.get("section", ""))
