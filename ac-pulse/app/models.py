from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

HealthStatus = Literal["Healthy", "Watch", "At Risk", "Critical"]
PriorityTier = Literal["Critical", "High", "Standard"]
RenewalMotion = Literal["Renewal Not Set", "Overdue", "Renewing Soon", "Mid-Cycle"]


class AccountSignals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: int
    churn_decile_band: str | None = None
    churn_score: float | None = None
    acai_score: float | None = None
    nbn_score: float | None = None
    utilization_percent: float | None = None
    days_since_touchpoint: int | None = None
    touchpoint_count_30d: int | None = None
    days_to_renewal: int | None = None
    renewal_date: date | None = None

    cs_priority_tier: PriorityTier = "Standard"
    cs_intervention_due: bool = False
    cs_health_status: HealthStatus = "Healthy"
    cs_next_best_action: str = "Maintain normal cadence"
    cs_priority_reason: str = "No elevated customer success risk detected."
    cs_renewal_motion: RenewalMotion = "Renewal Not Set"
    cs_owner_attention: bool = False
    updated_at: datetime | None = None
