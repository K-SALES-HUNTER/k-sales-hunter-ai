"""ai 스키마 테이블 정의.

[들어가는 것] AI 실행 상태와 운영 데이터
[들어가지 않는 것] users, products, orders, 그리고 분석 결과의 정본
                   분석 결과 정본은 Spring 이 검증 후 public 스키마에 저장한다.
                   아래 job_results 는 콜백 실패 시 임시 버퍼일 뿐이다.

[규칙] public 스키마 테이블을 FK 로 참조하지 않는다.
       job_id 는 그냥 숫자 컬럼이다. 배포 순서 의존을 없애기 위함이다.
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "ai"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)


class LLMCallLog(Base):
    """모든 LLM 호출 기록.

    1주차부터 넣는다. 나중에 소급이 안 되는데
    토큰 비용 관리 / 논문 정량 데이터 / 알고리즘 명세서 근거 / 프롬프트 A-B 비교
    네 가지에 전부 쓰인다.
    """

    __tablename__ = "llm_call_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    job_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    node: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(64))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RagDocument(Base):
    """정책 문서 청크 + 임베딩.

    별도 벡터 DB 없이 여기서 끝낸다.
    메타데이터와 임베딩이 같은 테이블에 있어 동기화 문제가 없다.
    """

    __tablename__ = "rag_documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    country: Mapped[str] = mapped_column(String(2), index=True)
    category_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_type: Mapped[str] = mapped_column(String(32))
    source_url: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(String(128), nullable=True)
    effective_from: Mapped[datetime] = mapped_column(Date)
    effective_to: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    language: Mapped[str] = mapped_column(String(8), default="vi")
    #: 임베딩 대상. 베트남어 원문을 적재 시점에 한국어로 1회 번역한 결과.
    content_ko: Mapped[str] = mapped_column(Text)
    #: 원문 보존. 출처 링크와 대조용. (R-004-08)
    content_origin: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    doc_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    #: DRAFT | VERIFIED. VERIFIED 만 최종 판매 가능 판정에 쓴다.
    review_status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "ix_rag_documents_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_rag_documents_filter", "country", "document_type", "effective_from"),
        {"schema": SCHEMA},
    )


class MarketDataCache(Base):
    """외부 시장 데이터 원본 응답. 재현성 + API 비용 절감."""

    __tablename__ = "market_data_cache"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    source_name: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSONB)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class JobResult(Base):
    """콜백 실패 시 결과 임시 보관.

    이게 없으면 Spring 이 잠깐 죽었을 때 몇 분짜리 LLM 결과와 토큰 비용이 함께 날아간다.
    Spring 은 GET /internal/ai/jobs/{jobId}/result 로 회수한다.
    """

    __tablename__ = "job_results"

    job_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    command_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvalRun(Base):
    """평가셋 실행. 논문과 산출물의 정량 근거."""

    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64))
    metrics: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, index=True)
    case_id: Mapped[str] = mapped_column(String(64))
    passed: Mapped[bool] = mapped_column(Boolean)
    detail: Mapped[dict] = mapped_column(JSONB)
