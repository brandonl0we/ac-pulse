# ac-pulse

This repository hosts the `ac-pulse` Customer Success signal sync service for ActiveCampaign.

## Current repository layout

The full implementation is currently in the `ac-pulse/` subdirectory. Root-level files are provided so Spark can detect and run the app.

- Root `main.py` adds `ac-pulse/` to `PYTHONPATH` and exposes `app`.
- Root `requirements.txt` supports Spark Python build auto-detection.
- Root `spark.json` configures health checks and the background arq worker.

## Spark deployment configuration

- Runtime: Python 3.12 (`runtime.txt`)
- Health check: `GET /healthz`
- Worker command: `PYTHONPATH=/app/ac-pulse arq app.workers.settings.WorkerSettings`

## Required environment variables

Set these in Spark app settings/secrets:

- `AC_API_URL` (sandbox: `https://brandontest.api-us1.com/api/3`)
- `AC_API_KEY`
- `SNOWFLAKE_ACCOUNT`
- `SNOWFLAKE_USER`
- `SNOWFLAKE_PASSWORD`
- `SNOWFLAKE_WAREHOUSE`
- `SNOWFLAKE_DATABASE`
- `SNOWFLAKE_ROLE`
- `ACCOUNT_ID_MAP_PATH` (example: `./data/account_id_map.csv`)
- `ACCOUNT_ID_MAP_JSON` (optional Spark-friendly override, example: `{"101":9001}`)
- `REDIS_URL`
- `CRON_SECRET`

## First live Spark test

Use a single sandbox account until the Snowflake-to-ActiveCampaign mapping source
is confirmed.

1. Set `LIMIT_ACCOUNTS=1`.
2. Set either `ACCOUNT_ID_MAP_JSON='{"<snowflake_account_id>":<ac_account_id>}'`
   or provide a CSV at `ACCOUNT_ID_MAP_PATH` with `snowflake_account_id` and
   `ac_account_id` columns.
3. Trigger `POST /resync/{snowflake_account_id}`.
4. Check `/audit/recent` and the target AC account fields before widening scope.

`ACCOUNT_ID_MAP_JSON` takes precedence over the CSV path. If a resync has no
matching mapping, the endpoint returns a failure instead of silently succeeding.

## API endpoints

- `GET /healthz`
- `POST /resync/{account_id}`
- `GET /audit/recent`
- `POST /admin/bootstrap-account-fields`
