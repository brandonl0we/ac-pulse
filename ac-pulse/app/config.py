from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    snowflake_account: str = Field(alias="SNOWFLAKE_ACCOUNT")
    snowflake_user: str = Field(alias="SNOWFLAKE_USER")
    snowflake_password: str = Field(alias="SNOWFLAKE_PASSWORD")
    snowflake_warehouse: str = Field(alias="SNOWFLAKE_WAREHOUSE")
    snowflake_database: str = Field(alias="SNOWFLAKE_DATABASE")
    snowflake_role: str = Field(alias="SNOWFLAKE_ROLE")

    ac_api_url: str = Field(alias="AC_API_URL")
    ac_api_key: str = Field(alias="AC_API_KEY")

    redis_url: str = Field(alias="REDIS_URL")

    slack_webhook_url: str = Field(default="", alias="SLACK_WEBHOOK_URL")

    limit_accounts: int | None = Field(default=None, alias="LIMIT_ACCOUNTS")
    env: str = Field(default="development", alias="ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    account_id_map_path: Path = Field(alias="ACCOUNT_ID_MAP_PATH")
    git_sha: str | None = Field(default=None, alias="GIT_SHA")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
