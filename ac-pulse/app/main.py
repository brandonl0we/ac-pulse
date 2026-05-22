import subprocess
import time
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.ac_client.api import ActiveCampaignAPI
from app.ac_client.field_bootstrap import AccountFieldBootstrapper
from app.audit import configure_audit, get_last_success_by_worker, get_recent_audit_rows
from app.config import get_settings
from app.extractors.acai import ACAIExtractor
from app.extractors.churn import ChurnExtractor
from app.extractors.nbn import NBNExtractor
from app.extractors.renewal import RenewalExtractor
from app.extractors.touchpoints import TouchpointsExtractor
from app.extractors.utilization import UtilizationExtractor
from app.logging_setup import configure_logging
from app.lookup_service import lookup_customer_by_email
from app.portfolio import build_success_rep_portfolio
from app.pulse import build_account_pulse, build_account_resolver
from app.snowflake_client import SnowflakeClient
from app.workers.on_demand import run_on_demand

settings = get_settings()
configure_logging(settings.log_level)
logger = structlog.get_logger(__name__)
app = FastAPI(title="ac-pulse", version="0.1.0")
configure_audit(SnowflakeClient(settings))

# Lazy Redis client for the lookup-result cache. We don't open a
# connection at module load (Spark may start the web process before
# Redis is reachable); the first /lookup call resolves it.
_redis_client: Redis | None = None

INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ac-pulse</title>
  <style>
    :root { color-scheme: light; --ink:#1f2933; --muted:#667085; --line:#d9e2ec; --bg:#f7f9fc; --panel:#fff; --accent:#0f766e; --risk:#b42318; }
    * { box-sizing: border-box; }
    body { margin:0; background:var(--bg); color:var(--ink); font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    header { padding:24px 28px 14px; border-bottom:1px solid var(--line); background:var(--panel); position:sticky; top:0; z-index:2; }
    h1 { margin:0; font-size:24px; letter-spacing:0; }
    .bar { display:flex; gap:12px; align-items:center; margin-top:16px; flex-wrap:wrap; }
    input { width:min(360px, 100%); padding:10px 12px; border:1px solid #b8c4d4; border-radius:6px; font-size:14px; }
    button { border:0; border-radius:6px; background:var(--accent); color:white; padding:10px 14px; font-weight:700; cursor:pointer; }
    main { padding:24px 28px 40px; max-width:1400px; margin:0 auto; }
    .status { color:var(--muted); font-size:14px; margin-bottom:18px; }
    .kpis { display:grid; grid-template-columns: repeat(5, minmax(160px, 1fr)); gap:12px; margin-bottom:22px; }
    .kpi { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; }
    .label { color:var(--muted); font-size:12px; text-transform:uppercase; font-weight:800; letter-spacing:.04em; }
    .value { font-size:24px; font-weight:800; margin-top:6px; }
    table { width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--line); border-radius:8px; overflow:hidden; }
    th, td { padding:10px 12px; border-bottom:1px solid var(--line); text-align:left; font-size:13px; vertical-align:top; }
    th { background:#eef3f8; color:#334e68; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
    tr:last-child td { border-bottom:0; }
    .num { text-align:right; white-space:nowrap; }
    .pill { display:inline-block; padding:3px 8px; border-radius:999px; background:#e6fffb; color:#0f766e; font-weight:700; }
    .pill.risk { background:#fee4e2; color:var(--risk); }
    .reason { color:var(--muted); max-width:520px; }
    @media (max-width: 900px) { .kpis { grid-template-columns: repeat(2, minmax(140px, 1fr)); } table { display:block; overflow-x:auto; } }
  </style>
</head>
<body>
  <header>
    <h1>ac-pulse</h1>
    <div class="bar">
      <input id="rep" value="Kevin Oostema" aria-label="Success rep name" />
      <button id="load">Load Portfolio</button>
    </div>
  </header>
  <main>
    <div id="status" class="status">Loading portfolio...</div>
    <section id="kpis" class="kpis"></section>
    <table>
      <thead>
        <tr>
          <th>Account</th>
          <th class="num">ARR</th>
          <th>Health</th>
          <th>Action</th>
          <th>Reason</th>
          <th class="num">Last TP</th>
        </tr>
      </thead>
      <tbody id="rows"></tbody>
    </table>
  </main>
  <script>
    const statusEl = document.getElementById("status");
    const kpisEl = document.getElementById("kpis");
    const rowsEl = document.getElementById("rows");
    const repEl = document.getElementById("rep");

    const money = value => new Intl.NumberFormat("en-US", {
      style: "currency", currency: "USD", maximumFractionDigits: 0
    }).format(value || 0);

    function kpi(label, value) {
      return `<div class="kpi"><div class="label">${label}</div><div class="value">${value}</div></div>`;
    }

    async function loadPortfolio() {
      const rep = repEl.value.trim() || "Kevin Oostema";
      statusEl.textContent = `Loading ${rep}...`;
      kpisEl.innerHTML = "";
      rowsEl.innerHTML = "";
      const response = await fetch(`/portfolio?rep_name=${encodeURIComponent(rep)}`);
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text.slice(0, 500));
      }
      const data = await response.json();
      const summary = data.summary;
      statusEl.textContent = `${data.success_rep_name} portfolio generated at ${new Date(data.generated_at).toLocaleString()}`;
      kpisEl.innerHTML = [
        kpi("Accounts", summary.account_count),
        kpi("Total ARR", money(summary.total_arr)),
        kpi("Owner Attention", summary.owner_attention_count),
        kpi("High Churn ARR", money(summary.high_or_very_high_churn_arr)),
        kpi("Detractor ARR", money(summary.nps_detractor_arr))
      ].join("");
      rowsEl.innerHTML = data.accounts.slice(0, 50).map(account => {
        const command = account.command;
        const riskClass = ["Critical", "At Risk"].includes(command.health_status) ? " risk" : "";
        const days = account.touchpoints.days_since_last_touchpoint;
        return `<tr>
          <td><strong>${account.account_name || account.account_id}</strong><br><span class="status">${account.plan_tier_name || ""}</span></td>
          <td class="num">${money(account.arr)}</td>
          <td><span class="pill${riskClass}">${command.health_status}</span></td>
          <td>${command.next_best_action}</td>
          <td class="reason">${command.priority_reason}</td>
          <td class="num">${days == null ? "None" : `${days}d`}</td>
        </tr>`;
      }).join("");
    }

    document.getElementById("load").addEventListener("click", () => loadPortfolio().catch(showError));
    function showError(error) {
      statusEl.textContent = `Unable to load portfolio: ${error.message}`;
    }
    loadPortfolio().catch(showError);
  </script>
</body>
</html>
"""  # noqa: E501


def _get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def _git_sha_from_repo() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    try:
        output = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root)
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return output.decode("utf-8").strip()


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return INDEX_HTML


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    """Liveness probe — does NOT call any external service.

    Kubernetes uses this to decide if the process should be restarted.
    A previous version of this handler called Snowflake on every request,
    which crashed deploys when Snowflake's network policy didn't include
    the Spark egress IP — the TCP connect timed out, the probe failed,
    Kubernetes restarted the container, and the loop repeated forever.

    Liveness must depend ONLY on process state. Dependency health belongs
    on /readyz.
    """
    version = settings.git_sha or _git_sha_from_repo()
    return {"status": "ok", "version": version}


@app.get("/readyz")
async def readyz() -> dict[str, object]:
    """Readiness probe — checks dependency health.

    Calls Snowflake to verify auth + network reachability + grants.
    Always returns HTTP 200; the body's `status` field reflects truth
    ("ok" / "degraded"). This separates the question "should the process
    run" (liveness) from "can it actually serve" (readiness).

    Hit this after a deploy to validate the Snowflake JWT chain. If
    snowflake.status === "down" with a TCP error, the Spark egress IP
    (see runtime logs) needs to be whitelisted in Snowflake's network
    policy.
    """
    version = settings.git_sha or _git_sha_from_repo()
    client = SnowflakeClient(settings)

    snowflake_status: dict[str, object] = {"status": "ok"}
    try:
        await client.execute("SELECT 1 AS ping", None)
    except Exception as exc:
        logger.exception("readyz_snowflake_ping_failed")
        snowflake_status = {"status": "down", "error": str(exc)[:1000]}

    worker_last_success: dict[str, object]
    if settings.snowflake_backend == "zapier_mcp":
        worker_last_success = {
            "status": "skipped",
            "reason": "audit history requires the direct Snowflake backend",
            "nightly": None,
            "monthly": None,
            "weekly_snapshot": None,
            "on_demand": None,
        }
    else:
        try:
            worker_last_success = dict(await get_last_success_by_worker())
        except Exception as exc:
            logger.exception("readyz_worker_lookup_failed")
            worker_last_success = {
                "error": str(exc)[:1000],
                "nightly": None,
                "monthly": None,
                "weekly_snapshot": None,
                "on_demand": None,
            }

    overall = "ok" if snowflake_status["status"] == "ok" else "degraded"
    logger.debug("readyz_check", version=version, status=overall)
    return {
        "status": overall,
        "version": version,
        "snowflake_backend": settings.snowflake_backend,
        "snowflake": snowflake_status,
        "workers": worker_last_success,
    }


@app.post("/resync/{account_id}")
async def resync(account_id: int) -> dict[str, Any]:
    try:
        return await run_on_demand({}, account_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to resync account: {exc}") from exc


@app.get("/audit/recent")
async def audit_recent() -> dict[str, object]:
    rows = await get_recent_audit_rows(limit=100)
    return {"rows": rows}


@app.get("/portfolio/{rep_name}")
async def success_rep_portfolio(rep_name: str) -> dict[str, Any]:
    try:
        return await build_success_rep_portfolio(
            snowflake_client=SnowflakeClient(settings),
            rep_name=rep_name,
        )
    except Exception as exc:
        logger.exception("success_rep_portfolio_failed", rep_name=rep_name)
        raise HTTPException(
            status_code=500,
            detail=f"Unable to build portfolio: {str(exc)[:1000]}",
        ) from exc


@app.get("/portfolio")
async def success_rep_portfolio_query(rep_name: str = Query(...)) -> dict[str, Any]:
    return await success_rep_portfolio(rep_name)


@app.get("/pulse/{account_id}")
async def account_pulse(account_id: int) -> dict[str, Any]:
    snowflake_client = SnowflakeClient(settings)
    extractors = [
        ChurnExtractor(snowflake_client),
        ACAIExtractor(snowflake_client),
        NBNExtractor(snowflake_client),
        UtilizationExtractor(snowflake_client),
        TouchpointsExtractor(snowflake_client),
        RenewalExtractor(snowflake_client),
    ]
    pulse = await build_account_pulse(
        snowflake_account_id=account_id,
        extractor_instances=extractors,
        resolver=build_account_resolver(settings.account_id_map_path),
    )
    if pulse is None:
        raise HTTPException(status_code=404, detail="No account pulse found")
    return pulse


def _require_service_key(provided: str | None) -> None:
    """Shared-secret gate for cross-service endpoints.

    Other Spark agents that call ac-pulse pass their secret via the
    X-Service-Key header. If SERVICE_API_KEY isn't configured, the
    endpoint 503s rather than running unauthed.
    """
    if not settings.service_api_key:
        raise HTTPException(
            status_code=503,
            detail="SERVICE_API_KEY not configured on this deployment",
        )
    if provided != settings.service_api_key:
        raise HTTPException(status_code=401, detail="invalid service key")


@app.get("/admin/smoke-snowflake")
async def smoke_snowflake(
    x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
    activehosted_id: str | None = Query(
        default=None,
        description="If provided, look up this specific account's projected ARR. "
        "Otherwise the smoke test returns one sample row.",
    ),
) -> dict[str, object]:
    """End-to-end smoke test of the Snowflake JWT connection.

    Queries AC.CONFORMED_DIMENSIONS.EXPECTED_ARR_MODEL_PREDICTIONS — the
    same canonical table from the example connection — to prove:
      1. PEM private key parsed correctly
      2. JWT auth handshake succeeded
      3. The role has SELECT grants on the conformed dimensions schema
      4. Results return as expected dicts

    Useful as a deploy-time validation and as a real lookup demo of the
    shape future service endpoints will use.
    """
    _require_service_key(x_service_key)

    if activehosted_id:
        sql = (
            "SELECT ACCOUNT_ID, ACTIVEHOSTED_ID, PROJECTED_ARR, "
            "PROJECTED_ARR_PREDICTION_TIMESTAMP "
            "FROM AC.CONFORMED_DIMENSIONS.EXPECTED_ARR_MODEL_PREDICTIONS "
            "WHERE ACTIVEHOSTED_ID = %(activehosted_id)s "
            "LIMIT 5"
        )
        params: dict[str, Any] = {"activehosted_id": activehosted_id}
    else:
        sql = (
            "SELECT ACCOUNT_ID, ACTIVEHOSTED_ID, PROJECTED_ARR, "
            "PROJECTED_ARR_PREDICTION_TIMESTAMP "
            "FROM AC.CONFORMED_DIMENSIONS.EXPECTED_ARR_MODEL_PREDICTIONS "
            "LIMIT 1"
        )
        params = {}

    client = SnowflakeClient(settings)
    started = time.monotonic()
    try:
        rows = await client.execute(sql, params)
    except Exception as exc:
        logger.exception("smoke_snowflake_failed", activehosted_id=activehosted_id)
        raise HTTPException(
            status_code=500,
            detail=f"Snowflake query failed: {str(exc)[:300]}",
        ) from exc
    elapsed_ms = int((time.monotonic() - started) * 1000)

    logger.info(
        "smoke_snowflake_ok",
        rows=len(rows),
        elapsed_ms=elapsed_ms,
        activehosted_id=activehosted_id,
    )
    return {
        "status": "ok",
        "account": settings.snowflake_account,
        "user": settings.snowflake_user,
        "warehouse": settings.snowflake_warehouse,
        "database": settings.snowflake_database,
        "schema": settings.snowflake_schema,
        "query": sql,
        "row_count": len(rows),
        "elapsed_ms": elapsed_ms,
        "rows": rows,
    }


class LookupEmailRequest(BaseModel):
    email: str = Field(..., min_length=3, description="Email address to dedupe-check.")


@app.post("/lookup/customer-by-email")
async def lookup_customer_by_email_route(
    body: LookupEmailRequest,
    x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
    debug: int = Query(
        default=0,
        description="Pass ?debug=1 to include raw SQL + Zapier response preview.",
    ),
) -> dict[str, Any]:
    """Cross-agent dedupe lookup: is this email an AC customer?

    Six-source footprint check against the Snowflake warehouse. Backed
    today by Zapier MCP (BI's pre-authed Snowflake connection); will
    swap to direct Snowflake once the network policy whitelists the
    Spark egress IP. Callers get the same response shape either way.

    Response shape (see app/lookup_service.shape_response):
      {
        "input_email": "user@company.com",
        "input_domain": "company.com",
        "is_customer": true,            // any Active Paid account match
        "is_known": true,               // any hit at all
        "highest_value_match": {...},   // best ACCOUNT row by ARR, if any
        "exact_email_matches": [...],
        "by_record_type": {ACCOUNT: [...], DEAL: [...], CONTACT: [...], ORG: [...]},
        "summary": {accounts, deals, contacts, orgs, active_paid_accounts},
        "cached": false,
        "elapsed_ms": 1234,
        "source": "zapier_mcp"
      }

    Failure modes return is_customer=null + reason=lookup_unavailable so
    calling agents fail-closed (don't email someone we can't dedupe).
    """
    _require_service_key(x_service_key)
    return await lookup_customer_by_email(
        settings=settings,
        redis=_get_redis(),
        email=body.email,
        force_refresh=bool(debug),  # bypass cache when debugging
        debug=bool(debug),
    )


@app.post("/admin/bootstrap-account-fields")
async def bootstrap_account_fields() -> dict[str, object]:
    async with ActiveCampaignAPI(
        base_url=settings.ac_api_url,
        api_key=settings.ac_api_key,
    ) as api:
        bootstrapper = AccountFieldBootstrapper(api)
        return await bootstrapper.ensure_required_fields()
