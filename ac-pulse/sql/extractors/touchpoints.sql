SELECT
    account_id,
    DATEDIFF(day, MAX(touchpoint_at), CURRENT_DATE()) AS days_since_touchpoint,
    COUNT_IF(touchpoint_at >= DATEADD(day, -30, CURRENT_DATE())) AS touchpoint_count_30d
FROM CS_ANALYTICS.CSM_TOUCHPOINTS
WHERE event_source = 'Totango'
GROUP BY account_id
;
