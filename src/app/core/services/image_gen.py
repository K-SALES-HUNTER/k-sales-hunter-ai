"""상품·상세 이미지 AI 생성 (화면 DTL-01-02).

1회 요청에 1장. 20~40초 걸려 잡으로 돌리고 프론트가 폴링한다.

입력
    참고 사진      사용자가 고른 보유 상품 사진 + 업로드한 레퍼런스
    생성 방식      기본 컷 / 모델 컷 (모델 컷은 기본 모델 4종 중 선택)
    요청 내용      자연어 한 문장

구현 메모
    OpenAI images.edit (gpt-image-1) 에 참조 이미지를 다중 입력한다. 1024x1024.
    mode=MODEL 이면 data/models.yaml 의 페르소나 문장을 프롬프트 앞에 붙인다.
    target=DETAIL 이면 인포그래픽·상세 컷 스타일 지시를 덧붙인다.
    비용이 장당 $0.05~0.2 이므로 일일 상한(DAILY_IMAGE_BUDGET)을 건다.

담당: 강근우 (콘텐츠 아키텍트 R-003)   상태: stub
"""

from __future__ import annotations

from app.contracts.v1 import ImageCommand, ImageResult


async def generate(command: ImageCommand) -> ImageResult:
    # TODO(강근우): OpenAI images.edit 호출 + 저장으로 교체
    return ImageResult(
        job_id=command.job_id,
        prompt=command.prompt,
        resolved_prompt=command.prompt,
    )
