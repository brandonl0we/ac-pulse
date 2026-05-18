CREATE TABLE IF NOT EXISTS CS_ANALYTICS.AC_PULSE_AUDIT_LOG (
    run_id STRING NOT NULL,
    event_ts TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    account_id NUMBER(38,0) NOT NULL,
    field_name STRING NOT NULL,
    old_value STRING,
    new_value STRING,
    status STRING NOT NULL,
    error_message STRING
);
