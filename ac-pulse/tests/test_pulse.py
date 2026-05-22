from typing import Any

import pytest

from app.pulse import build_account_pulse


class FakeExtractor:
    def __init__(self, payload: dict[int, dict[str, Any]]):
        self._payload = payload

    async def extract(self) -> dict[int, dict[str, Any]]:
        return self._payload


class FakeResolver:
    def resolve(self, snowflake_account_id: int) -> int:
        assert snowflake_account_id == 42
        return 202


@pytest.mark.asyncio
async def test_build_account_pulse_shapes_command_and_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_last_success_for_account(account_id: int) -> str:
        assert account_id == 202
        return "2026-05-22T12:00:00"

    monkeypatch.setattr(
        "app.pulse.get_last_success_for_account",
        fake_get_last_success_for_account,
    )

    pulse = await build_account_pulse(
        snowflake_account_id=42,
        extractor_instances=[
            FakeExtractor(
                {
                    42: {
                        "account_id": 42,
                        "churn_decile_band": "Very High",
                        "churn_score": 0.91,
                    }
                }
            ),
            FakeExtractor(
                {
                    42: {
                        "days_to_renewal": 30,
                        "days_since_touchpoint": 40,
                        "utilization_percent": 66,
                    }
                }
            ),
        ],
        resolver=FakeResolver(),
    )

    assert pulse is not None
    assert pulse["snowflake_account_id"] == 42
    assert pulse["activecampaign_account_id"] == 202
    assert pulse["last_synced_at"] == "2026-05-22T12:00:00"
    assert pulse["command"] == {
        "health_status": "Critical",
        "next_best_action": "Schedule renewal risk outreach",
        "priority_reason": (
            "Churn band is Very High. Renewal motion is Renewing Soon. "
            "No CSM touchpoint in 40 days."
        ),
        "renewal_motion": "Renewing Soon",
        "owner_attention": True,
        "priority_tier": "Critical",
        "intervention_due": True,
    }
    assert pulse["metrics"]["churn_score"] == 0.91
    assert pulse["metrics"]["utilization_percent"] == 66.0
    assert "cs_health_status" not in pulse["metrics"]


@pytest.mark.asyncio
async def test_build_account_pulse_returns_none_when_no_signals() -> None:
    pulse = await build_account_pulse(
        snowflake_account_id=42,
        extractor_instances=[FakeExtractor({7: {"account_id": 7}})],
        resolver=None,
    )

    assert pulse is None


@pytest.mark.asyncio
async def test_build_account_pulse_tolerates_missing_audit_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_last_success_for_account(account_id: int) -> str:
        assert account_id == 202
        raise RuntimeError("audit schema unavailable")

    monkeypatch.setattr(
        "app.pulse.get_last_success_for_account",
        fake_get_last_success_for_account,
    )

    pulse = await build_account_pulse(
        snowflake_account_id=42,
        extractor_instances=[
            FakeExtractor(
                {
                    42: {
                        "account_id": 42,
                        "churn_decile_band": "Low",
                    }
                }
            )
        ],
        resolver=FakeResolver(),
    )

    assert pulse is not None
    assert pulse["activecampaign_account_id"] == 202
    assert pulse["last_synced_at"] is None
