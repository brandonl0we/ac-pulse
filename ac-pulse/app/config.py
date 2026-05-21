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

    # Snowflake JWT (key-pair) auth — the canonical AC path.
    # Defaults match the official DEAL_CONDUCTOR_SVC user on FM00411.
    # The private key (PEM-encoded) comes from SNOWFLAKE_API_KEY; it's
    # the only secret that must be set. Everything else has a sane
    # default but can be overridden via env.
    snowflake_account: str = Field(default="FM00411", alias="SNOWFLAKE_ACCOUNT")
    snowflake_user: str = Field(default="DEAL_CONDUCTOR_SVC", alias="SNOWFLAKE_USER")
    snowflake_private_key: str = Field(alias="SNOWFLAKE_API_KEY")
    snowflake_warehouse: str = Field(default="AC_CONSOLIDATED", alias="SNOWFLAKE_WAREHOUSE")
    snowflake_database: str = Field(default="AC", alias="SNOWFLAKE_DATABASE")
    snowflake_schema: str = Field(default="CONFORMED_DIMENSIONS", alias="SNOWFLAKE_SCHEMA")
    # Role is optional — when unset, Snowflake uses the user's default role.
    snowflake_role: str | None = Field(default=None, alias="SNOWFLAKE_ROLE")

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
