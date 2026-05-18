from datetime import UTC, datetime

from app.snowflake_client import SnowflakeClient

WEEKLY_SNAPSHOT_SQL = """
MERGE INTO CS_ANALYTICS.ACCOUNT_STATE_WEEKLY AS target
USING (
    SELECT
        account_id,
        CURRENT_DATE() AS snapshot_date,
        churn_decile_band,
        churn_score,
        acai_score,
        nbn_score,
        utilization_percent,
        days_since_touchpoint,
        touchpoint_count_30d,
        days_to_renewal,
        renewal_date
    FROM CS_ANALYTICS.ACCOUNT_CURRENT_STATE_V
) AS source
ON target.account_id = source.account_id
AND target.snapshot_date = source.snapshot_date
WHEN NOT MATCHED THEN INSERT (
    account_id,
    snapshot_date,
    churn_decile_band,
    churn_score,
    acai_score,
    nbn_score,
    utilization_percent,
    days_since_touchpoint,
    touchpoint_count_30d,
    days_to_renewal,
    renewal_date,
    created_at
) VALUES (
    source.account_id,
    source.snapshot_date,
    source.churn_decile_band,
    source.churn_score,
    source.acai_score,
    source.nbn_score,
    source.utilization_percent,
    source.days_since_touchpoint,
    source.touchpoint_count_30d,
    source.days_to_renewal,
    source.renewal_date,
    CURRENT_TIMESTAMP()
)
"""

BACKFILL_CHURN_FLAGS_SQL = """
UPDATE CS_ANALYTICS.ACCOUNT_STATE_WEEKLY AS weekly
SET
    churned_in_next_30d = CASE
        WHEN churn_event.event_date <= DATEADD(day, 30, weekly.snapshot_date) THEN TRUE
        ELSE FALSE
    END,
    churned_in_next_60d = CASE
        WHEN churn_event.event_date <= DATEADD(day, 60, weekly.snapshot_date) THEN TRUE
        ELSE FALSE
    END,
    churned_in_next_90d = CASE
        WHEN churn_event.event_date <= DATEADD(day, 90, weekly.snapshot_date) THEN TRUE
        ELSE FALSE
    END,
    updated_at = CURRENT_TIMESTAMP()
FROM CS_ANALYTICS.ACCOUNT_CHURN_EVENTS churn_event
WHERE churn_event.account_id = weekly.account_id
    AND weekly.snapshot_date >= DATEADD(day, -120, CURRENT_DATE())
"""


async def write_weekly_snapshot(sf: SnowflakeClient) -> dict[str, str]:
    await sf.execute(WEEKLY_SNAPSHOT_SQL)
    await sf.execute(BACKFILL_CHURN_FLAGS_SQL)
    return {"status": "ok", "executed_at": datetime.now(UTC).isoformat()}
