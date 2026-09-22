"""정책 수집 목록이 ingest 가 읽을 수 있는 모양인지 고정.

필드 이름은 infra/models.py 의 RagDocument 컬럼과 맞춘다. 여기서 깨지면 적재가 깨진다.
"""

from __future__ import annotations

import datetime

import pytest
import yaml

from app.config import DATA_DIR

MANIFEST = DATA_DIR / "policies" / "manifest.yaml"

REQUIRED = {
    "doc_id",
    "country",
    "document_type",
    "title",
    "source_url",
    "publisher",
    "effective_from",
    "language",
    "review_status",
}
DOCUMENT_TYPES = {
    "PROHIBITED_LIST",
    "CUSTOMS",
    "TAX",
    "CERTIFICATION",
    "PLATFORM_POLICY",
    "RETURN_POLICY",
}


@pytest.fixture(scope="module")
def documents() -> list[dict]:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["documents"]


def test_문서마다_필수_필드가_있다(documents):
    for doc in documents:
        assert doc.keys() >= REQUIRED, f"{doc.get('doc_id')} 누락: {REQUIRED - doc.keys()}"


def test_doc_id는_중복되지_않는다(documents):
    ids = [doc["doc_id"] for doc in documents]
    assert len(ids) == len(set(ids))


def test_열거값과_시행일_형식(documents):
    for doc in documents:
        assert doc["document_type"] in DOCUMENT_TYPES, doc["doc_id"]
        assert doc["review_status"] in {"DRAFT", "VERIFIED"}, doc["doc_id"]
        assert doc["source_url"].startswith("https://"), doc["doc_id"]
        # YAML 이 날짜로 파싱하지 못했다면 형식이 틀린 것이다
        assert isinstance(doc["effective_from"], datetime.date), doc["doc_id"]


def test_VN_문서는_10건_이상(documents):
    assert sum(1 for doc in documents if doc["country"] == "VN") >= 10
