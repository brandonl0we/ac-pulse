import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from app.ac_client.account_resolver import AccountResolver
from app.audit import get_last_success_for_account
from app.models import AccountSignals
from app.transformer import transform_account_signals
from app.workers.pipeline import SupportsExtract, _merge_extractor_payloads

COMMAND_FIELDS = (
    "cs_health_status",
    "cs_next_best_action",
    "cs_priority_reason",
    "cs_renewal_motion",
    "cs_owner_attention",
    "cs_priority_tier",
    "cs_intervention_due",
)


class SupportsResolve(Protocol):
    def resolve(self, snowflake_account_id: int) -> int: ...


async def build_account_pulse(
    *,
    snowflake_account_id: int,
    extractor_instances: Iterable[SupportsExtract],
    resolver: SupportsResolve | None,
) -> dict[str, Any] | None:
    """Build a read-only CS pulse from current source signals.

    This intentionally does not write to ActiveCampaign. It reuses the same
    extractor and transformer path as the sync workers so UI/agent surfaces
    and AC custom fields speak from the same account-state logic.
    """
    extractor_payloads = await asyncio.gather(
        *[extractor.extract() for extractor in extractor_instances]
    )
    merged = _merge_extractor_payloads(extractor_payloads)
    payload = merged.get(snowflake_account_id)
    if payload is None:
        return None

    signals = transform_account_signals(payload)
    if signals is None:
        return None

    activecampaign_account_id = _resolve_activecampaign_account_id(
        resolver=resolver,
        snowflake_account_id=snowflake_account_id,
    )
    last_synced_at = (
        await get_last_success_for_account(activecampaign_account_id)
        if activecampaign_account_id is not None
        else None
    )

    return shape_account_pulse(
        signals=signals,
        activecampaign_account_id=activecampaign_account_id,
        last_synced_at=last_synced_at,
    )


def shape_account_pulse(
    *,
    signals: AccountSignals,
    activecampaign_account_id: int | None,
    last_synced_at: str | None,
) -> dict[str, Any]:
    signal_payload = signals.model_dump(mode="json")
    return {
        "snowflake_account_id": signals.account_id,
        "activecampaign_account_id": activecampaign_account_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "last_synced_at": last_synced_at,
        "command": {
            "health_status": signals.cs_health_status,
            "next_best_action": signals.cs_next_best_action,
            "priority_reason": signals.cs_priority_reason,
            "renewal_motion": signals.cs_renewal_motion,
            "owner_attention": signals.cs_owner_attention,
            "priority_tier": signals.cs_priority_tier,
            "intervention_due": signals.cs_intervention_due,
        },
        "metrics": {
            key: value
            for key, value in signal_payload.items()
            if key not in COMMAND_FIELDS and key != "account_id"
        },
    }


def _resolve_activecampaign_account_id(
    *,
    resolver: SupportsResolve | None,
    snowflake_account_id: int,
) -> int | None:
    if resolver is None:
        return None
    try:
        return resolver.resolve(snowflake_account_id)
    except KeyError:
        return None


def build_account_resolver(csv_path: Path) -> AccountResolver:
    return AccountResolver(csv_path)
