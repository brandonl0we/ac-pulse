import subprocess
from pathlib import Path

import structlog
from arq.connections import RedisSettings, create_pool
from fastapi import FastAPI, HTTPException

from app.ac_client.api import ActiveCampaignAPI
from app.ac_client.field_bootstrap import AccountFieldBootstrapper
from app.audit import configure_audit, get_last_success_by_worker, get_recent_audit_rows
from app.config import get_settings
from app.logging_setup import configure_logging
from app.snowflake_client import SnowflakeClient

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
    version = settings.git_sha or _git_sha_from_repo()
    try:
        worker_last_success = await get_last_success_by_worker()
    except Exception:
        logger.exception("healthz_worker_lookup_failed")
        worker_last_success = {
            "nightly": None,
            "monthly": None,
            "weekly_snapshot": None,
            "on_demand": None,
        }
    logger.debug("health_check", version=version)
    return {"status": "ok", "version": version, "workers": worker_last_success}


@app.post("/resync/{account_id}")
async def resync(account_id: int) -> dict[str, str]:
    try:
        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        job = await redis.enqueue_job("run_on_demand", account_id)
        await redis.aclose()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to enqueue resync job: {exc}") from exc
    if job is None:
        raise HTTPException(status_code=500, detail="Failed to create resync job")
    return {"job_id": job.job_id}


@app.get("/audit/recent")
async def audit_recent() -> dict[str, object]:
    rows = await get_recent_audit_rows(limit=100)
    return {"rows": rows}


@app.post("/admin/bootstrap-account-fields")
async def bootstrap_account_fields() -> dict[str, object]:
    async with ActiveCampaignAPI(
        base_url=settings.ac_api_url,
        api_key=settings.ac_api_key,
    ) as api:
        bootstrapper = AccountFieldBootstrapper(api)
        return await bootstrapper.ensure_required_fields()
