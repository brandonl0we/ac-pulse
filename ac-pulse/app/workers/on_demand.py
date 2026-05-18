from collections.abc import Mapping
from typing import Any

from app.alerts import send_alert
from app.audit import get_audit_rows_for_run
from app.config import get_settings
from app.extractors.acai import ACAIExtractor
from app.extractors.churn import ChurnExtractor
from app.extractors.nbn import NBNExtractor
from app.extractors.renewal import RenewalExtractor
from app.extractors.touchpoints import TouchpointsExtractor
from app.extractors.utilization import UtilizationExtractor
from app.snowflake_client import SnowflakeClient
from app.workers.pipeline import run_signal_sync


async def run_on_demand(ctx: Mapping[str, Any], account_id: int) -> dict[str, Any]:
    del ctx
    settings = get_settings()
    snowflake_client = SnowflakeClient(settings)
    extractors = [
        ChurnExtractor(snowflake_client),
        ACAIExtractor(snowflake_client),
        NBNExtractor(snowflake_client),
        UtilizationExtractor(snowflake_client),
        TouchpointsExtractor(snowflake_client),
        RenewalExtractor(snowflake_client),
    ]
    try:
        summary = await run_signal_sync(
            worker_name="on_demand",
            extractor_instances=extractors,
            account_filter=account_id,
        )
    except Exception as exc:
        await send_alert(f"ac-pulse on_demand worker failed for account {account_id}: {exc}")
        raise

    run_id = str(summary["run_id"])
    audit_rows = await get_audit_rows_for_run(run_id)
    return {
        "account_id": account_id,
        "summary": summary,
        "audit_rows": audit_rows,
    }
