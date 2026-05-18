SELECT
    account_id,
    acai_score
FROM CS_ANALYTICS.ACAI_SIGNALS
QUALIFY ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY snapshot_month DESC) = 1
;
