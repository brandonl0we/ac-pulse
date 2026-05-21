# Claude Code Prompt — Build `ac-pulse`

> Paste this entire file into Claude Code as the opening message in a fresh repo, or save it as `BUILD_PROMPT.md` at the repo root and reference it. After the initial build, distill the still-relevant sections into a `CLAUDE.md` for ongoing context.

---

## Mission

Build a production-grade Python service that reads customer success signals from Snowflake, persists historical snapshots for clean point-in-time analytics, and writes ~25 derived signals to ActiveCampaign account-level custom fields. The service makes AC the operational surface for CS workflows (segmentation, automations, personalization, alerts) without needing a separate CS platform like Totango.

The model is already validated. The hard part isn't analytics — it's clean, idempotent, observable data movement at scale.

---

## Who I Am, What I'm Building, Why

I'm Principal AI Automation at ActiveCampaign. I built an outbound prospecting service on this same stack (FastAPI + Redis + arq on Fly.io) and this service mirrors that pattern intentionally — don't invent new architecture.

We've already validated:
- AC's churn ML model (`VELOCITY_CHURN_MODEL.ACCOUNT_FEATURE_CHURN_PREDICTION_DRIVERS_BY_MONTH`) has 3.5× lift on its top band ("Very High") with clean monotonic discrimination across bands. It's the spine.
- ~16K accounts/year are flagged Very High but receive zero CSM touchpoints. The leverage is automation at SMB volume, not better scoring.
- `C360_ACCOUNT_DETAILS` and `ACCOUNT_EXTENSION` are NOT safe for point-in-time historical analytics — they leak post-churn state (ARR → 0, plan_tier → null on churn). The snapshot layer in this service exists to fix that.

---

## Stack & Conventions (non-negotiable)

- **Python 3.12**
- **uv** for dependency management — `pyproject.toml`, `uv.lock`
- **FastAPI** for the HTTP layer (health endpoint, on-demand resync endpoint)
- **arq** for async job queue + cron scheduling
- **Redis** as the arq broker (Upstash on Fly.io)
- **snowflake-connector-python** for Snowflake reads, **wrap sync calls in `asyncio.to_thread`** so they don't block the event loop
- **httpx** (async client) for ActiveCampaign API calls
- **pydantic v2** for data models, **pydantic-settings** for env-var config
- **structlog** for structured JSON logging (Fly.io picks it up natively)
- **pytest** + **pytest-asyncio** + **respx** (httpx mock) for tests
- **ruff** for linting + formatting (no black, no isort — ruff handles both)
- **mypy** in strict mode for types
- **Fly.io** for deployment — `fly.toml` configured for a single app with a worker process

Code style:
- Type hints everywhere. mypy strict.
- No bare `except`. Catch specific exceptions, log structured, re-raise or dead-letter.
- One class per file unless the classes are tightly coupled.
- SQL lives in sibling `.sql` files next to the extractor that owns it, not as Python string constants. Analysts will read and edit these — make them clean.
- Don't write docstrings on obvious functions. Do write docstrings on extractors explaining what the source represents, refresh cadence, and known gotchas (especially the point-in-time stuff).

---

## Repo Structure (create exactly this)

```
ac-pulse/
├── pyproject.toml
├── uv.lock
├── README.md
├── fly.toml
├── .env.example
├── .gitignore
├── .python-version
├── ruff.toml
├── BUILD_PROMPT.md          # this file
├── CLAUDE.md                # distilled ongoing context (write LAST)
├── sql/
│   ├── migrations/
│   │   ├── 001_create_cs_analytics_schema.sql
│   │   ├── 002_account_state_weekly.sql
│   │   └── 003_ac_pulse_audit_log.sql
│   └── extractors/
│       ├── churn.sql
│       ├── acai.sql
│       ├── nbn.sql
│       ├── utilization.sql
│       ├── touchpoints.sql
│       └── renewal.sql
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app
│   ├── config.py            # pydantic-settings Settings class
│   ├── logging_setup.py     # structlog config
│   ├── snowflake_client.py  # async-wrapped Snowflake client
│   ├── models.py            # pydantic models for account signals
│   ├── extractors/
│   │   ├── __init__.py
│   │   ├── base.py          # abstract Extractor
│   │   ├── churn.py
│   │   ├── acai.py
│   │   ├── nbn.py
│   │   ├── utilization.py
│   │   ├── touchpoints.py
│   │   └── renewal.py
│   ├── transformer.py       # derives priority_tier, intervention_due
│   ├── snapshot.py          # writes ACCOUNT_STATE_WEEKLY
│   ├── ac_client/
│   │   ├── __init__.py
│   │   ├── api.py           # httpx wrapper, rate limiting, retries
│   │   ├── field_writer.py  # idempotent custom field writes
│   │   └── account_resolver.py  # SF account_id <-> AC account_id
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── settings.py      # arq WorkerSettings
│   │   ├── nightly.py
│   │   ├── monthly.py
│   │   ├── weekly_snapshot.py
│   │   └── on_demand.py
│   ├── audit.py             # writes AC_PULSE_AUDIT_LOG
│   └── alerts.py            # Slack webhook for failures
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── fixtures/
    │   ├── snowflake_churn.json
    │   ├── snowflake_acai.json
    │   └── ac_account_response.json
    ├── test_transformer.py
    ├── test_field_writer.py
    ├── test_extractors.py
    └── test_workers.py
```

---

## Implementation Phases (build in this order, don't skip ahead)

Each phase ends with a verifiable outcome. Before moving to the next phase, run tests and confirm the outcome with me.

### Phase 1 — Scaffolding (no business logic yet)

- Initialize uv project, add all deps from the Stack section
- Set up ruff, mypy, pytest config in `pyproject.toml`
- Write `app/config.py` with `Settings` class covering every env var in `.env.example`
- Write `app/logging_setup.py` with structlog JSON config
- Write `app/main.py` with FastAPI app, a `/healthz` endpoint that returns `{"status": "ok", "version": <git_sha>}`
- Write `app/snowflake_client.py` — async wrapper around `snowflake.connector`. Single `execute(sql, params)` method returning `list[dict]`. Use `asyncio.to_thread`. Connection pooled at module level.
- Write `fly.toml` for a single app, single process group (worker + http combined for v1)
- Write the three migration SQL files in `sql/migrations/`
- Write `tests/conftest.py` with reusable fixtures: mock Settings, mock Snowflake client, respx mock router
- **Outcome:** `uv run pytest` passes. `uv run uvicorn app.main:app` serves `/healthz`. Migrations apply cleanly to a Snowflake `CS_ANALYTICS` schema.

### Phase 2 — Extractors

The abstract pattern (write this first in `app/extractors/base.py`):

```python
from abc import ABC, abstractmethod
from pathlib import Path
from app.snowflake_client import SnowflakeClient
from app.models import AccountSignals

class Extractor(ABC):
    """One extractor per Snowflake source. Owns a single SQL file and a single
    transformation step from raw rows to a partial AccountSignals dict."""

    sql_file: str  # e.g. "churn.sql", relative to sql/extractors/

    def __init__(self, sf: SnowflakeClient):
        self.sf = sf

    @property
    def sql(self) -> str:
        path = Path(__file__).parent.parent.parent / "sql" / "extractors" / self.sql_file
        return path.read_text()

    @abstractmethod
    async def extract(self) -> dict[int, dict]:
        """Returns a dict keyed by account_id with the partial signal payload."""
        ...
```

For each of the six extractors:
- Put the SQL in `sql/extractors/<name>.sql` — use the queries from the spec in this repo's `BUILD_PROMPT.md` §3 (the section titled "Data Sources & Extraction Logic"). Copy them verbatim, don't reinvent.
- Implement the Python `Extractor` subclass that runs the SQL and returns `{account_id: {field: value, ...}}`
- Write a unit test using a fixture JSON for the Snowflake response, asserting the dict shape

**Outcome:** Each extractor can be run standalone, returns the right shape, has a passing test.

### Phase 3 — Snapshot Job

- Implement `app/snapshot.py` — a single `write_weekly_snapshot()` function that runs the population SQL from spec §4 against Snowflake.
- The job idempotently upserts the current week's row per account. If today's snapshot already exists for an account, skip.
- The backfill UPDATE for `churned_in_next_*` flags runs as a second statement.
- **Outcome:** Manually running the snapshot job populates `CS_ANALYTICS.ACCOUNT_STATE_WEEKLY` for all active accounts. Re-running on the same day is a no-op.

### Phase 4 — Transformer + AC Client

`app/transformer.py`:
- Pure function: takes a merged dict per account (combining all six extractors' outputs) and adds derived fields per spec §5:
  - `cs_priority_tier`: `Critical` if `churn_decile_band == "Very High"` AND `days_to_renewal <= 90`; `High` if decile in (`Very High`, `High`); else `Standard`
  - `cs_intervention_due`: True if `priority_tier in ("Critical", "High")` AND `days_since_touchpoint > 30`
- Validate the final dict against `AccountSignals` pydantic model. Reject and log if validation fails — never write garbage to AC.

`app/ac_client/api.py`:
- Async httpx wrapper. Bearer auth via env var `AC_API_KEY`. Base URL via `AC_API_URL`.
- Token-bucket rate limit: 5 req/sec global.
- Retry policy: 5 retries, exponential backoff with jitter (0.5s → 16s). Retry on 429, 5xx, network errors. Don't retry on 4xx (except 429).
- Methods: `get_account(account_id)`, `update_account_custom_fields(account_id, fields: dict)`.

`app/ac_client/field_writer.py`:
- Idempotent writer. For each account:
  1. GET current field values
  2. Diff against the new payload
  3. If no diff, log to audit as `skipped_unchanged`, skip the write
  4. If diff, PUT only the changed fields, log to audit as `success` or `failed`
- Use AC's bulk endpoint where supported.

`app/ac_client/account_resolver.py`:
- Maintains a Snowflake account_id → AC account_id mapping. For v1, build this from a Snowflake view (we'll provide the view name later — for now, stub with an env var pointing to a CSV path and load at startup).

**Stop and ask me** before this phase: confirm the Snowflake-to-AC account ID mapping source. Don't guess — wrong IDs corrupt every downstream write.

`app/audit.py`:
- One function: `log_write(run_id, account_id, field_name, old_value, new_value, status, error_message)`. Batches inserts to `CS_ANALYTICS.AC_PULSE_AUDIT_LOG` in groups of 500 rows for efficiency.

**Outcome:** Given a mock AC account and a mock signal payload, the field_writer correctly identifies the diff, makes only the necessary PUT calls, and writes audit rows. All tested with respx — NO real AC writes during the build.

### Phase 5 — Workers

`app/workers/settings.py`: arq `WorkerSettings` class with cron jobs per spec §8.

For each worker (`nightly`, `monthly`, `weekly_snapshot`, `on_demand`):
- Implement as an arq task function
- Each task: instantiate extractors → run extracts in parallel via `asyncio.gather` → merge by account_id → transform → write to AC via field_writer → emit summary metrics
- `nightly.run()`: runs daily extractors (utilization, touchpoints, renewal)
- `monthly.run()`: runs monthly extractors (churn, acai, nbn)
- `weekly_snapshot.run()`: calls `snapshot.write_weekly_snapshot()`
- `on_demand.run(account_id)`: runs all extractors for a single account, writes to AC, returns the audit log entries

Add a FastAPI endpoint `POST /resync/{account_id}` that enqueues the `on_demand` job and returns the arq job ID.

**Outcome:** Worker runs against a small set of test accounts (configurable via `LIMIT_ACCOUNTS` env var) and writes to a sandbox AC instance. End-to-end traced via audit log.

### Phase 6 — Observability

- `app/alerts.py`: Slack webhook poster. Triggers: worker failure, error rate >5%, dead-letter queue depth >100.
- Extend `/healthz` to surface last successful run timestamp per worker (from audit log).
- Add a `GET /audit/recent` endpoint returning the last 100 audit rows as JSON for quick debugging.

**Outcome:** When a worker fails, Slack alerts. When the system is healthy, `/healthz` confirms it. Audit log is queryable from the running service.

---

## Configuration — `.env.example`

```
# Snowflake
SNOWFLAKE_ACCOUNT=
SNOWFLAKE_USER=
SNOWFLAKE_PASSWORD=
SNOWFLAKE_WAREHOUSE=
SNOWFLAKE_DATABASE=
SNOWFLAKE_ROLE=

# ActiveCampaign
AC_API_URL=https://<account>.api-us1.com/api/3
AC_API_KEY=

# Redis (arq broker)
REDIS_URL=

# Slack alerts
SLACK_WEBHOOK_URL=

# Operational
LIMIT_ACCOUNTS=          # if set, only process N accounts (for testing)
ENV=development          # development | staging | production
LOG_LEVEL=INFO

# Account ID mapping (v1 stub)
ACCOUNT_ID_MAP_PATH=./data/account_id_map.csv
```

---

## What's IN scope for MVP

- Six extractors writing the 25 fields in spec §5
- Weekly snapshot job
- Idempotent AC writes with audit logging
- Slack alerting
- Three cron jobs (nightly, monthly, weekly_snapshot)
- On-demand single-account resync via HTTP endpoint
- Tests for transformer, field_writer, each extractor
- Deployable to Fly.io

## What's OUT of scope (DO NOT BUILD)

- LLM briefing generation
- Streamlit cockpit / any UI
- Real-time AC webhooks back into the service
- Auto-creation of AC custom fields (assume they're created manually first; document the names in README)
- Migration off Totango as the touchpoint source (`event_source = 'Totango'` filter stays for v1)
- Multi-tenancy or multi-AC-instance support
- Fancy CLI tooling (typer, click, etc.)
- Docker beyond what Fly.io's buildpack needs
- A database for state — Snowflake IS the state store

---

## Testing Strategy

- **DO write unit tests for:** transformer logic (every branch of priority_tier and intervention_due), field_writer diffing, AC API retry behavior, extractor SQL-to-dict shape conversion
- **DO use:** respx for httpx mocking, pytest-asyncio, fixture JSON files for Snowflake responses
- **DO NOT write:** integration tests against real Snowflake or real AC during the build. We'll set those up in a sandbox AC instance separately.
- **DO NOT** chase 100% coverage. Aim for ~80%, focused on the parts where bugs are expensive (transformer correctness, idempotency, retry logic).

---

## Definition of Done — MVP

A clean checklist. The MVP is complete when ALL of these are true:

- [ ] `uv run pytest` passes with zero failures
- [ ] `uv run ruff check .` returns clean
- [ ] `uv run mypy app` returns clean in strict mode
- [ ] `fly deploy` succeeds against a staging app
- [ ] Manually triggering `POST /resync/{account_id}` for a test account results in: Snowflake reads complete, transformer produces a valid payload, AC custom fields update, audit log rows are written
- [ ] All three cron jobs are registered in arq and trigger at the configured times
- [ ] A simulated worker failure (raise inside a task) fires a Slack alert
- [ ] README documents: how to run locally, how to deploy, the env vars required, the AC custom field names that need to exist beforehand
- [ ] `CLAUDE.md` is written as a distilled ongoing-context file (~200 lines, not 500)

---

## What to Ask Me — Don't Guess

Stop and ask before:
1. **Account ID mapping source** — confirmed at start of Phase 4. Wrong mapping = corrupt data.
2. **AC custom field creation** — do the `cs_*` fields exist in our AC instance, or do I need to create them first? Don't try to auto-create them via API in v1.
3. **Sandbox AC URL** — which AC instance should the staging deploy point to?
4. **Snowflake warehouse sizing** — if extractor queries are slow (>30s), surface it. Don't tune blindly.
5. **Slack channel for `#cs-pulse-alerts`** — confirm the webhook URL is for the right channel.

For all other ambiguities, choose the pragmatic option that matches the existing pattern in this repo, and note your choice in a code comment so I can review.

---

## Final Notes

- This codebase will be read by analysts and CSMs reviewing the SQL, not just engineers. Keep SQL files clean and commented.
- The audit log is the most important table in the system. If we can answer "what did we write to AC, when, why, and did it succeed?" we can debug anything. Don't shortcut audit coverage.
- The point-in-time hygiene problem (`C360` leaking post-churn state) is why the snapshot layer exists. Never let any new analytics depend directly on `C360_ACCOUNT_DETAILS` for historical questions — always go through `CS_ANALYTICS.ACCOUNT_STATE_WEEKLY`.
- When in doubt, mirror the patterns from my outbound prospecting service. If you find yourself inventing architecture, stop and ask.

Let's build.
