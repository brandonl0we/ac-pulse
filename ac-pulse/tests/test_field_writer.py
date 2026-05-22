from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.ac_client.field_writer import FieldWriter


@pytest.mark.asyncio
async def test_field_writer_skips_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    audit_calls: list[dict[str, Any]] = []

    async def fake_log_write(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    monkeypatch.setattr("app.ac_client.field_writer.log_write", fake_log_write)
    api = AsyncMock()
    api.get_account.return_value = {
        "account": {
            "fields": [
                {"field": "cs_priority_tier", "value": "High"},
                {"field": "cs_intervention_due", "value": True},
                {"field": "cs_snowflake_account_id", "value": 101},
            ]
        }
    }
    writer = FieldWriter(api)

    result = await writer.write_account_fields(
        run_id="run-1",
        account_id=101,
        payload={
            "account_id": 101,
            "cs_priority_tier": "High",
            "cs_intervention_due": True,
        },
    )

    assert result["status"] == "skipped_unchanged"
    api.update_account_custom_fields.assert_not_called()
    assert audit_calls[0]["status"] == "skipped_unchanged"


@pytest.mark.asyncio
async def test_field_writer_updates_only_changed_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    audit_calls: list[dict[str, Any]] = []

    async def fake_log_write(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    monkeypatch.setattr("app.ac_client.field_writer.log_write", fake_log_write)
    api = AsyncMock()
    api.get_account.return_value = {
            "account": {
                "fields": [
                    {"field": "cs_priority_tier", "value": "Standard"},
                    {"field": "cs_intervention_due", "value": False},
                    {"field": "cs_health_status", "value": "Healthy"},
                    {"field": "cs_next_best_action", "value": "Maintain normal cadence"},
                    {
                        "field": "cs_priority_reason",
                        "value": "No elevated customer success risk detected.",
                    },
                    {"field": "cs_renewal_motion", "value": "Mid-Cycle"},
                    {"field": "cs_owner_attention", "value": False},
                    {"field": "cs_snowflake_account_id", "value": 202},
                ]
            }
    }
    api.update_account_custom_fields.return_value = {"ok": True}
    writer = FieldWriter(api)

    result = await writer.write_account_fields(
        run_id="run-2",
        account_id=202,
        payload={
            "account_id": 202,
            "cs_priority_tier": "Critical",
            "cs_intervention_due": False,
            "cs_health_status": "Critical",
            "cs_next_best_action": "Prepare renewal save plan",
            "cs_priority_reason": "Churn band is Very High.",
            "cs_renewal_motion": "Renewing Soon",
            "cs_owner_attention": True,
        },
    )

    assert result["status"] == "success"
    api.update_account_custom_fields.assert_awaited_once_with(
        202,
        {
            "cs_priority_tier": "Critical",
            "cs_health_status": "Critical",
            "cs_next_best_action": "Prepare renewal save plan",
            "cs_priority_reason": "Churn band is Very High.",
            "cs_renewal_motion": "Renewing Soon",
            "cs_owner_attention": True,
        },
    )
    assert len(audit_calls) == 6
    assert audit_calls[0]["field_name"] == "cs_priority_tier"
