"""내부 API — 상세페이지 수정본 재번역 (POST /internal/ai/content/retranslate).

Spring 의 PATCH .../detail-page/content {retranslate: true} 가 부른다.
FakeLLM 은 tests/fixtures/llm/TranslatedText.json 을 돌려준다.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    from app.config import get_settings
    from app.entrypoints import http

    app = FastAPI()
    app.include_router(http.internal)
    return TestClient(app, headers={"X-Internal-Token": get_settings().internal_token})


def test_수정본을_현지어로_옮겨_준다(client: TestClient):
    res = client.post(
        "/internal/ai/content/retranslate",
        json={
            "country": "vn",
            "locale": "vi",
            "name": "포근한 캐릭터 인형",
            "description": "부드러운 촉감의 캐릭터 인형입니다.",
            "previousName": "Gấu bông nhân vật",
            "previousDescription": "",
        },
    )

    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"name", "description"}
    assert body["name"]


def test_필수값이_없으면_422(client: TestClient):
    res = client.post("/internal/ai/content/retranslate", json={"country": "VN", "locale": "vi"})

    assert res.status_code == 422
