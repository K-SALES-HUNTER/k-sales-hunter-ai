"""환경 설정 한 곳.

[규칙] 환경변수를 os.getenv 로 직접 읽지 않는다. 전부 여기를 거친다.
       키를 추가하면 .env.example 에도 이름을 적는다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

#: 레포 루트. data/ · uploads/ · tests/fixtures 경로 기준점.
ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    log_level: str = "INFO"

    # 인프라
    postgres_url: str = "postgresql+psycopg://ai_service:ai_service_pw@localhost:5432/sales_hunter"
    redis_url: str = "redis://localhost:6379/0"

    # LLM
    #: fake 면 OPENAI_API_KEY 없이도 전 구간이 돈다. 테스트·오프라인 데모 기본값.
    llm_provider: str = "fake"
    openai_api_key: str = ""
    openai_model_main: str = "gpt-4o"
    openai_model_light: str = "gpt-4o-mini"
    openai_embed_model: str = "text-embedding-3-small"
    openai_image_model: str = "gpt-image-1"

    # 외부 데이터
    market_provider: str = "mock"
    tavily_api_key: str = ""
    fx_provider: str = "mock"
    exchange_rate_api_key: str = ""

    # 내부 통신
    internal_token: str = "dev-internal-token"
    spring_base_url: str = "http://localhost:8080"

    # dev_bff (Spring 완성 전 임시 백엔드)
    dev_bff_enabled: bool = True
    dev_bff_upload_dir: str = "./uploads"

    # 한도
    max_concurrent_jobs: int = 3
    job_timeout_sec: int = 480
    node_timeout_sec: int = 90
    llm_timeout_sec: int = 60
    daily_token_budget: int = 2_000_000
    daily_image_budget: int = 50

    @property
    def use_fake_llm(self) -> bool:
        """키가 없으면 provider 설정과 무관하게 fake 로 떨어진다.

        키를 빠뜨렸을 때 런타임 401 대신 결정론 응답으로 계속 돌게 한다.
        """
        return self.llm_provider == "fake" or not self.openai_api_key

    @property
    def upload_dir(self) -> Path:
        path = Path(self.dev_bff_upload_dir)
        return path if path.is_absolute() else ROOT_DIR / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
