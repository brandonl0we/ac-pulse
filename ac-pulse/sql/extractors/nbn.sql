SELECT
    account_id,
    nbn_score
FROM CS_ANALYTICS.NBN_SIGNALS
QUALIFY ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY snapshot_month DESC) = 1
;
