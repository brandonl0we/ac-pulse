import asyncio
import base64
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


_BASE64_BODY_RE = re.compile(r"^[A-Za-z0-9+/=\s]+$")


def _wrap_bare_base64_as_pem(value: str) -> str | None:
    """If the input looks like pure base64 (no markers, no other content),
    wrap it with standard PRIVATE KEY headers. This handles the case
    where the secret store stripped the BEGIN/END framing entirely.
    """
    body = re.sub(r"\s+", "", value)
    if not body or not _BASE64_BODY_RE.match(value):
        return None
    # Sanity check: must look like base64 of a reasonable key length.
    if len(body) < 100:
        return None
    wrapped = "\n".join(body[i : i + 64] for i in range(0, len(body), 64))
    return f"-----BEGIN PRIVATE KEY-----\n{wrapped}\n-----END PRIVATE KEY-----\n"


def _try_base64_decode_to_pem(value: str) -> str | None:
    """If the input is base64-encoded text whose decoded form is a PEM,
    return the decoded string. Handles the case where Spark base64-
    encoded the whole secret to preserve newlines.
    """
    stripped = re.sub(r"\s+", "", value)
    if not stripped or not _BASE64_BODY_RE.match(value):
        return None
    try:
        decoded = base64.b64decode(stripped, validate=True)
    except Exception:
        return None
    try:
        text = decoded.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if "BEGIN" in text and "PRIVATE KEY" in text:
        return text
    return None


def diagnose_pem_value(pem: str) -> dict[str, Any]:
    """Safe, no-secrets-leaked diagnostic for the SNOWFLAKE_API_KEY value.

    Returns shape/structure info without exposing the actual bytes.
    Used by /healthz when parsing fails so the operator can tell what
    went wrong without scraping container logs.
    """
    return {
        "length": len(pem),
        "has_begin_marker": "BEGIN" in pem,
        "has_end_marker": "END" in pem,
        "has_real_newlines": "\n" in pem,
        "has_literal_backslash_n": "\\n" in pem,
        "starts_with": pem[:20] if pem else "",
        "ends_with": pem[-20:] if len(pem) > 20 else "",
        "looks_like_pure_base64": bool(pem and _BASE64_BODY_RE.match(pem)),
    }


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
    bare_wrapped = _wrap_bare_base64_as_pem(pem)
    if bare_wrapped is not None:
        attempts.append(("wrapped-bare-base64", bare_wrapped))
    b64_decoded = _try_base64_decode_to_pem(pem)
    if b64_decoded is not None:
        attempts.append(("base64-decoded", b64_decoded))

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
    diag = diagnose_pem_value(pem)
    raise ValueError(
        f"Could not parse SNOWFLAKE_API_KEY as PEM after {len(attempts)} "
        f"attempts ({tried}). Diagnosis: {diag}. Last error: {last_error}"
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
