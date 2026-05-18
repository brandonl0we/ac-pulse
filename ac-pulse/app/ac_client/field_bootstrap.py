from dataclasses import dataclass
from typing import Any

import structlog

from app.ac_client.api import ActiveCampaignAPI

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RequiredAccountField:
    name: str
    label: str
    field_type: str = "text"


REQUIRED_ACCOUNT_FIELDS: tuple[RequiredAccountField, ...] = (
    RequiredAccountField("churn_decile_band", "Churn Decile Band", "text"),
    RequiredAccountField("churn_score", "Churn Score", "number"),
    RequiredAccountField("acai_score", "ACAI Score", "number"),
    RequiredAccountField("nbn_score", "NBN Score", "number"),
    RequiredAccountField("utilization_percent", "Utilization Percent", "number"),
    RequiredAccountField("days_since_touchpoint", "Days Since Touchpoint", "number"),
    RequiredAccountField("touchpoint_count_30d", "Touchpoint Count 30D", "number"),
    RequiredAccountField("days_to_renewal", "Days To Renewal", "number"),
    RequiredAccountField("renewal_date", "Renewal Date", "date"),
    RequiredAccountField("cs_priority_tier", "CS Priority Tier", "text"),
    RequiredAccountField("cs_intervention_due", "CS Intervention Due", "checkbox"),
    RequiredAccountField("cs_snowflake_account_id", "Snowflake Account ID", "number"),
)


class AccountFieldBootstrapper:
    def __init__(self, api: ActiveCampaignAPI):
        self._api = api

    async def ensure_required_fields(
        self,
        fields: tuple[RequiredAccountField, ...] = REQUIRED_ACCOUNT_FIELDS,
    ) -> dict[str, object]:
        existing_fields = await self._api.get_account_custom_fields()
        existing_names = _extract_existing_field_names(existing_fields)
        created: list[str] = []
        skipped: list[str] = []

        for field in fields:
            if field.name.lower() in existing_names:
                skipped.append(field.name)
                continue

            await self._api.create_account_custom_field(
                field_name=field.name,
                field_label=field.label,
                field_type=field.field_type,
            )
            created.append(field.name)

        logger.info(
            "ac_field_bootstrap_complete",
            created_count=len(created),
            skipped_count=len(skipped),
        )
        return {
            "created": created,
            "skipped_existing": skipped,
            "required_total": len(fields),
        }


def _extract_existing_field_names(rows: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for row in rows:
        for key in (
            "fieldName",
            "field_name",
            "tag",
            "title",
            "fieldLabel",
            "name",
        ):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                names.add(value.strip().lower())
    return names
