from collections.abc import Mapping
from typing import Any

from app.alerts import maybe_alert_on_summary, send_alert
from app.config import get_settings
from app.extractors.acai import ACAIExtractor
from app.extractors.churn import ChurnExtractor
from app.extractors.nbn import NBNExtractor
from app.snowflake_client import SnowflakeClient
from app.workers.pipeline import run_signal_sync


async def run_monthly(ctx: Mapping[str, Any]) -> dict[str, str]:
    del ctx
    settings = get_settings()
    snowflake_client = SnowflakeClient(settings)
    extractors = [
        ChurnExtractor(snowflake_client),
        ACAIExtractor(snowflake_client),
        NBNExtractor(snowflake_client),
    ]
    try:
        summary = await run_signal_sync(worker_name="monthly", extractor_instances=extractors)
    except Exception as exc:
        await send_alert(f"ac-pulse monthly worker failed: {exc}")
        raise
    await maybe_alert_on_summary(summary)
    return {key: str(value) for key, value in summary.items()}
