import json
import re
import time
from pathlib import Path
from typing import Any

import structlog
from redis.asyncio import Redis

from app.config import Settings
from app.zapier_client import ZapierMCPError, execute_snowflake_sql

logger = structlog.get_logger(__name__)

# Strict email format check before substitution into raw SQL. We don't
# parameter-bind through Zapier MCP (the tool accepts a single SQL
# statement string), so we have to validate the input ourselves.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

_SQL_PATH = Path(__file__).resolve().parent.parent / "sql" / "lookups" / "customer_footprint.sql"
_SQL_TEMPLATE: str | None = None

# Explicit column list for output_hint — without this Zapier's LLM-driven
# filter drops columns we don't name. Keep in sync with the SELECT list
# in customer_footprint.sql.
_OUTPUT_COLUMNS = [
    "record_type", "account_id", "deal_id", "contact_id",
    "matched_email", "match_type", "discovery_source",
    "account_name", "account_web_domain", "plan_tier_name", "arr",
    "paid_account_flag", "live_account_flag",
    "account_convert_date", "expire_date", "cancelled_flag",
    "cancel_reason_bucket", "region", "account_status",
    "pipeline", "deal_stage", "deal_status", "deal_owner",
    "record_created",
]
_OUTPUT_HINT = (
    "Return all rows with these columns and do not filter: "
    + ", ".join(_OUTPUT_COLUMNS)
)


def _load_sql_template() -> str:
    global _SQL_TEMPLATE
    if _SQL_TEMPLATE is None:
        _SQL_TEMPLATE = _SQL_PATH.read_text(encoding="utf-8")
    return _SQL_TEMPLATE


def _build_sql(email: str) -> str:
    """Substitute :EMAIL into the template after format validation."""
    if not _EMAIL_RE.match(email):
        raise ValueError(f"invalid email format: {email!r}")
    # Email has already passed regex; safe to inject as a literal.
    return _load_sql_template().replace(":EMAIL", email)


def _cache_key(email: str) -> str:
    return f"acpulse:lookup:email:{email.lower()}"


async def _get_cached(redis: Redis, email: str) -> dict[str, Any] | None:
    try:
        raw = await redis.get(_cache_key(email))
    except Exception:
        logger.exception("lookup_cache_get_failed")
        return None
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


async def _set_cached(redis: Redis, email: str, payload: dict[str, Any], ttl: int) -> None:
    try:
        await redis.setex(_cache_key(email), ttl, json.dumps(payload))
    except Exception:
        logger.exception("lookup_cache_set_failed")


def shape_response(email: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Group raw SQL rows into the grouped/labeled response agents consume.

    The shape answers the most-common questions an outbound agent asks
    in one round trip:
      - is_customer    → any active paid account match?
      - is_known       → any hit at all?
      - exact_email    → row(s) where match_type indicates exact email
      - by record_type → all hits grouped by ACCOUNT / DEAL / CONTACT / ORG
      - highest_value  → the account with the highest ARR (if any)
    """
    domain = email.split("@", 1)[1].lower() if "@" in email else ""

    by_type: dict[str, list[dict[str, Any]]] = {
        "ACCOUNT": [],
        "DEAL": [],
        "CONTACT": [],
        "ORG": [],
    }
    exact_email_matches: list[dict[str, Any]] = []
    is_customer = False
    highest_value: dict[str, Any] | None = None

    for row in rows:
        record_type = row.get("record_type")
        if record_type in by_type:
            by_type[record_type].append(row)
        match_type = row.get("match_type") or ""
        # Anything keyed on the exact email (not just domain) qualifies
        # as a direct hit — EXACT_EMAIL from contact_hits, ADMIN_EMAIL
        # from admin_email_match, and EMAIL_RESOLUTION discovery_source
        # from the support email resolution table.
        if match_type in {"EXACT_EMAIL", "ADMIN_EMAIL"} or (
            row.get("discovery_source") == "EMAIL_RESOLUTION"
        ):
            exact_email_matches.append(row)
        if record_type == "ACCOUNT" and row.get("account_status") == "Active Paid":
            is_customer = True
        # Track the highest-ARR account match.
        if record_type == "ACCOUNT":
            arr = row.get("arr") or 0
            current_arr = (highest_value or {}).get("arr") or 0
            if highest_value is None or arr > current_arr:
                highest_value = row

    return {
        "input_email": email,
        "input_domain": domain,
        "is_customer": is_customer,
        "is_known": bool(rows),
        "highest_value_match": highest_value,
        "exact_email_matches": exact_email_matches,
        "by_record_type": by_type,
        "summary": {
            "accounts": len(by_type["ACCOUNT"]),
            "deals": len(by_type["DEAL"]),
            "contacts": len(by_type["CONTACT"]),
            "orgs": len(by_type["ORG"]),
            "active_paid_accounts": sum(
                1 for r in by_type["ACCOUNT"] if r.get("account_status") == "Active Paid"
            ),
        },
        "total_rows": len(rows),
    }


async def lookup_customer_by_email(
    settings: Settings,
    redis: Redis,
    email: str,
    *,
    force_refresh: bool = False,
    debug: bool = False,
) -> dict[str, Any]:
    """End-to-end dedupe lookup. Cache → MCP → shape → cache → return.

    Set force_refresh=True to skip the cache read but still update it
    after the MCP call returns. Used by the heartbeat cron so each run
    actually exercises the wire instead of replaying cached results.

    Set debug=True to include `_debug` info in the response: the SQL
    sent to Zapier (first 500 chars), a preview of the raw response,
    and content-block metadata. Use when results are unexpectedly
    empty so we can see what Zapier actually sent back.
    """
    started = time.monotonic()
    normalized = email.strip().lower()

    if not force_refresh:
        cached = await _get_cached(redis, normalized)
        if cached is not None:
            cached["cached"] = True
            cached["elapsed_ms"] = int((time.monotonic() - started) * 1000)
            return cached

    if not settings.zapier_mcp_url or not settings.zapier_mcp_token:
        return {
            "input_email": normalized,
            "is_customer": None,
            "is_known": None,
            "reason": "lookup_unavailable",
            "error": "ZAPIER_MCP_URL or ZAPIER_MCP_TOKEN not configured",
            "cached": False,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }

    try:
        sql = _build_sql(normalized)
    except ValueError as exc:
        return {
            "input_email": normalized,
            "is_customer": None,
            "is_known": None,
            "reason": "invalid_email",
            "error": str(exc),
            "cached": False,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }

    try:
        rows, mcp_debug = await execute_snowflake_sql(
            server_url=settings.zapier_mcp_url,
            token=settings.zapier_mcp_token,
            statement=sql,
            output_hint=_OUTPUT_HINT,
            instructions=(
                "Dedupe lookup for the customer footprint of a single email "
                "address. Read-only. Always returns every column listed in "
                "output_hint without filtering."
            ),
        )
    except ZapierMCPError as exc:
        return {
            "input_email": normalized,
            "is_customer": None,
            "is_known": None,
            "reason": "lookup_unavailable",
            "error": str(exc)[:300],
            "cached": False,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }

    payload = shape_response(normalized, rows)
    payload["cached"] = False
    payload["source"] = "zapier_mcp"
    payload["elapsed_ms"] = int((time.monotonic() - started) * 1000)

    if debug:
        payload["_debug"] = {
            "sql_length": len(sql),
            "sql_preview": sql[:500],
            "output_hint": _OUTPUT_HINT,
            **mcp_debug,
        }

    await _set_cached(redis, normalized, payload, settings.lookup_cache_ttl_seconds)
    return payload
