import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import respx
from httpx import Response

from app.config import Settings, get_settings


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    env = {
        "SNOWFLAKE_ACCOUNT": "acct",
        "SNOWFLAKE_USER": "user",
        # Dummy PEM string — tests use mock_snowflake_client, so this
        # value is never actually parsed against snowflake-connector.
        "SNOWFLAKE_API_KEY": "test-private-key-pem",
        "SNOWFLAKE_WAREHOUSE": "wh",
        "SNOWFLAKE_DATABASE": "db",
        "SNOWFLAKE_SCHEMA": "schema",
        "SNOWFLAKE_ROLE": "role",
        "AC_API_URL": "https://example.test/api/3",
        "AC_API_KEY": "key",
        "REDIS_URL": "redis://localhost:6379/0",
        "SLACK_WEBHOOK_URL": "",
        "LIMIT_ACCOUNTS": "",
        "ENV": "test",
        "LOG_LEVEL": "INFO",
        "ACCOUNT_ID_MAP_PATH": "./data/account_id_map.csv",
        "GIT_SHA": "deadbee",
        # Lookup-service env vars; dummy values are fine because the
        # tests that exercise lookup_service mock the MCP call.
        "SERVICE_API_KEY": "test-service-key",
        "ZAPIER_MCP_URL": "https://mcp.example.test/zapier",
        "ZAPIER_MCP_TOKEN": "test-zapier-token",
        "LOOKUP_CACHE_TTL_SECONDS": "60",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    return Settings()


@pytest.fixture(autouse=True)
def _set_test_env(settings: Settings) -> Iterator[None]:
    yield
    get_settings.cache_clear()


@pytest.fixture
def fixture_json() -> Callable[[str], list[dict[str, Any]]]:
    def _loader(name: str) -> list[dict[str, Any]]:
        path = Path(__file__).parent / "fixtures" / name
        return json.loads(path.read_text(encoding="utf-8"))

    return _loader


@pytest.fixture
def mock_snowflake_client() -> Any:
    class MockSnowflakeClient:
        def __init__(self) -> None:
            self.responses: list[dict[str, Any]] = []

        async def execute(
            self, sql: str, params: dict[str, Any] | None = None
        ) -> list[dict[str, Any]]:
            del sql, params
            return self.responses

    return MockSnowflakeClient()


@pytest.fixture
def respx_mock_router() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        router.route().mock(return_value=Response(200, json={"ok": True}))
        yield router
