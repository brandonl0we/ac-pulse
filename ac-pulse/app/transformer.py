from typing import Any

import structlog
from pydantic import ValidationError

from app.models import AccountSignals

logger = structlog.get_logger(__name__)


def transform_account_signals(payload: dict[str, Any]) -> AccountSignals | None:
    enriched_payload = dict(payload)
    priority_tier = _derive_priority_tier(enriched_payload)
    enriched_payload["cs_priority_tier"] = priority_tier
    enriched_payload["cs_intervention_due"] = _derive_intervention_due(
        priority_tier=priority_tier,
        days_since_touchpoint=_as_int_or_none(enriched_payload.get("days_since_touchpoint")),
    )

    try:
        return AccountSignals.model_validate(enriched_payload)
    except ValidationError as exc:
        logger.warning(
            "account_signal_validation_failed",
            account_id=enriched_payload.get("account_id"),
            errors=exc.errors(),
        )
        return None


def _derive_priority_tier(payload: dict[str, Any]) -> str:
    churn_band = str(payload.get("churn_decile_band") or "")
    days_to_renewal = _as_int_or_none(payload.get("days_to_renewal"))
    if churn_band == "Very High" and days_to_renewal is not None and days_to_renewal <= 90:
        return "Critical"
    if churn_band in {"Very High", "High"}:
        return "High"
    return "Standard"


def _derive_intervention_due(
    *,
    priority_tier: str,
    days_since_touchpoint: int | None,
) -> bool:
    if priority_tier not in {"Critical", "High"}:
        return False
    if days_since_touchpoint is None:
        return False
    return days_since_touchpoint > 30


def _as_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
