import json
from typing import Any

import structlog

from app.ac_client.api import ActiveCampaignAPI
from app.audit import log_write

logger = structlog.get_logger(__name__)


class FieldWriter:
    def __init__(self, api: ActiveCampaignAPI):
        self._api = api

    async def write_account_fields(
        self,
        run_id: str,
        account_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        account_response = await self._api.get_account(account_id)
        current_fields = _extract_current_fields(account_response)
        target_fields = _extract_target_fields(payload)
        changed_fields = {
            field_name: new_value
            for field_name, new_value in target_fields.items()
            if current_fields.get(field_name) != new_value
        }

        if not changed_fields:
            await log_write(
                run_id=run_id,
                account_id=account_id,
                field_name="*",
                old_value=json.dumps(current_fields, sort_keys=True),
                new_value=json.dumps(target_fields, sort_keys=True),
                status="skipped_unchanged",
            )
            return {"status": "skipped_unchanged", "changed_fields": []}

        try:
            response = await self._api.update_account_custom_fields(account_id, changed_fields)
        except Exception as exc:
            for field_name, new_value in changed_fields.items():
                await log_write(
                    run_id=run_id,
                    account_id=account_id,
                    field_name=field_name,
                    old_value=current_fields.get(field_name),
                    new_value=new_value,
                    status="failed",
                    error_message=str(exc),
                )
            raise

        for field_name, new_value in changed_fields.items():
            await log_write(
                run_id=run_id,
                account_id=account_id,
                field_name=field_name,
                old_value=current_fields.get(field_name),
                new_value=new_value,
                status="success",
            )

        logger.info(
            "ac_fields_updated",
            account_id=account_id,
            changed_field_count=len(changed_fields),
        )
        return {
            "status": "success",
            "changed_fields": list(changed_fields.keys()),
            "response": response,
        }

    async def write_accounts_bulk(
        self,
        run_id: str,
        account_payloads: dict[int, dict[str, Any]],
    ) -> dict[int, dict[str, Any]]:
        changed_updates: list[tuple[int, dict[str, Any]]] = []
        diff_by_account: dict[int, dict[str, Any]] = {}
        result_by_account: dict[int, dict[str, Any]] = {}

        for account_id, payload in account_payloads.items():
            account_response = await self._api.get_account(account_id)
            current_fields = _extract_current_fields(account_response)
            target_fields = _extract_target_fields(payload)
            changed_fields = {
                field_name: new_value
                for field_name, new_value in target_fields.items()
                if current_fields.get(field_name) != new_value
            }
            if not changed_fields:
                await log_write(
                    run_id=run_id,
                    account_id=account_id,
                    field_name="*",
                    old_value=json.dumps(current_fields, sort_keys=True),
                    new_value=json.dumps(target_fields, sort_keys=True),
                    status="skipped_unchanged",
                )
                result_by_account[account_id] = {
                    "status": "skipped_unchanged",
                    "changed_fields": [],
                }
                continue

            changed_updates.append((account_id, changed_fields))
            diff_by_account[account_id] = changed_fields

        if not changed_updates:
            return result_by_account

        await self._api.bulk_update_account_custom_fields(tuple(changed_updates))
        for account_id, changed_fields in diff_by_account.items():
            for field_name, new_value in changed_fields.items():
                await log_write(
                    run_id=run_id,
                    account_id=account_id,
                    field_name=field_name,
                    old_value=None,
                    new_value=new_value,
                    status="success",
                )
            result_by_account[account_id] = {
                "status": "success",
                "changed_fields": list(changed_fields.keys()),
            }
        return result_by_account


async def write_account_fields(
    account_id: int,
    payload: dict[str, Any],
    *,
    run_id: str,
    writer: FieldWriter,
) -> dict[str, Any]:
    return await writer.write_account_fields(run_id=run_id, account_id=account_id, payload=payload)


def _extract_target_fields(payload: dict[str, Any]) -> dict[str, Any]:
    ignored_keys = {"account_id", "updated_at"}
    fields = {
        key: value
        for key, value in payload.items()
        if key not in ignored_keys and value is not None
    }
    if "account_id" in payload and payload["account_id"] is not None:
        fields["cs_snowflake_account_id"] = payload["account_id"]
    return fields


def _extract_current_fields(account_response: dict[str, Any]) -> dict[str, Any]:
    account = account_response.get("account", account_response)
    fields = account.get("fields", [])
    current: dict[str, Any] = {}

    if isinstance(fields, dict):
        return dict(fields)

    if isinstance(fields, list):
        for item in fields:
            if not isinstance(item, dict):
                continue
            field_name = item.get("field") or item.get("name")
            if isinstance(field_name, str):
                current[field_name] = item.get("value")
    return current
