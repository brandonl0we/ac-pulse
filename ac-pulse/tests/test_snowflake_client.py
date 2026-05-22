from typing import Any

import pytest

from app.config import Settings
from app.snowflake_client import SnowflakeClient
from app.zapier_client import _extract_rows


@pytest.mark.asyncio
async def test_snowflake_client_uses_zapier_backend(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_execute_snowflake_sql(
        **kwargs: Any,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        captured.update(kwargs)
        return [{"account_id": 42, "churn_score": 0.91}], {"parsed_row_count": 1}

    monkeypatch.setattr("app.snowflake_client.execute_snowflake_sql", fake_execute_snowflake_sql)
    client = SnowflakeClient(settings.model_copy(update={"snowflake_backend": "zapier_mcp"}))

    rows = await client.execute(
        "SELECT * FROM account_state WHERE account_id = %(account_id)s",
        {"account_id": 42},
    )

    assert rows == [{"ACCOUNT_ID": 42, "CHURN_SCORE": 0.91}]
    assert captured["server_url"] == "https://mcp.example.test/zapier"
    assert captured["token"] == "test-zapier-token"
    assert captured["statement"] == "SELECT * FROM account_state WHERE account_id = 42"
    assert "Read-only Snowflake query" in captured["instructions"]


@pytest.mark.asyncio
async def test_snowflake_client_rejects_zapier_execute_many(settings: Settings) -> None:
    client = SnowflakeClient(settings.model_copy(update={"snowflake_backend": "zapier_mcp"}))

    with pytest.raises(NotImplementedError):
        await client.execute_many("INSERT INTO t VALUES (%(id)s)", [{"id": 1}])


@pytest.mark.asyncio
async def test_snowflake_client_requires_zapier_config(settings: Settings) -> None:
    client = SnowflakeClient(
        settings.model_copy(
            update={
                "snowflake_backend": "zapier_mcp",
                "zapier_mcp_url": None,
            }
        )
    )

    with pytest.raises(ValueError, match="ZAPIER_MCP_URL"):
        await client.execute("SELECT 1")


def test_extract_rows_unwraps_zapier_empty_result_wrapper() -> None:
    assert _extract_rows({"results": [{"rows": []}]}) == []
