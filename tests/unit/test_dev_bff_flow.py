"""dev_bff 전 구간 — 등록 → 분석 → 판매 정보 → 상세 페이지 생성·수정.

시연 막 2 → 막 6 을 프론트 대신 HTTP 로 따라간다. Postgres 대신 memory_store 를 쓴다.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI

from app.entrypoints import dev_bff

pytestmark = pytest.mark.usefixtures("memory_store")

BASE = "/api/v1"


@pytest.fixture
async def client():  # noqa: ANN201
    app = FastAPI()
    app.include_router(dev_bff.router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


async def _poll(client: httpx.AsyncClient, path: str, *, done) -> httpx.Response:  # noqa: ANN001
    """프론트처럼 다시 부른다. 잡은 같은 이벤트 루프에서 돈다."""
    for _ in range(200):
        response = await client.get(path)
        if done(response):
            return response
        await asyncio.sleep(0.02)
    raise AssertionError(f"{path} 가 끝나지 않았다: {response.text}")


async def test_등록부터_상세페이지_수정까지(client: httpx.AsyncClient):
    created = await client.post(
        f"{BASE}/products",
        json={
            "name": "말랑 프렌즈 캐릭터 인형",
            "category": "캐릭터·굿즈",
            "costPrice": 11500,
            "weight": 250,
        },
    )
    assert created.status_code == 201
    product_id = created.json()["productId"]
    country = f"{BASE}/products/{product_id}/countries/VN"

    await _poll(
        client,
        f"{BASE}/products/{product_id}/analysis",
        done=lambda r: r.json()["status"] == "COMPLETED",
    )

    # ── 막 5 · 판매 정보 ─────────────────────────────────
    early = await client.post(f"{country}/detail-page")
    assert early.status_code == 409

    info = (await client.get(f"{country}/sales-info")).json()
    assert info["shopeeCategoryDefault"] == "toys-plush"
    assert len(info["priceScenarios"]) == 3
    assert info["optionLevel1"]["label"] == "제공 색상"
    assert {attr["key"] for attr in info["categoryAttrs"]} >= {"brand", "character", "origin"}

    option1, option2 = info["optionLevel1"], info["optionLevel2"]
    stock = [
        {"option1": a, "option2": b, "qty": 20}
        for a in option1["values"]
        for b in option2["values"]
    ]
    saved = await client.put(
        f"{country}/sales-info",
        json={
            "category": info["shopeeCategoryDefault"],
            "finalPrice": 28900,
            "shippingMethod": "sls",
            "attrs": {attr["key"]: attr["value"] for attr in info["categoryAttrs"]},
            "option1": option1,
            "option2": option2,
            "stock": stock,
        },
    )
    assert saved.status_code == 200
    card = (await client.get(f"{BASE}/products/{product_id}")).json()
    assert next(c for c in card["countries"] if c["code"] == "VN")["stage"] == "sales-info"

    # ── 막 6 · 상세 페이지 ───────────────────────────────
    job = await client.post(f"{country}/detail-page")
    assert job.status_code == 202
    page = await _poll(client, f"{country}/detail-page", done=lambda r: r.status_code == 200)
    body = page.json()

    assert body["status"] == "DONE"
    ko, local = body["content"]["ko"], body["content"]["local"]
    assert ko["breadcrumb"][0] == "홈" and local["breadcrumb"][0] == "Trang chủ"
    assert ko["price"].startswith("₫") and "," in ko["price"]
    assert local["price"].startswith("₫") and "." in local["price"]
    assert local["shipping"]["fee"] == "Miễn phí vận chuyển · Shopee SLS"
    assert local["stockNote"] == "Còn 160 sản phẩm"
    assert ko["options"][0]["label"] == "색상"

    edited = await client.patch(
        f"{country}/detail-page/content",
        json={"name": "말랑 프렌즈 인형 (수정)", "description": "셀러가 고친 설명"},
    )
    assert edited.status_code == 200
    edited_body = edited.json()
    assert edited_body["edited"] is True
    assert edited_body["content"]["ko"]["name"] == "말랑 프렌즈 인형 (수정)"
    assert edited_body["content"]["local"]["name"].startswith("Gấu Bông")

    card = (await client.get(f"{BASE}/products/{product_id}")).json()
    assert next(c for c in card["countries"] if c["code"] == "VN")["stage"] == "detail"
