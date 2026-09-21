"""job_results 를 jobs 로 교체

콜백 방식을 버리고 폴링 방식으로 바꾼다.
Spring 이 GET 으로 상태와 결과를 가져가므로 잡 전체 생애를 한 테이블에 담는다.

llm_call_logs.job_id 도 BIGINT -> VARCHAR 로 바꾼다.
job_id 는 Spring 이 발번한 문자열이다 (예: a_12_1).

Revision ID: b1a2c3d4e5f6
Revises: baf7d117a48e
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b1a2c3d4e5f6"
down_revision: str | Sequence[str] | None = "baf7d117a48e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("job_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("step", sa.String(length=24), nullable=True),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("trace_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column(
            "country_states",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "request",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("llm_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("job_id"),
        schema="ai",
    )
    op.create_index(op.f("ix_ai_jobs_job_type"), "jobs", ["job_type"], schema="ai")
    op.create_index(op.f("ix_ai_jobs_status"), "jobs", ["status"], schema="ai")

    op.drop_table("job_results", schema="ai")

    op.alter_column(
        "llm_call_logs",
        "job_id",
        existing_type=sa.BigInteger(),
        type_=sa.String(length=64),
        existing_nullable=True,
        postgresql_using="job_id::varchar",
        schema="ai",
    )


def downgrade() -> None:
    op.alter_column(
        "llm_call_logs",
        "job_id",
        existing_type=sa.String(length=64),
        type_=sa.BigInteger(),
        existing_nullable=True,
        postgresql_using="job_id::bigint",
        schema="ai",
    )

    op.create_table(
        "job_results",
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("command_id", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("delivered", sa.Boolean(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("job_id"),
        schema="ai",
    )

    op.drop_index(op.f("ix_ai_jobs_status"), table_name="jobs", schema="ai")
    op.drop_index(op.f("ix_ai_jobs_job_type"), table_name="jobs", schema="ai")
    op.drop_table("jobs", schema="ai")
