# CLAUDE

ac-pulse is a production Python service for moving customer success signals from
Snowflake into ActiveCampaign account custom fields. Keep the architecture aligned
with the validated stack in `BUILD_PROMPT.md`: FastAPI, arq, Redis, Snowflake,
httpx, pydantic v2, structlog, pytest, ruff, and strict mypy.

## Current State

- The GitHub repo root wraps this service in the `ac-pulse/` subdirectory.
- Python is pinned with `.python-version` to 3.12 for `uv`.
- `uv run pytest`, `uv run ruff check .`, and `uv run mypy app` pass.
- `/healthz` has been smoke-tested with dummy environment values.

## Spark Deployment Notes

- The GitHub repo root is the Spark app root. Root `main.py` imports this nested
  FastAPI app so Spark's default Python entrypoint can run it.
- Spark injects `PORT`, `REDIS_URL`, `CRON_SECRET`, and `OUTCOMES_API_KEY` at
  runtime. The app must bind to `0.0.0.0` on `PORT`; uvicorn handles this when
  Spark uses the default Python entrypoint.
- `spark.json` owns platform health checks, resources, workers, cron jobs,
  webhooks, and ACOS-Data vendor declarations.
- Cron endpoints must verify `X-Cron-Secret` against `CRON_SECRET`.
- Webhook endpoints must validate their own secrets or signatures because Spark
  webhook ingress bypasses Cloudflare Access.
- Redis is a Spark sidecar and is ephemeral. Do not use the web process to
  enqueue manual jobs into localhost Redis for a separate worker deployment;
  each deployment may have its own sidecar.

## Guardrails

- Do not write to real ActiveCampaign accounts during development; use mocked AC
  responses and `respx` tests.
- Keep SQL in `sql/extractors/` or `sql/migrations/`, not embedded in Python.
- Confirm the Snowflake-to-ActiveCampaign account mapping source before building
  any production write path that depends on account IDs.
- Treat the audit log as the operational source of truth for field-write attempts.
