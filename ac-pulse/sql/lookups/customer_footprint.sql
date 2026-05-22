-- ============================================================
-- DOMAIN & EMAIL FOOTPRINT LOOKUP — customer dedupe service
-- ============================================================
-- The :EMAIL placeholder is substituted by app/lookup_service.py
-- at runtime AFTER the email has been format-validated. Don't
-- attempt SQL parameter binding here; this query is executed
-- through Zapier MCP's snowflake_execute_sql which takes a
-- single statement string.
--
-- Searches 6 sources for any trace of the email or its domain:
--   1. SUPPORT.EMAIL_TO_ACCOUNTID_BEST_MATCH (exact email → account)
--   2. CONFORMED_DIMENSIONS.ACCOUNT_EXTENSION admin email (exact)
--   3. CONFORMED_DIMENSIONS.ACCOUNT_EXTENSION domain match
--      (excluding test/sandbox/credit accounts)
--   4. CONFORMED_DIMENSIONS.DEALS_MAT subscriber email (domain)
--   5. EM_4303.EM_SUBSCRIBER (CRM contact email + domain)
--   6. EM_4303.EM_CUSTOMER_ACCOUNT (org URL contains domain)
-- ============================================================

WITH params AS (
    SELECT
        ':EMAIL'                                       AS input_email,
        LOWER(SPLIT_PART(':EMAIL', '@', 2))            AS input_domain
),
email_match AS (
    SELECT e.ACCOUNTID AS account_id, e.EMAIL AS matched_email,
           e.MATCH_TYPE, 'EMAIL_RESOLUTION' AS discovery_source
    FROM SUPPORT.EMAIL_TO_ACCOUNTID_BEST_MATCH e, params p
    WHERE LOWER(e.EMAIL) = LOWER(p.input_email)
),
admin_email_match AS (
    SELECT ae.ACCOUNT_ID, ae.PRIMARY_ADMIN_EMAIL AS matched_email,
           'ADMIN_EMAIL' AS match_type, 'ACCOUNT_EXTENSION' AS discovery_source
    FROM CONFORMED_DIMENSIONS.ACCOUNT_EXTENSION ae, params p
    WHERE LOWER(ae.PRIMARY_ADMIN_EMAIL) = LOWER(p.input_email)
),
domain_acct_match AS (
    SELECT ae.ACCOUNT_ID, ae.PRIMARY_ADMIN_EMAIL AS matched_email,
           'DOMAIN_MATCH' AS match_type, 'ACCOUNT_EXTENSION' AS discovery_source
    FROM CONFORMED_DIMENSIONS.ACCOUNT_EXTENSION ae, params p
    WHERE LOWER(ae.ACCOUNT_WEB_DOMAIN) = p.input_domain
      AND ae.TEST_ACCOUNT_FLAG = 0
      AND ae.CLIENT_SANDBOX_FLAG = 0
      AND ae.CREDIT_ACCOUNT_FLAG = 0
),
all_account_hits AS (
    SELECT account_id, matched_email, match_type, discovery_source FROM email_match
    UNION
    SELECT account_id, matched_email, match_type, discovery_source FROM admin_email_match
    UNION
    SELECT account_id, matched_email, match_type, discovery_source FROM domain_acct_match
),
enriched_accounts AS (
    SELECT 'ACCOUNT' AS record_type, h.account_id, NULL AS deal_id, NULL AS contact_id,
           h.matched_email, h.match_type, h.discovery_source,
           ae.ACCOUNT_NAME, ae.ACCOUNT_WEB_DOMAIN, ae.PLAN_TIER_NAME,
           ROUND(COALESCE(ae.MRR, 0) * 12, 2) AS arr,
           ae.PAID_ACCOUNT_FLAG, ae.LIVE_ACCOUNT_FLAG,
           ae.ACCOUNT_CONVERT_DATE, ae.EXPIRE_DATE, ae.CANCELLED_FLAG,
           ae.CANCEL_REASON_BUCKET, ae.REGION,
           CASE WHEN ae.PAID_ACCOUNT_FLAG = 1 AND ae.LIVE_ACCOUNT_FLAG = 1 THEN 'Active Paid'
                WHEN ae.CANCELLED_FLAG = 1 THEN 'Cancelled'
                WHEN ae.EXPIRE_DATE < CURRENT_DATE() THEN 'Expired'
                WHEN ae.ACCOUNT_CONVERT_DATE IS NULL THEN 'Trial / Never Converted'
                ELSE 'Other' END AS account_status,
           NULL AS pipeline, NULL AS deal_stage, NULL AS deal_status,
           NULL AS deal_owner, NULL AS record_created
    FROM all_account_hits h
    LEFT JOIN CONFORMED_DIMENSIONS.ACCOUNT_EXTENSION ae ON h.account_id = ae.ACCOUNT_ID
),
deal_hits AS (
    SELECT 'DEAL' AS record_type, d.ACCOUNT_ID, d.ID AS deal_id, NULL AS contact_id,
           d.SUBSCRIBER_EMAIL AS matched_email,
           'DOMAIN_MATCH' AS match_type, 'DEALS_MAT' AS discovery_source,
           d.TITLE AS account_name, NULL AS account_web_domain, NULL AS plan_tier_name,
           NULL AS arr, NULL AS paid_account_flag, NULL AS live_account_flag,
           NULL AS account_convert_date, NULL AS expire_date, NULL AS cancelled_flag,
           NULL AS cancel_reason_bucket, NULL AS region, NULL AS account_status,
           d.PIPELINE_TITLE AS pipeline, d.DEAL_STAGE_NAME AS deal_stage,
           CASE d.STATUS WHEN 0 THEN 'Open' WHEN 1 THEN 'Won' WHEN 2 THEN 'Lost' ELSE 'Unknown' END AS deal_status,
           d.DEAL_OWNER_NAME AS deal_owner, d.CDATE AS record_created
    FROM CONFORMED_DIMENSIONS.DEALS_MAT d, params p
    WHERE LOWER(SPLIT_PART(d.SUBSCRIBER_EMAIL, '@', 2)) = p.input_domain
),
contact_hits AS (
    SELECT 'CONTACT' AS record_type, NULL AS account_id, NULL AS deal_id, s.ID AS contact_id,
           s.EMAIL AS matched_email,
           CASE WHEN LOWER(s.EMAIL) = LOWER(p.input_email) THEN 'EXACT_EMAIL' ELSE 'DOMAIN_MATCH' END AS match_type,
           'EM_SUBSCRIBER' AS discovery_source,
           COALESCE(s.FIRST_NAME,'') || ' ' || COALESCE(s.LAST_NAME,'') AS account_name,
           NULL AS account_web_domain, NULL AS plan_tier_name, NULL AS arr,
           NULL AS paid_account_flag, NULL AS live_account_flag,
           NULL AS account_convert_date, NULL AS expire_date, NULL AS cancelled_flag,
           NULL AS cancel_reason_bucket, NULL AS region, NULL AS account_status,
           NULL AS pipeline, NULL AS deal_stage, NULL AS deal_status,
           NULL AS deal_owner, s.CDATE AS record_created
    FROM EM_4303.EM_SUBSCRIBER s, params p
    WHERE LOWER(SPLIT_PART(s.EMAIL, '@', 2)) = p.input_domain
),
org_hits AS (
    SELECT 'ORG' AS record_type, NULL AS account_id, NULL AS deal_id, ca.ID AS contact_id,
           NULL AS matched_email, 'URL_DOMAIN_MATCH' AS match_type,
           'EM_CUSTOMER_ACCOUNT' AS discovery_source,
           ca.NAME AS account_name, ca.ACCOUNT_URL AS account_web_domain,
           NULL AS plan_tier_name, NULL AS arr, NULL AS paid_account_flag,
           NULL AS live_account_flag, NULL AS account_convert_date, NULL AS expire_date,
           NULL AS cancelled_flag, NULL AS cancel_reason_bucket, NULL AS region,
           NULL AS account_status, NULL AS pipeline, NULL AS deal_stage,
           NULL AS deal_status, NULL AS deal_owner, ca.CREATED_TIMESTAMP AS record_created
    FROM EM_4303.EM_CUSTOMER_ACCOUNT ca, params p
    WHERE LOWER(ca.ACCOUNT_URL) LIKE '%' || p.input_domain || '%'
)
SELECT * FROM enriched_accounts
UNION ALL SELECT * FROM deal_hits
UNION ALL SELECT * FROM contact_hits
UNION ALL SELECT * FROM org_hits
ORDER BY CASE record_type
             WHEN 'ACCOUNT' THEN 1
             WHEN 'DEAL'    THEN 2
             WHEN 'CONTACT' THEN 3
             WHEN 'ORG'     THEN 4
         END,
         arr DESC NULLS LAST,
         record_created DESC NULLS LAST
LIMIT 50
