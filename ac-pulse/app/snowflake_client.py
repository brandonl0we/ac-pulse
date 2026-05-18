import asyncio
from collections.abc import Mapping
from threading import Lock
from typing import Any, cast

import snowflake.connector
from snowflake.connector import SnowflakeConnection

from app.config import Settings

_CONNECTION: SnowflakeConnection | None = None
_CONNECTION_LOCK = Lock()


def _get_connection(settings: Settings) -> SnowflakeConnection:
    global _CONNECTION
    with _CONNECTION_LOCK:
        if _CONNECTION is None or _CONNECTION.is_closed():
            _CONNECTION = snowflake.connector.connect(
                account=settings.snowflake_account,
                user=settings.snowflake_user,
                password=settings.snowflake_password,
                warehouse=settings.snowflake_warehouse,
                database=settings.snowflake_database,
                role=settings.snowflake_role,
            )
    return _CONNECTION


class SnowflakeClient:
    def __init__(self, settings: Settings):
        self._settings = settings

    async def execute(
        self,
        sql: str,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._execute_sync, sql, params)

    def _execute_sync(
        self,
        sql: str,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        connection = _get_connection(self._settings)
        execute_params = cast(dict[str, Any] | None, dict(params) if params else None)
        with connection.cursor(snowflake.connector.DictCursor) as cursor:
            cursor.execute(sql, execute_params)
            rows = cursor.fetchall()
        return [dict(row) for row in rows]
