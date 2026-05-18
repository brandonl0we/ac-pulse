SELECT
    account_id,
    utilization_percent
FROM CS_ANALYTICS.ACCOUNT_UTILIZATION_DAILY
QUALIFY ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY snapshot_date DESC) = 1
;
