"""Alembic 환경 설정.

[핵심] 이 마이그레이션은 ai 스키마만 본다.
       안 하면 Spring(Flyway)이 만든 public 테이블을 지우는 마이그레이션이
       자동 생성된다. 한 번 터지면 복구가 오래 걸린다.

[핵심] LangGraph checkpoint 테이블은 라이브러리가 직접 만든다.
       autogenerate 대상에서 빼지 않으면 매번 DROP 을 제안한다.

[규칙] ai 스키마는 public 테이블을 FK 로 참조하지 않는다.
       job_id 는 그냥 숫자 컬럼이다. 배포 순서 의존을 없애기 위함이다.
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

# .env 를 먼저 읽는다. 없으면 OS 환경변수를 쓴다.
load_dotenv()

# 1. src 디렉토리를 파이썬 패스에 추가하여 models.py 모듈을 불러올 수 있게 설정
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# 2. 파이썬 ORM 모델의 Base 가져오기
from app.infra.models import SCHEMA, Base  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# alembic.ini 대신 .env 의 POSTGRES_URL 을 쓴다.
# DB 비밀번호를 alembic.ini 에 적어 커밋하지 않기 위함이다.
# %% 이스케이프는 ConfigParser 가 % 를 보간 문자로 해석하는 것을 막는다.
_url = os.getenv("POSTGRES_URL")
if _url:
    config.set_main_option("sqlalchemy.url", _url.replace("%", "%%"))

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 3. Alembic이 인식할 target_metadata 설정
target_metadata = Base.metadata

#: LangGraph 가 직접 만드는 테이블. Alembic 이 건드리면 안 된다.
LANGGRAPH_TABLES = {
    "checkpoints",
    "checkpoint_writes",
    "checkpoint_blobs",
    "checkpoint_migrations",
}


def include_object(obj, name, type_, reflected, compare_to) -> bool:  # noqa: ANN001
    """ai 스키마의 우리 테이블만 autogenerate 대상으로 삼는다."""
    if type_ == "table":
        if name in LANGGRAPH_TABLES:
            return False
        return getattr(obj, "schema", None) == SCHEMA
    return True


def render_item(type_, obj, autogen_context):  # noqa: ANN001, ANN201
    """pgvector 의 Vector 타입에 import 문을 함께 찍는다.

    이게 없으면 생성된 마이그레이션이 NameError: name 'pgvector' is not defined 로 죽는다.
    """
    if type_ == "type" and obj.__class__.__module__.startswith("pgvector"):
        autogen_context.imports.add("import pgvector.sqlalchemy")
        return f"pgvector.sqlalchemy.Vector({obj.dim})"
    return False


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema=SCHEMA,
        include_object=include_object,
        render_item=render_item,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        # 연결이 안 될 때 무한 대기하지 않고 5초 만에 실패한다.
        connect_args={"connect_timeout": 5},
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema=SCHEMA,
            include_object=include_object,
            render_item=render_item,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
