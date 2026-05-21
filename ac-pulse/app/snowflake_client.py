import asyncio
from collections.abc import Mapping
from threading import Lock
from typing import Any, cast

import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from snowflake.connector import SnowflakeConnection

from app.config import Settings

_CONNECTION: SnowflakeConnection | None = None
_CONNECTION_LOCK = Lock()
# Cache the parsed DER key separately so we don't re-parse on every
# connection refresh — PEM→DER decoding is cheap but pointless to repeat.
_PRIVATE_KEY_DER: bytes | None = None
_PRIVATE_KEY_LOCK = Lock()


def _load_private_key_der(pem: str) -> bytes:
    """Convert a PEM-encoded RSA private key to PKCS8 DER bytes.

    snowflake-connector-python's `private_key` parameter expects DER. The
    PEM string we get from SNOWFLAKE_API_KEY may include actual newlines
    or the literal ``\\n`` token depending on how Fly.io / the local
    .env stores it — both are handled.
    """
    pem_text = pem.replace("\\n", "\n") if "\\n" in pem and "\n" not in pem else pem
    private_key = serialization.load_pem_private_key(
        pem_text.encode("utf-8"),
        password=None,
        backend=default_backend(),
    )
    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _get_private_key_der(settings: Settings) -> bytes:
    global _PRIVATE_KEY_DER
    with _PRIVATE_KEY_LOCK:
        if _PRIVATE_KEY_DER is None:
            _PRIVATE_KEY_DER = _load_private_key_der(settings.snowflake_private_key)
        return _PRIVATE_KEY_DER


def _get_connection(settings: Settings) -> SnowflakeConnection:
    global _CONNECTION
    with _CONNECTION_LOCK:
        if _CONNECTION is None or _CONNECTION.is_closed():
            connect_kwargs: dict[str, Any] = {
                "account": settings.snowflake_account,
                "user": settings.snowflake_user,
                "authenticator": "SNOWFLAKE_JWT",
                "private_key": _get_private_key_der(settings),
                "warehouse": settings.snowflake_warehouse,
                "database": settings.snowflake_database,
                "schema": settings.snowflake_schema,
            }
            if settings.snowflake_role:
                connect_kwargs["role"] = settings.snowflake_role
            _CONNECTION = snowflake.connector.connect(**connect_kwargs)
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
