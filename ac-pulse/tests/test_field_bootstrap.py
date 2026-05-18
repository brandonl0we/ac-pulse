from unittest.mock import AsyncMock

import pytest

from app.ac_client.field_bootstrap import AccountFieldBootstrapper, RequiredAccountField


@pytest.mark.asyncio
async def test_bootstrap_creates_missing_fields() -> None:
    api = AsyncMock()
    api.get_account_custom_fields.return_value = [{"fieldName": "churn_score"}]
    bootstrapper = AccountFieldBootstrapper(api)
    required = (
        RequiredAccountField("churn_score", "Churn Score", "number"),
        RequiredAccountField("cs_priority_tier", "CS Priority Tier", "text"),
    )

    summary = await bootstrapper.ensure_required_fields(required)

    api.create_account_custom_field.assert_awaited_once_with(
        field_name="cs_priority_tier",
        field_label="CS Priority Tier",
        field_type="text",
    )
    assert summary["created"] == ["cs_priority_tier"]
    assert summary["skipped_existing"] == ["churn_score"]


@pytest.mark.asyncio
async def test_bootstrap_skips_when_all_fields_exist() -> None:
    api = AsyncMock()
    api.get_account_custom_fields.return_value = [
        {"fieldName": "churn_score"},
        {"fieldName": "cs_priority_tier"},
    ]
    bootstrapper = AccountFieldBootstrapper(api)
    required = (
        RequiredAccountField("churn_score", "Churn Score", "number"),
        RequiredAccountField("cs_priority_tier", "CS Priority Tier", "text"),
    )

    summary = await bootstrapper.ensure_required_fields(required)

    api.create_account_custom_field.assert_not_awaited()
    assert summary["created"] == []
    assert summary["required_total"] == 2
