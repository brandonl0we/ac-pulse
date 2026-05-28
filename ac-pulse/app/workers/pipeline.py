from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

import structlog

from app.ac_client.account_resolver import AccountResolver
from app.ac_client.api import ActiveCampaignAPI
from app.ac_client.field_writer import FieldWriter
from app.audit import configure_audit, flush_audit_logs
from app.config import get_settings
from app.snowflake_client import SnowflakeClient
from app.transformer import transform_account_signals

logger = structlog.get_logger(__name__)


ExtractorPayload = dict[int, dict[str, object]]


class SupportsExtract(Protocol):
    async def extract(self) -> ExtractorPayload: ...


async def run_signal_sync(
    *,
    worker_name: str,
    extractor_instances: Iterable[SupportsExtract],
    account_filter: int | None = None,
) -> dict[str, int | str]:
    settings = get_settings()
    snowflake_client = SnowflakeClient(settings)
    configure_audit(snowflake_client)
    resolver = AccountResolver(settings.account_id_map_path, settings.account_id_map_json)
    run_id = f"{worker_name}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"

    extractor_results = await asyncio.gather(
        *[extractor.extract() for extractor in extractor_instances]
    )
    merged = _merge_extractor_payloads(extractor_results)
    account_ids = sorted(merged.keys())
    if account_filter is not None:
        account_ids = [account_id for account_id in account_ids if account_id == account_filter]
    if settings.limit_accounts:
        account_ids = account_ids[: settings.limit_accounts]

    processed = 0
    skipped = 0
    failed = 0
    changed = 0

    async with ActiveCampaignAPI(
        base_url=settings.ac_api_url,
        api_key=settings.ac_api_key,
    ) as api:
        writer = FieldWriter(api)
        for account_id in account_ids:
            transformed = transform_account_signals(merged[account_id])
            if transformed is None:
                skipped += 1
                continue

            try:
                ac_account_id = resolver.resolve(account_id)
            except KeyError:
                logger.warning("account_mapping_missing", account_id=account_id)
                failed += 1
                continue

            try:
                result = await writer.write_account_fields(
                    run_id=run_id,
                    account_id=ac_account_id,
                    payload=transformed.model_dump(mode="json"),
                )
            except Exception:
                failed += 1
                logger.exception("account_write_failed", account_id=account_id)
                continue

            processed += 1
            if result["status"] == "skipped_unchanged":
                skipped += 1
            else:
                changed += len(result["changed_fields"])

    await flush_audit_logs()
    return {
        "run_id": run_id,
        "worker": worker_name,
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "changed_fields": changed,
    }


def _merge_extractor_payloads(payloads: Iterable[ExtractorPayload]) -> dict[int, dict[str, object]]:
    merged: dict[int, dict[str, object]] = {}
    for payload in payloads:
        for account_id, fields in payload.items():
            merged.setdefault(account_id, {})
            merged[account_id].update(fields)
    return merged
