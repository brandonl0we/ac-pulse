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
        "SNOWFLAKE_PASSWORD": "pass",
        "SNOWFLAKE_WAREHOUSE": "wh",
        "SNOWFLAKE_DATABASE": "db",
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
