from typing import Any

import httpx
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)


async def send_alert(message: str) -> None:
    settings = get_settings()
    webhook_url = settings.slack_webhook_url.strip()
    if not webhook_url:
        logger.warning("slack_alert_skipped_missing_webhook", message=message)
        return

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(webhook_url, json={"text": message})
        response.raise_for_status()


async def maybe_alert_on_summary(summary: dict[str, Any]) -> None:
    total_accounts = int(summary.get("processed", 0))
    failed_accounts = int(summary.get("failed", 0))
    dead_letter_depth = int(summary.get("dead_letter_depth", 0))
    if total_accounts > 0 and (failed_accounts / total_accounts) > 0.05:
        await send_alert(
            f"ac-pulse worker `{summary.get('worker')}` exceeded 5% error rate "
            f"({failed_accounts}/{total_accounts})."
        )
    if dead_letter_depth > 100:
        await send_alert(
            f"ac-pulse dead-letter queue depth is {dead_letter_depth}, above threshold 100."
        )
