import subprocess
import time
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, Header, HTTPException, Query

from app.ac_client.api import ActiveCampaignAPI
from app.ac_client.field_bootstrap import AccountFieldBootstrapper
from app.audit import configure_audit, get_last_success_by_worker, get_recent_audit_rows
from app.config import get_settings
from app.logging_setup import configure_logging
from app.snowflake_client import SnowflakeClient
from app.workers.on_demand import run_on_demand

settings = get_settings()
configure_logging(settings.log_level)
logger = structlog.get_logger(__name__)
app = FastAPI(title="ac-pulse", version="0.1.0")
configure_audit(SnowflakeClient(settings))


def _git_sha_from_repo() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    try:
        output = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root)
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return output.decode("utf-8").strip()


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

    worker_last_success: dict[str, str | None]
    try:
        worker_last_success = await get_last_success_by_worker()
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


@app.post("/admin/bootstrap-account-fields")
async def bootstrap_account_fields() -> dict[str, object]:
    async with ActiveCampaignAPI(
        base_url=settings.ac_api_url,
        api_key=settings.ac_api_key,
    ) as api:
        bootstrapper = AccountFieldBootstrapper(api)
        return await bootstrapper.ensure_required_fields()
