import asyncio
import re
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


def _reconstruct_pem_framing(pem: str) -> str | None:
    """Rebuild a valid PEM string from one whose newlines were stripped
    or replaced with spaces.

    Spark/Fly/Heroku-style secret stores frequently mangle multi-line
    secrets:
      - newlines → single spaces
      - newlines → ``\\n`` literal tokens
      - newlines stripped entirely
    Any of these breaks PEM framing and yields MalformedFraming from
    cryptography. We extract the BEGIN/END markers, strip all whitespace
    from the base64 body, and re-emit a canonically-framed PEM (header
    line, 64-char body lines, footer line).

    Returns None when no BEGIN/END markers can be found — caller should
    treat that as "unrecoverable" and surface the original error.
    """
    match = re.search(
        r"-----BEGIN ([A-Z ]+?)-----(.+?)-----END \1-----",
        pem,
        re.DOTALL,
    )
    if not match:
        return None
    header_type = match.group(1).strip()
    body = re.sub(r"\s+", "", match.group(2))
    if not body:
        return None
    wrapped = "\n".join(body[i : i + 64] for i in range(0, len(body), 64))
    return f"-----BEGIN {header_type}-----\n{wrapped}\n-----END {header_type}-----\n"


def _load_private_key_der(pem: str) -> bytes:
    """Convert a PEM-encoded RSA private key to PKCS8 DER bytes.

    snowflake-connector-python expects DER. The PEM string from
    SNOWFLAKE_API_KEY may arrive in any of several mangled forms
    depending on how Spark stored it, so we try multiple normalizations
    in order before giving up.
    """
    attempts: list[tuple[str, str]] = [("as-is", pem)]
    if "\\n" in pem:
        attempts.append(("escaped-newlines", pem.replace("\\n", "\n")))
    reconstructed = _reconstruct_pem_framing(pem)
    if reconstructed is not None:
        attempts.append(("reconstructed-framing", reconstructed))

    last_error: Exception | None = None
    for _label, candidate in attempts:
        try:
            private_key = serialization.load_pem_private_key(
                candidate.encode("utf-8"),
                password=None,
                backend=default_backend(),
            )
            return private_key.private_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        except Exception as exc:
            last_error = exc
            continue

    tried = ", ".join(label for label, _ in attempts)
    raise ValueError(
        f"Could not parse SNOWFLAKE_API_KEY as PEM after {len(attempts)} "
        f"attempts ({tried}). Last error: {last_error}"
    ) from last_error


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
