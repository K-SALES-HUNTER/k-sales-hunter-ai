"""이미지 생성 잡 계약 (상품 컷 / 상세 컷).

프론트 GenerateImageParams 와 1:1. 1회 요청에 1장을 만든다.
"""

from __future__ import annotations

from pydantic import Field

from app.contracts.v1.base import SCHEMA_VERSION, CamelModel
from app.contracts.v1.enums import ImageMode, ImageTarget


class ImageCommand(CamelModel):
    schema_version: str = SCHEMA_VERSION
    job_id: str
    trace_id: str = ""
    target: ImageTarget = ImageTarget.DETAIL
    #: 사용자가 자연어로 적은 요청 내용
    prompt: str
    mode: ImageMode = ImageMode.BASIC
    #: mode=MODEL 일 때 고른 기본 모델. data/models.yaml 의 키.
    model_id: str | None = None
    #: 참고 사진 URL (보유 사진 + 업로드 레퍼런스)
    reference_urls: list[str] = Field(default_factory=list)


class ImageResult(CamelModel):
    schema_version: str = SCHEMA_VERSION
    job_id: str
    image_url: str = ""
    #: 결과 화면 '요청 내용 요약'에 표시
    prompt: str = ""
    #: 페르소나·스타일 지시가 붙은 실제 전송 프롬프트. 디버그용.
    resolved_prompt: str = ""
