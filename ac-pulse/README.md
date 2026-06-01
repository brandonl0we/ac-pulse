# ac-pulse

ac-pulse syncs customer success signals from Snowflake into ActiveCampaign account
custom fields, with historical snapshots and audit logging in Snowflake.

## Local development

```bash
uv sync --dev
cp .env.example .env
uv run pytest
uv run ruff check .
uv run mypy app
uv run uvicorn app.main:app --reload
```

Run these commands from the `ac-pulse/` implementation directory. The repository
root keeps separate Spark deployment shims so the platform can detect and run the
app.

## API endpoints

Public app and health endpoints:

- `GET /` and `GET /app` (portfolio command center UI)
- `GET /healthz` (liveness only; no external dependency calls)
- `GET /readyz` (dependency readiness diagnostics)
- `GET /portfolio?rep_name=...`
- `GET /portfolio/{rep_name}`
- `GET /pulse/{account_id}` (read-only account health narrative)
- `GET /audit/recent`
- `POST /resync/{account_id}`
- `POST /actions/plan` (dry-run task and note planning)
- `POST /actions/commit` (writes reviewed ActiveCampaign account notes)

Protected service endpoints require `X-Service-Key` and `SERVICE_API_KEY`:

- `GET /admin/smoke-snowflake`
- `GET /admin/account-map/preview`
- `GET /admin/account-materialization/plan`
- `POST /admin/account-materialization/plan`
- `POST /lookup/customer-by-email`

ActiveCampaign field bootstrap endpoint:

- `POST /admin/bootstrap-account-fields`

## API key and environment setup

- Local development: put your key in `.env` as `AC_API_KEY=<your_key>`
- Fly.io: set secrets with `fly secrets set AC_API_KEY=... AC_API_URL=...`
- Spark: set secrets through app settings; see the root `README.md`
- Never commit API keys to git. `.env` is ignored by `.gitignore`.

## Snowflake backend

- Production path: `SNOWFLAKE_BACKEND=direct` with `SNOWFLAKE_API_KEY`.
- POC path: `SNOWFLAKE_BACKEND=zapier_mcp` with `ZAPIER_MCP_URL` and
  `ZAPIER_MCP_TOKEN`.
- Zapier MCP is intended for read-only pulse/lookup flows. Batch writes and
  audit inserts still require the direct Snowflake backend.

## Account ID mapping

`ACCOUNT_ID_MAP_JSON` takes precedence over `ACCOUNT_ID_MAP_PATH`. It may be a
simple object mapping Snowflake account IDs to ActiveCampaign account IDs:

```json
{"1043604": 9001}
```

It may also use nested values or reviewed mapping rows copied from the account
mapping workflow:

```json
{"1043604": {"ac_account_id": 9001}}
```

```json
[{"snowflake_account_id": 1043604, "ac_account_id": 9001}]
```

When `ACCOUNT_ID_MAP_JSON` is empty, the resolver reads `ACCOUNT_ID_MAP_PATH` as
a CSV with `snowflake_account_id,ac_account_id` columns.

## Required ActiveCampaign custom fields

This service writes the following account custom fields (created automatically by
`POST /admin/bootstrap-account-fields`):

- `churn_decile_band`
- `churn_score`
- `acai_score`
- `nbn_score`
- `utilization_percent`
- `days_since_touchpoint`
- `touchpoint_count_30d`
- `days_to_renewal`
- `renewal_date`
- `cs_priority_tier`
- `cs_intervention_due`
- `cs_health_status`
- `cs_next_best_action`
- `cs_priority_reason`
- `cs_renewal_motion`
- `cs_owner_attention`
- `cs_snowflake_account_id`
