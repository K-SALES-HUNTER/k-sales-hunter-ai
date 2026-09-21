"""전략 고도화 코파일럿 — AI 패널 (요구사항 R-005).

모든 2 Depth 화면 우측에 붙어 있고, 대화는 페이지를 옮겨도 이어진다.

설계
    gpt-4o 도구 호출로 답한다. 의도 분류를 위한 별도 LLM 호출을 두지 않는다.
    도구가 실제 숫자와 근거를 가져오므로 "가격 낮추면 마진 어떻게 돼?" 에 정확히 답할 수 있다.

    pricing_quote(price_krw, shipping_method)  가격을 바꿨을 때의 손익
    search_policy(country, query)              관세·규정 근거 문서
    get_report_section(section)                컨텍스트가 클 때 필요한 부분만

    보고서에 영향을 주는 명령은 3종뿐이다. 그 외 요청은 답변만 한다.
        ADD_COUNTRY        다른 국가 분석 추가
        REANALYZE          보고서 재생성
        REGENERATE_DETAIL  상세페이지 재생성
    명령이면 action 을 채워 돌려준다. 잡을 만드는 것은 Spring(또는 dev_bff) 이 한다.
    Python 이 직접 재실행하지 않는 이유는 버전 관리와 이력이 Spring 소유이기 때문이다.

    답변은 600자 이내. 프론트 패널 폭이 320px 다.

담당: 이동건   상태: stub (4주차 구현)
"""

from __future__ import annotations

from app.contracts.v1 import CopilotIntent, CopilotRequest, CopilotResponse

#: 프론트가 화면마다 보여주는 추천 프롬프트 12종. 골든 테스트 케이스로 쓴다.
GOLDEN_PROMPTS: dict[str, list[str]] = {
    "TOTAL_REPORT": ["필리핀도 분석해줘", "가장 마진 높은 국가?", "현지 경쟁사 가격대 알려줘"],
    "COUNTRY_REPORT": ["이 국가 관세 알려줘", "가격 낮추면 마진 어떻게 돼?", "경쟁사 대비 강점은?"],
    "SALES_INFO": ["추천 가격 근거 알려줘", "옵션 구성 추천해줘", "재고는 얼마나 준비할까?"],
    "DETAIL_PAGE": ["더 고급스럽게 만들어줘", "상품 정보 더 자세하게", "이 정보 반영해줘"],
    "SALES_OPS": ["요즘 판매 추세 어때?", "재고 얼마나 버틸까?", "가격 조정해도 될까?"],
}

_PLACEHOLDER = (
    "코파일럿은 아직 연결 전입니다. 4주차에 실제 답변으로 바뀝니다. "
    "보고서에 영향을 주는 요청은 재생성, 다른 국가 추가, 입력 정보 수정 세 가지입니다."
)


async def answer(request: CopilotRequest) -> CopilotResponse:
    # TODO(이동건): gpt-4o tool calling + agents.schemas.CopilotAnswer 로 교체
    return CopilotResponse(answer=_PLACEHOLDER, intent=CopilotIntent.QUERY)
