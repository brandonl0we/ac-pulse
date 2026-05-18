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
- `REDIS_URL`
- `CRON_SECRET`

## API endpoints

- `GET /healthz`
- `POST /resync/{account_id}`
- `GET /audit/recent`
- `POST /admin/bootstrap-account-fields`
