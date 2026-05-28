WITH params AS (
    SELECT
        %(rep_name)s AS rep_name,
        CURRENT_DATE() AS today,
        DATEADD('day', -30, CURRENT_DATE()) AS window_30d,
        DATEADD('day', -90, CURRENT_DATE()) AS window_90d
),

-- 1. Account spine: paid/live accounts assigned to this rep.
acct AS (
    SELECT
        ae.ACCOUNT_ID,
        ae.ACCOUNT_NAME,
        ae.SUCCESS_REP_NAME,
        ae.SUCCESS_OWNERSHIP_BUCKET,
        ae.PLAN_TIER_NAME,
        ae.PRODUCT_LINE_ACTUAL,
        ae.ACCOUNT_WEB_DOMAIN,
        ae.MRR,
        ROUND(ae.MRR * 12, 2) AS arr,
        ae.ACCOUNT_CONVERT_DATE,
        ae.CONTRACT_START_DATE,
        ae.CONTRACT_END_DATE,
        ae.CONTRACT_LENGTH_CURRENT,
        ae.REGION,
        ae.CURRENT_CHURN_RISK_3MO,
        ae.CURRENT_CONTRACTION_RISK_3MO,
        ae.CURRENT_OVERALL_PREDICTION_TYPE_RISK,
        ae.CANCELLED_FLAG,
        ae.CANCEL_REASON,
        ae.FUTURE_CANCEL_CHURN_DATE,
        ae.PRODUCT_SCORE,
        ae.MAX_PRODUCT_SCORE,
        ae.ACTIVE_AUTOMATIONS_PRODUCT_SCORE,
        ae.BATCH_CAMPAIGNS_PRODUCT_SCORE,
        ae.ACTIVE_INTEGRATIONS_PRODUCT_SCORE,
        ae.UNIQUE_NON_AC_USER_LOGINS_PRODUCT_SCORE,
        ae.GENERATIVE_AI_PRODUCT_SCORE,
        ae.CRM_DEALS_PRODUCT_SCORE,
        ae.SMS_ADD_ON_PRODUCT_SCORE,
        ae.LATEST_NPS_SCORE,
        ae.LATEST_NPS_SUBMISSION_DATE,
        ae.LAST_SUCCESS_INTERACTION_DATE,
        ae.LAST_SUCCESS_INTERACTION_CONTENT
    FROM CONFORMED_DIMENSIONS.ACCOUNT_EXTENSION ae
    CROSS JOIN params p
    WHERE UPPER(TRIM(ae.SUCCESS_REP_NAME)) = UPPER(TRIM(p.rep_name))
      AND ae.PAID_ACCOUNT_FLAG = 1
      AND ae.LIVE_ACCOUNT_FLAG = 1
      AND ae.TEST_ACCOUNT_FLAG = 0
      AND ae.CLIENT_SANDBOX_FLAG = 0
      AND ae.CREDIT_ACCOUNT_FLAG = 0
),

-- 2. Totango touchpoints: 90-day summary per account.
tp_summary AS (
    SELECT
        st.ACCOUNT_ID,
        COUNT(*) AS total_touchpoints_90d,
        COUNT(CASE WHEN st.EVENT_TYPE = 'Email Engagement' THEN 1 END) AS email_tp_90d,
        COUNT(CASE WHEN st.EVENT_TYPE = 'Web meeting' THEN 1 END) AS web_mtg_90d,
        COUNT(CASE WHEN st.EVENT_TYPE = 'Internal Note' THEN 1 END) AS internal_notes_90d,
        COUNT(CASE WHEN st.EVENT_TYPE = 'Telephone call' THEN 1 END) AS phone_90d,
        COUNT(CASE WHEN st.EVENT_TYPE = 'LinkedIn' THEN 1 END) AS linkedin_90d,
        COUNT(CASE WHEN st.EVENT_TYPE = 'SMS' THEN 1 END) AS sms_90d,
        MAX(st.EVENT_START_DATE) AS last_tp_date,
        DATEDIFF('day', MAX(st.EVENT_START_DATE), CURRENT_DATE()) AS days_since_last_tp
    FROM CUSTOMER_SUCCESS.SUCCESS_TOUCHPOINTS st
    CROSS JOIN params p
    WHERE st.EVENT_SOURCE = 'Totango'
      AND st.EVENT_START_DATE >= p.window_90d
      AND st.ACCOUNT_ID IN (SELECT ACCOUNT_ID FROM acct)
    GROUP BY st.ACCOUNT_ID
),

-- 3. Totango touchpoints: 30-day summary per account.
tp_30d AS (
    SELECT
        st.ACCOUNT_ID,
        COUNT(*) AS total_tp_30d,
        COUNT(CASE WHEN st.EVENT_TYPE = 'Email Engagement' THEN 1 END) AS email_tp_30d,
        COUNT(CASE WHEN st.EVENT_TYPE = 'Web meeting' THEN 1 END) AS web_mtg_30d
    FROM CUSTOMER_SUCCESS.SUCCESS_TOUCHPOINTS st
    CROSS JOIN params p
    WHERE st.EVENT_SOURCE = 'Totango'
      AND st.EVENT_START_DATE >= p.window_30d
      AND st.ACCOUNT_ID IN (SELECT ACCOUNT_ID FROM acct)
    GROUP BY st.ACCOUNT_ID
)

SELECT
    a.ACCOUNT_ID,
    a.ACCOUNT_NAME,
    a.SUCCESS_REP_NAME,
    a.SUCCESS_OWNERSHIP_BUCKET,
    a.PLAN_TIER_NAME,
    a.PRODUCT_LINE_ACTUAL,
    a.ACCOUNT_WEB_DOMAIN,
    a.MRR,
    a.ARR,
    a.REGION,
    a.ACCOUNT_CONVERT_DATE,
    a.CONTRACT_END_DATE,
    a.CONTRACT_LENGTH_CURRENT,
    a.CURRENT_CHURN_RISK_3MO,
    a.CURRENT_CONTRACTION_RISK_3MO,
    a.CURRENT_OVERALL_PREDICTION_TYPE_RISK,
    a.CANCELLED_FLAG,
    a.CANCEL_REASON,
    a.FUTURE_CANCEL_CHURN_DATE,
    a.PRODUCT_SCORE,
    a.MAX_PRODUCT_SCORE,
    a.ACTIVE_AUTOMATIONS_PRODUCT_SCORE,
    a.BATCH_CAMPAIGNS_PRODUCT_SCORE,
    a.ACTIVE_INTEGRATIONS_PRODUCT_SCORE,
    a.UNIQUE_NON_AC_USER_LOGINS_PRODUCT_SCORE,
    a.GENERATIVE_AI_PRODUCT_SCORE,
    a.CRM_DEALS_PRODUCT_SCORE,
    a.SMS_ADD_ON_PRODUCT_SCORE,
    a.LATEST_NPS_SCORE,
    a.LATEST_NPS_SUBMISSION_DATE,
    a.LAST_SUCCESS_INTERACTION_DATE,
    a.LAST_SUCCESS_INTERACTION_CONTENT,
    COALESCE(tp.total_touchpoints_90d, 0) AS total_touchpoints_90d,
    COALESCE(tp.email_tp_90d, 0) AS email_touchpoints_90d,
    COALESCE(tp.web_mtg_90d, 0) AS web_meetings_90d,
    COALESCE(tp.internal_notes_90d, 0) AS internal_notes_90d,
    COALESCE(tp.phone_90d, 0) AS phone_calls_90d,
    COALESCE(tp.linkedin_90d, 0) AS linkedin_90d,
    COALESCE(tp.sms_90d, 0) AS sms_touchpoints_90d,
    tp.last_tp_date,
    tp.days_since_last_tp,
    COALESCE(tp30.total_tp_30d, 0) AS total_touchpoints_30d,
    COALESCE(tp30.email_tp_30d, 0) AS email_touchpoints_30d,
    COALESCE(tp30.web_mtg_30d, 0) AS web_meetings_30d
FROM acct a
LEFT JOIN tp_summary tp ON a.ACCOUNT_ID = tp.ACCOUNT_ID
LEFT JOIN tp_30d tp30 ON a.ACCOUNT_ID = tp30.ACCOUNT_ID
ORDER BY a.ARR DESC
LIMIT 500
;
