"""Pydantic 계약 -> JSON Schema 파일.

백엔드는 이 파일로 DTO 를 만들거나 jsonschema2pojo 를 돌린다.
계약을 고치면 반드시 다시 돌려 커밋한다. 스키마 파일이 곧 합의문이다.

    make contracts
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.contracts.v1 import (  # noqa: E402
    AnalysisCommand,
    AnalysisResult,
    ContentCommand,
    ContentResult,
    CopilotRequest,
    CopilotResponse,
    ImageCommand,
    ImageResult,
    JobAccepted,
    JobState,
    ProductFillRequest,
    ProductFillResponse,
    QuoteRequest,
    QuoteResponse,
    SalesSuggestRequest,
    SalesSuggestResponse,
)
from app.contracts.v1.enums import ErrorCode  # noqa: E402

OUT_DIR = ROOT / "contracts" / "v1"

EXPORTS = {
    "analysis_command": AnalysisCommand,
    "analysis_result": AnalysisResult,
    "content_command": ContentCommand,
    "content_result": ContentResult,
    "image_command": ImageCommand,
    "image_result": ImageResult,
    "job_accepted": JobAccepted,
    "job_state": JobState,
    "product_fill_request": ProductFillRequest,
    "product_fill_response": ProductFillResponse,
    "quote_request": QuoteRequest,
    "quote_response": QuoteResponse,
    "sales_suggest_request": SalesSuggestRequest,
    "sales_suggest_response": SalesSuggestResponse,
    "copilot_request": CopilotRequest,
    "copilot_response": CopilotResponse,
}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for name, model in EXPORTS.items():
        #: by_alias -> JSON 은 camelCase 로 나간다
        schema = model.model_json_schema(by_alias=True)
        path = OUT_DIR / f"{name}.schema.json"
        path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  {path.relative_to(ROOT)}")

    #: 프론트는 자연어 메시지가 아니라 이 코드로 분기한다
    errors = {
        "schemaVersion": "1.0",
        "codes": [code.value for code in ErrorCode],
    }
    path = OUT_DIR / "error_codes.json"
    path.write_text(json.dumps(errors, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  {path.relative_to(ROOT)}")
    print(f"\n{len(EXPORTS) + 1}개 파일 생성. 백엔드에 공유한다.")


if __name__ == "__main__":
    main()
