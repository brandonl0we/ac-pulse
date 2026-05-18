from collections.abc import Mapping
from typing import Any

from app.alerts import send_alert
from app.config import get_settings
from app.snapshot import write_weekly_snapshot
from app.snowflake_client import SnowflakeClient


async def run_weekly_snapshot(ctx: Mapping[str, Any]) -> dict[str, str]:
    del ctx
    settings = get_settings()
    snowflake_client = SnowflakeClient(settings)
    try:
        return await write_weekly_snapshot(snowflake_client)
    except Exception as exc:
        await send_alert(f"ac-pulse weekly snapshot worker failed: {exc}")
        raise
