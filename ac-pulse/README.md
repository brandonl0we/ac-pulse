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

## API endpoints

- `GET /healthz`
- `POST /resync/{account_id}`
- `GET /pulse/{account_id}` (read-only account health narrative)
- `GET /audit/recent`
- `POST /admin/bootstrap-account-fields` (create required AC account custom fields)

## API key and environment setup

- Local development: put your key in `.env` as `AC_API_KEY=<your_key>`
- Fly.io: set secrets with `fly secrets set AC_API_KEY=... AC_API_URL=...`
- Never commit API keys to git. `.env` is ignored by `.gitignore`.

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
