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
- `REDIS_URL`
- `ACCOUNT_ID_MAP_PATH` (example: `./ac-pulse/data/account_id_map.csv`)
- `SERVICE_API_KEY` (required for protected `/admin/*` and `/lookup/*` endpoints)

For the production Snowflake backend, also set:

- `SNOWFLAKE_BACKEND=direct`
- `SNOWFLAKE_ACCOUNT`
- `SNOWFLAKE_USER`
- `SNOWFLAKE_API_KEY` (PEM private key for Snowflake JWT auth)
- `SNOWFLAKE_WAREHOUSE`
- `SNOWFLAKE_DATABASE`
- `SNOWFLAKE_ROLE` (optional when the Snowflake user has a default role)

For the Zapier MCP proof-of-concept backend, set `SNOWFLAKE_BACKEND=zapier_mcp` plus:

- `ZAPIER_MCP_URL`
- `ZAPIER_MCP_TOKEN`

## API endpoints

- `GET /healthz`
- `GET /readyz`
- `POST /resync/{account_id}`
- `GET /pulse/{account_id}`
- `GET /audit/recent`
- `GET /portfolio`
- `POST /actions/plan`
- `POST /actions/commit`
- `GET /admin/account-map/preview`
- `GET /admin/account-materialization/plan`
- `POST /admin/account-materialization/plan`
- `POST /admin/bootstrap-account-fields`
- `POST /lookup/customer-by-email`
