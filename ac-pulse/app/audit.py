import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import structlog

from app.snowflake_client import SnowflakeClient

logger = structlog.get_logger(__name__)
_BATCH_SIZE = 500
_BUFFER: list[dict[str, Any]] = []
_BUFFER_LOCK = asyncio.Lock()
_SNOWFLAKE_CLIENT: SnowflakeClient | None = None


def configure_audit(snowflake_client: SnowflakeClient) -> None:
    global _SNOWFLAKE_CLIENT
    _SNOWFLAKE_CLIENT = snowflake_client


async def log_write(
    run_id: str,
    account_id: int,
    field_name: str,
    old_value: Any,
    new_value: Any,
    status: str,
    error_message: str | None = None,
) -> None:
    if _SNOWFLAKE_CLIENT is None:
        logger.warning("audit_write_skipped_no_client", run_id=run_id, account_id=account_id)
        return

    row = {
        "run_id": run_id,
        "event_ts": datetime.now(UTC).isoformat(),
        "account_id": account_id,
        "field_name": field_name,
        "old_value": _stringify_value(old_value),
        "new_value": _stringify_value(new_value),
        "status": status,
        "error_message": error_message,
    }

    async with _BUFFER_LOCK:
        _BUFFER.append(row)
        if len(_BUFFER) < _BATCH_SIZE:
            return
        rows = _drain_buffer()

    await _flush_rows(rows)


async def flush_audit_logs() -> None:
    if _SNOWFLAKE_CLIENT is None:
        return
    async with _BUFFER_LOCK:
        if not _BUFFER:
            return
        rows = _drain_buffer()
    await _flush_rows(rows)


async def get_recent_audit_rows(limit: int = 100) -> list[dict[str, Any]]:
    if _SNOWFLAKE_CLIENT is None:
        return []
    sql = f"""
SELECT
    run_id,
    event_ts,
    account_id,
    field_name,
    old_value,
    new_value,
    status,
    error_message
FROM CS_ANALYTICS.AC_PULSE_AUDIT_LOG
ORDER BY event_ts DESC
FETCH NEXT {limit} ROWS ONLY
"""
    return await _SNOWFLAKE_CLIENT.execute(sql)


async def get_audit_rows_for_run(run_id: str) -> list[dict[str, Any]]:
    if _SNOWFLAKE_CLIENT is None:
        return []
    escaped_run_id = _escape_sql_string(run_id)
    sql = f"""
SELECT
    run_id,
    event_ts,
    account_id,
    field_name,
    old_value,
    new_value,
    status,
    error_message
FROM CS_ANALYTICS.AC_PULSE_AUDIT_LOG
WHERE run_id = {escaped_run_id}
ORDER BY event_ts DESC
"""
    return await _SNOWFLAKE_CLIENT.execute(sql)


async def get_last_success_by_worker() -> dict[str, str | None]:
    if _SNOWFLAKE_CLIENT is None:
        return {"nightly": None, "monthly": None, "weekly_snapshot": None, "on_demand": None}

    sql = """
SELECT
    SPLIT_PART(run_id, '-', 1) AS worker_name,
    MAX(event_ts) AS last_success_ts
FROM CS_ANALYTICS.AC_PULSE_AUDIT_LOG
WHERE status = 'success'
GROUP BY 1
"""
    rows = await _SNOWFLAKE_CLIENT.execute(sql)
    result: dict[str, str | None] = {
        "nightly": None,
        "monthly": None,
        "weekly_snapshot": None,
        "on_demand": None,
    }
    for row in rows:
        worker_name = str(row["WORKER_NAME"]).strip()
        if worker_name in result:
            result[worker_name] = str(row["LAST_SUCCESS_TS"])
    return result


def _stringify_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str, sort_keys=True)


def _drain_buffer() -> list[dict[str, Any]]:
    rows = list(_BUFFER)
    _BUFFER.clear()
    return rows


async def _flush_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    if _SNOWFLAKE_CLIENT is None:
        return

    values_clause = ",\n".join(_render_values_tuple(row) for row in rows)
    sql = f"""
INSERT INTO CS_ANALYTICS.AC_PULSE_AUDIT_LOG (
    run_id,
    event_ts,
    account_id,
    field_name,
    old_value,
    new_value,
    status,
    error_message
)
SELECT
    column1 AS run_id,
    TO_TIMESTAMP_NTZ(column2) AS event_ts,
    column3::NUMBER(38,0) AS account_id,
    column4 AS field_name,
    column5 AS old_value,
    column6 AS new_value,
    column7 AS status,
    column8 AS error_message
FROM VALUES
{values_clause}
"""
    await _SNOWFLAKE_CLIENT.execute(sql)


def _render_values_tuple(row: dict[str, Any]) -> str:
    fields = [
        _escape_sql_string(row["run_id"]),
        _escape_sql_string(row["event_ts"]),
        str(int(row["account_id"])),
        _escape_sql_string(row["field_name"]),
        _escape_sql_string_or_null(row["old_value"]),
        _escape_sql_string_or_null(row["new_value"]),
        _escape_sql_string(row["status"]),
        _escape_sql_string_or_null(row["error_message"]),
    ]
    return "(" + ", ".join(fields) + ")"


def _escape_sql_string(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _escape_sql_string_or_null(value: str | None) -> str:
    if value is None:
        return "NULL"
    return _escape_sql_string(value)
