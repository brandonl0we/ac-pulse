# ac-pulse Product Brief

## Product Thesis

ac-pulse is a customer success operating layer built on top of an
ActiveCampaign account. The goal is to replace the day-to-day workflow surface
of Totango while keeping customer, sales, marketing, and lifecycle context in
ActiveCampaign instead of splitting it across a separate CS platform.

The first version should make ActiveCampaign the shared system of action:
customer health, renewal risk, CSM touchpoint gaps, and intervention priority
are written back to account-level fields so existing AC segments, automations,
pipelines, and internal workflows can act on them.

## Current Foundation

- Snowflake is the analytics source for churn, ACAI, NBN, utilization,
  renewal, touchpoint, and customer-footprint signals.
- ActiveCampaign is the operational surface where account fields are updated.
- FastAPI exposes health, readiness, resync, audit, field bootstrap, Snowflake
  smoke-test, and cross-agent customer lookup endpoints.
- arq workers run scheduled sync and snapshot jobs.
- Snowflake audit tables track field-write attempts and weekly account state.
- The service already has guardrails for idempotent AC writes, mocked tests, and
  no real account writes during development.

## Totango Replacement Map

| Totango-style capability | ac-pulse equivalent |
| --- | --- |
| Health score | `cs_priority_tier`, churn band, churn score, utilization, ACAI, NBN |
| Success plays | AC automations and segments triggered from account custom fields |
| Renewal risk | `days_to_renewal`, renewal date, churn band, intervention flag |
| Touchpoint tracking | `days_since_touchpoint`, `touchpoint_count_30d` |
| Account timeline | Future: AC notes/tasks/deals plus Snowflake snapshot history |
| CSM work queue | Future: prioritized account list backed by synced account fields |
| Executive reporting | Snowflake `CS_ANALYTICS.ACCOUNT_STATE_WEEKLY` snapshots |

## Near-Term Build Direction

1. Expand the account signal model from raw metrics into an explicit CS command
   object: health status, renewal motion, recommended action, reason text, and
   owner-visible urgency.
2. Write those fields back into AC so a CSM or sales rep can see why an account
   needs attention without leaving the account record.
3. Add a read endpoint for an account pulse summary so future UI, Slack, or
   agent surfaces can render the same canonical narrative.
4. Keep ActiveCampaign as the primary work surface: use external UI or Slack as
   triage support, not the source of truth.

## Command Fields

- `cs_health_status`: Healthy, Watch, At Risk, Critical
- `cs_next_best_action`: short action label for the CSM or account owner
- `cs_priority_reason`: concise human-readable explanation
- `cs_renewal_motion`: Renewing Soon, Mid-Cycle, Renewal Not Set, Overdue
- `cs_owner_attention`: boolean flag for account-owner workflow triggers

## Product Guardrails

- Do not duplicate the customer record outside ActiveCampaign unless it is for
  analytics, cache, or audit.
- Do not make CSMs infer priority from raw scores. Surface the action and the
  reason together.
- Keep writes idempotent and observable; every AC field mutation should be
  diffed and audit logged.
- Treat Snowflake snapshots as historical truth and AC fields as current
  operational state.
