CREATE TABLE IF NOT EXISTS CS_ANALYTICS.ACCOUNT_STATE_WEEKLY (
    account_id NUMBER(38,0) NOT NULL,
    snapshot_date DATE NOT NULL,
    churn_decile_band STRING,
    churn_score FLOAT,
    acai_score FLOAT,
    nbn_score FLOAT,
    utilization_percent FLOAT,
    days_since_touchpoint NUMBER(10,0),
    touchpoint_count_30d NUMBER(10,0),
    days_to_renewal NUMBER(10,0),
    renewal_date DATE,
    churned_in_next_30d BOOLEAN DEFAULT FALSE,
    churned_in_next_60d BOOLEAN DEFAULT FALSE,
    churned_in_next_90d BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    updated_at TIMESTAMP_NTZ,
    CONSTRAINT pk_account_state_weekly PRIMARY KEY (account_id, snapshot_date)
);
