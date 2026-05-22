"""Heartbeat cron — hourly self-test of the /lookup path.

Calls lookup_customer_by_email directly (bypassing HTTP/auth overhead)
against HEARTBEAT_TEST_EMAIL with force_refresh=True so each run
exercises the full wire (MCP → Snowflake → response shaping). Logs the
outcome with structured fields so dashboards can graph latency +
success rate over time. Sends a Slack alert when:
  - reason=lookup_unavailable (Zapier MCP down, auth expired, etc.)
  - reason=invalid_email (HEARTBEAT_TEST_EMAIL is malformed)
  - is_known=False on an email we expect to be in the warehouse —
    means SQL drift or warehouse schema changes

Skipped entirely when HEARTBEAT_TEST_EMAIL isn't configured, so deploys
without it set don't spam alerts.
"""

from collections.abc import Mapping
from typing import Any

import structlog
from redis.asyncio import Redis

from app.alerts import send_alert
from app.config import get_settings
from app.lookup_service import lookup_customer_by_email

logger = structlog.get_logger(__name__)


async def run_heartbeat(ctx: Mapping[str, Any]) -> dict[str, Any]:
    del ctx
    settings = get_settings()
    test_email = settings.heartbeat_test_email
    if not test_email:
        logger.info("heartbeat_skipped", reason="HEARTBEAT_TEST_EMAIL not set")
        return {"skipped": True}

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        result = await lookup_customer_by_email(
            settings, redis, test_email, force_refresh=True
        )
    finally:
        await redis.aclose()

    elapsed_ms = result.get("elapsed_ms", 0)
    reason = result.get("reason")
    is_known = result.get("is_known")
    is_customer = result.get("is_customer")

    log_fields: dict[str, Any] = {
        "test_email": test_email,
        "elapsed_ms": elapsed_ms,
        "reason": reason,
        "is_known": is_known,
        "is_customer": is_customer,
        "total_rows": result.get("total_rows"),
    }

    if reason == "lookup_unavailable":
        logger.error("heartbeat_lookup_unavailable", **log_fields, error=result.get("error"))
        await send_alert(
            f"ac-pulse heartbeat: /lookup is unavailable. "
            f"Error: {result.get('error', 'unknown')}"
        )
        return {"ok": False, **log_fields}

    if reason == "invalid_email":
        logger.error("heartbeat_invalid_email", **log_fields)
        await send_alert(
            f"ac-pulse heartbeat: HEARTBEAT_TEST_EMAIL is malformed: {test_email}"
        )
        return {"ok": False, **log_fields}

    if is_known is False:
        logger.warning("heartbeat_unexpected_unknown", **log_fields)
        await send_alert(
            f"ac-pulse heartbeat: lookup returned is_known=False for "
            f"{test_email} — SQL or warehouse drift?"
        )
        return {"ok": False, **log_fields}

    logger.info("heartbeat_ok", **log_fields)
    return {"ok": True, **log_fields}
