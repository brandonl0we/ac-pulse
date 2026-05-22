from typing import Any

import structlog
from pydantic import ValidationError

from app.models import AccountSignals

logger = structlog.get_logger(__name__)


def transform_account_signals(payload: dict[str, Any]) -> AccountSignals | None:
    enriched_payload = dict(payload)
    priority_tier = _derive_priority_tier(enriched_payload)
    days_since_touchpoint = _as_int_or_none(enriched_payload.get("days_since_touchpoint"))
    days_to_renewal = _as_int_or_none(enriched_payload.get("days_to_renewal"))
    utilization_percent = _as_float_or_none(enriched_payload.get("utilization_percent"))
    renewal_motion = _derive_renewal_motion(days_to_renewal)
    intervention_due = _derive_intervention_due(
        priority_tier=priority_tier,
        days_since_touchpoint=days_since_touchpoint,
    )
    health_status = _derive_health_status(
        priority_tier=priority_tier,
        utilization_percent=utilization_percent,
        days_since_touchpoint=days_since_touchpoint,
    )

    enriched_payload["cs_priority_tier"] = priority_tier
    enriched_payload["cs_intervention_due"] = intervention_due
    enriched_payload["cs_health_status"] = health_status
    enriched_payload["cs_renewal_motion"] = renewal_motion
    enriched_payload["cs_owner_attention"] = _derive_owner_attention(
        health_status=health_status,
        intervention_due=intervention_due,
        renewal_motion=renewal_motion,
    )
    enriched_payload["cs_next_best_action"] = _derive_next_best_action(
        health_status=health_status,
        renewal_motion=renewal_motion,
        intervention_due=intervention_due,
        utilization_percent=utilization_percent,
        days_since_touchpoint=days_since_touchpoint,
    )
    enriched_payload["cs_priority_reason"] = _derive_priority_reason(
        priority_tier=priority_tier,
        health_status=health_status,
        renewal_motion=renewal_motion,
        days_since_touchpoint=days_since_touchpoint,
        utilization_percent=utilization_percent,
        churn_band=str(enriched_payload.get("churn_decile_band") or ""),
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


def _derive_health_status(
    *,
    priority_tier: str,
    utilization_percent: float | None,
    days_since_touchpoint: int | None,
) -> str:
    if priority_tier == "Critical":
        return "Critical"
    if priority_tier == "High":
        return "At Risk"
    if utilization_percent is not None and utilization_percent < 50:
        return "Watch"
    if days_since_touchpoint is not None and days_since_touchpoint > 45:
        return "Watch"
    return "Healthy"


def _derive_renewal_motion(days_to_renewal: int | None) -> str:
    if days_to_renewal is None:
        return "Renewal Not Set"
    if days_to_renewal < 0:
        return "Overdue"
    if days_to_renewal <= 90:
        return "Renewing Soon"
    return "Mid-Cycle"


def _derive_owner_attention(
    *,
    health_status: str,
    intervention_due: bool,
    renewal_motion: str,
) -> bool:
    if health_status in {"Critical", "At Risk"}:
        return True
    if intervention_due:
        return True
    return renewal_motion == "Overdue"


def _derive_next_best_action(
    *,
    health_status: str,
    renewal_motion: str,
    intervention_due: bool,
    utilization_percent: float | None,
    days_since_touchpoint: int | None,
) -> str:
    if intervention_due and health_status == "Critical":
        return "Schedule renewal risk outreach"
    if intervention_due:
        return "Book customer health check"
    if renewal_motion == "Overdue":
        return "Confirm renewal status"
    if renewal_motion == "Renewing Soon" and health_status in {"Critical", "At Risk"}:
        return "Prepare renewal save plan"
    if utilization_percent is not None and utilization_percent < 50:
        return "Review adoption plan"
    if days_since_touchpoint is not None and days_since_touchpoint > 45:
        return "Log customer touchpoint"
    return "Maintain normal cadence"


def _derive_priority_reason(
    *,
    priority_tier: str,
    health_status: str,
    renewal_motion: str,
    days_since_touchpoint: int | None,
    utilization_percent: float | None,
    churn_band: str,
) -> str:
    reasons: list[str] = []
    if churn_band:
        reasons.append(f"Churn band is {churn_band}.")
    if renewal_motion in {"Overdue", "Renewing Soon"}:
        reasons.append(f"Renewal motion is {renewal_motion}.")
    if days_since_touchpoint is not None and days_since_touchpoint > 30:
        reasons.append(f"No CSM touchpoint in {days_since_touchpoint} days.")
    if utilization_percent is not None and utilization_percent < 50:
        reasons.append(f"Utilization is {utilization_percent:g}%.")

    if reasons:
        return " ".join(reasons)
    if health_status == "Healthy" and priority_tier == "Standard":
        return "No elevated customer success risk detected."
    return f"Health is {health_status} with {priority_tier} CS priority."


def _as_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
