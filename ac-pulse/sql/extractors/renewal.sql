SELECT
    account_id,
    renewal_date,
    DATEDIFF(day, CURRENT_DATE(), renewal_date) AS days_to_renewal
FROM CS_ANALYTICS.ACCOUNT_RENEWALS
QUALIFY ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY renewal_date ASC) = 1
;
