"""이미지 AI 생성 (DTL-01-02) — 프롬프트 조립 · fake 생성 · 캐시 · 일일 상한 · 취소."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.config import get_settings
from app.contracts.v1 import ImageCommand, ImageMode, ImageTarget, JobStatus
from app.core.jobs import runner, store
from app.core.services import image_gen
from app.errors import BudgetExceeded, ServiceError

PNG = b"\x89PNG\r\n\x1a\nreference"


@pytest.fixture
def uploads(tmp_path, monkeypatch):  # noqa: ANN001, ANN201
    """업로드 폴더를 임시 폴더로. 참고 사진 1장을 넣어 둔다."""
    settings = get_settings()
    monkeypatch.setattr(settings, "dev_bff_upload_dir", str(tmp_path))
    (tmp_path / "ref.png").write_bytes(PNG)
    return tmp_path


def _command(**override) -> ImageCommand:  # noqa: ANN003
    values = {
        "job_id": "i_1_1",
        "prompt": "베리(퍼플) 캐릭터 단독 컷, 밝은 회색 배경",
        "reference_urls": ["/api/v1/uploads/ref.png"],
    }
    values.update(override)
    return ImageCommand(**values)


# ── 프롬프트 ────────────────────────────────────────────────────────────


def test_모델컷은_페르소나를_붙인다():
    prompt = image_gen.build_prompt(
        _command(mode=ImageMode.MODEL, model_id="model-3", target=ImageTarget.PRODUCT)
    )
    assert "Southeast Asian woman" in prompt
    assert "thumbnail" in prompt
    assert prompt.endswith("밝은 회색 배경")


def test_기본컷은_사람을_빼고_가드레일을_붙인다():
    prompt = image_gen.build_prompt(_command())
    assert "no people" in prompt
    assert "Do not add any text" in prompt
    assert "Model:" not in prompt


# ── 생성 ────────────────────────────────────────────────────────────────


async def test_fake_모드는_첫_참고사진을_결과로_쓰고_두번째는_캐시다(uploads):  # noqa: ANN001
    first = await image_gen.generate(_command())
    assert first.image_url.startswith("/api/v1/uploads/gen_")
    assert not first.cached
    saved = uploads / first.image_url.rsplit("/", 1)[1]
    assert saved.read_bytes() == PNG

    again = await image_gen.generate(_command(job_id="i_1_2"))
    assert again.cached and again.image_url == first.image_url


async def test_참고사진이_없으면_fake_모드는_실패한다(uploads):  # noqa: ANN001
    with pytest.raises(ServiceError):
        await image_gen.generate(_command(reference_urls=["/api/v1/uploads/none.png"]))


@pytest.fixture
def real_mode(monkeypatch):  # noqa: ANN001, ANN201
    """API 키가 있는 것처럼. 실제 호출 대신 고정 바이트를 돌려준다."""
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    #: Redis 가 없을 때의 프로세스 내 카운터를 탄다 (연결 시도 자체를 막아 빠르게)
    import redis.asyncio

    def no_redis(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise ConnectionError("테스트에서는 Redis 를 쓰지 않는다")

    monkeypatch.setattr(redis.asyncio, "from_url", no_redis)
    monkeypatch.setattr(image_gen, "_local_budget", {})
    calls: list[tuple] = []

    async def fake_call(prompt, references):  # noqa: ANN001, ANN202
        calls.append((prompt, references))
        return b"generated"

    monkeypatch.setattr(image_gen, "_call_openai", fake_call)
    return calls


async def test_참고사진을_함께_보내고_일일_상한을_지킨다(uploads, real_mode, monkeypatch):  # noqa: ANN001
    monkeypatch.setattr(get_settings(), "daily_image_budget", 1)

    result = await image_gen.generate(_command())
    assert (uploads / result.image_url.rsplit("/", 1)[1]).read_bytes() == b"generated"
    _, references = real_mode[0]
    assert references == [("ref.png", PNG)]

    with pytest.raises(BudgetExceeded):
        await image_gen.generate(_command(prompt="다른 요청"))


# ── 취소 ────────────────────────────────────────────────────────────────


async def _wait_terminal(job_id: str) -> JobStatus:
    for _ in range(200):
        state = await store.get(job_id)
        if state.status.is_terminal:
            return state.status
        await asyncio.sleep(0.01)
    raise AssertionError("잡이 끝나지 않았다")


@pytest.mark.usefixtures("memory_store")
async def test_생성_중_취소하면_바로_끊는다(uploads, monkeypatch):  # noqa: ANN001
    started = asyncio.Event()

    async def slow(command):  # noqa: ANN001, ANN202
        started.set()
        await asyncio.sleep(30)

    monkeypatch.setattr(image_gen, "generate", slow)
    await runner.submit_image(_command(job_id="i_cancel_1"))
    await asyncio.wait_for(started.wait(), 1)

    await runner.cancel("i_cancel_1")
    assert await asyncio.wait_for(_wait_terminal("i_cancel_1"), 2) is JobStatus.CANCELLED


@pytest.mark.usefixtures("memory_store")
async def test_대기_중에_취소하면_시작하지_않는다(uploads, monkeypatch):  # noqa: ANN001
    called = []

    async def never(command):  # noqa: ANN001, ANN202
        called.append(command)

    monkeypatch.setattr(image_gen, "generate", never)
    await runner.submit_image(_command(job_id="i_cancel_2"))
    #: 태스크가 돌기 전에 취소한다 (QUEUED)
    await runner.cancel("i_cancel_2")

    assert await _wait_terminal("i_cancel_2") is JobStatus.CANCELLED
    assert called == []


# ── dev_bff ─────────────────────────────────────────────────────────────


@pytest.mark.usefixtures("memory_store")
async def test_상세페이지에서_이미지를_생성해_저장한다(uploads):  # noqa: ANN001
    from fastapi import FastAPI

    from app.entrypoints import dev_bff
    from tests.unit.test_dev_bff_flow import BASE, _poll

    app = FastAPI()
    app.include_router(dev_bff.router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        uploaded = (
            await client.post(f"{BASE}/uploads/images", files={"file": ("a.png", PNG)})
        ).json()
        assert (await client.get(uploaded["url"])).content == PNG

        product_id = (
            await client.post(
                f"{BASE}/products",
                json={
                    "name": "말랑 프렌즈 캐릭터 인형",
                    "category": "캐릭터·굿즈",
                    "costPrice": 11500,
                    "weight": 250,
                    "imageUrls": [uploaded["url"]],
                },
            )
        ).json()["productId"]
        country = f"{BASE}/products/{product_id}/countries/VN"
        await _poll(
            client,
            f"{BASE}/products/{product_id}/analysis",
            done=lambda r: r.json()["status"] == "COMPLETED",
        )
        info = (await client.get(f"{country}/sales-info")).json()
        await client.put(
            f"{country}/sales-info",
            json={
                "category": info["shopeeCategoryDefault"],
                "finalPrice": 28900,
                "option1": info["optionLevel1"],
                "option2": info["optionLevel2"],
            },
        )
        await client.post(f"{country}/detail-page")
        page = (
            await _poll(client, f"{country}/detail-page", done=lambda r: r.status_code == 200)
        ).json()
        assert page["productImages"][0]["src"] == uploaded["url"]
        assert page["mainImageId"] == page["productImages"][0]["id"]

        job_id = (
            await client.post(
                f"{country}/detail-page/images/generate",
                json={
                    "target": "detail",
                    "prompt": "베리 단독 컷",
                    "mode": "model",
                    "modelId": "model-1",
                    "referenceIds": [page["productImages"][0]["id"]],
                },
            )
        ).json()["jobId"]
        job = (
            await _poll(
                client,
                f"{BASE}/image-jobs/{job_id}",
                done=lambda r: r.json()["status"] != "RUNNING",
            )
        ).json()
        assert job["status"] == "DONE"
        assert (await client.get(job["result"]["src"])).status_code == 200

        saved = (
            await client.post(
                f"{country}/detail-page/images/generated",
                json={"generatedImageId": job_id, "target": "detail"},
            )
        ).json()
        assert saved["label"] == "상세 이미지 1"
        page = (await client.get(f"{country}/detail-page")).json()
        assert [item["id"] for item in page["detailImages"]] == [saved["id"]]
