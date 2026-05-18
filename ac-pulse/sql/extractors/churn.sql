-- Assumption: spec SQL section is not present in this repo; this query mirrors the
-- intended source table referenced in the build prompt and can be replaced verbatim
-- once the canonical SQL block is added to BUILD_PROMPT.md.
SELECT
    account_id,
    churn_decile_band,
    churn_score
FROM VELOCITY_CHURN_MODEL.ACCOUNT_FEATURE_CHURN_PREDICTION_DRIVERS_BY_MONTH
QUALIFY ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY score_month DESC) = 1
;
