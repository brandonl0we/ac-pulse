from typing import Any

import pytest

from app.ac_client.account_resolver import AccountResolver
from app.actions import build_action_plan, commit_action_plan


def test_build_action_plan_creates_priority_task() -> None:
    portfolio = _portfolio(
        [
            _account(
                account_id=42,
                action="Schedule churn-risk outreach",
                health_status="Critical",
            )
        ]
    )

    plan = build_action_plan(portfolio=portfolio)

    assert plan["mode"] == "dry_run"
    assert plan["summary"] == {"planned_actions": 1, "tasks": 1, "notes": 0, "skipped": 0}
    assert plan["actions"][0]["dedupe_key"] == "cs:task:42:schedule-churn-risk-outreach"
    assert plan["actions"][0]["priority"] == "high"
    assert plan["actions"][0]["due_in_days"] == 1
    assert plan["actions"][0]["activecampaign_account_id"] is None
    assert plan["actions"][0]["target_resolution"] == "pending"


def test_build_action_plan_creates_context_note_for_save_plan() -> None:
    portfolio = _portfolio(
        [
            _account(
                account_id=77,
                action="Confirm save plan for future cancellation",
                health_status="At Risk",
            )
        ]
    )

    plan = build_action_plan(portfolio=portfolio)

    assert plan["summary"]["planned_actions"] == 2
    assert [action["action_type"] for action in plan["actions"]] == ["task", "note"]
    assert plan["actions"][1]["dedupe_key"] == (
        "cs:note:77:confirm-save-plan-for-future-cancellation"
    )
    assert "Future cancel date" in plan["actions"][1]["body"]


def test_build_action_plan_skips_normal_cadence() -> None:
    portfolio = _portfolio(
        [
            _account(
                account_id=10,
                action="Maintain normal cadence",
                health_status="Healthy",
            )
        ]
    )

    plan = build_action_plan(portfolio=portfolio)

    assert plan["actions"] == []
    assert plan["summary"] == {"planned_actions": 0, "tasks": 0, "notes": 0, "skipped": 1}
    assert plan["skipped"][0]["reason"] == "normal_cadence"


def test_build_action_plan_filters_accounts_and_limits_actions() -> None:
    portfolio = _portfolio(
        [
            _account(account_id=1, action="Book customer health check"),
            _account(account_id=2, action="Follow up on NPS detractor feedback"),
        ]
    )

    plan = build_action_plan(portfolio=portfolio, account_ids=[2], limit=1)

    assert len(plan["actions"]) == 1
    assert plan["actions"][0]["snowflake_account_id"] == 2
    assert plan["actions"][0]["action_type"] == "task"


def test_build_action_plan_resolves_activecampaign_account_id(tmp_path: Any) -> None:
    csv_path = tmp_path / "account-map.csv"
    csv_path.write_text(
        "snowflake_account_id,ac_account_id\n42,9001\n",
        encoding="utf-8",
    )
    portfolio = _portfolio(
        [
            _account(
                account_id=42,
                action="Schedule churn-risk outreach",
                health_status="Critical",
            )
        ]
    )

    plan = build_action_plan(
        portfolio=portfolio,
        resolver=AccountResolver(csv_path),
    )

    assert plan["actions"][0]["activecampaign_account_id"] == 9001
    assert plan["actions"][0]["target_resolution"] == "resolved"


@pytest.mark.asyncio
async def test_commit_action_plan_requires_confirmation() -> None:
    api = FakeActiveCampaignAPI()
    plan = {
        "actions": [
            {
                "dedupe_key": "cs:task:42:schedule-churn-risk-outreach",
                "action_type": "task",
                "snowflake_account_id": 42,
                "activecampaign_account_id": 9001,
                "title": "Schedule churn-risk outreach",
                "priority": "high",
                "due_in_days": 1,
                "body": "Churn risk is Very High.",
            }
        ]
    }

    result = await commit_action_plan(
        plan=plan,
        activecampaign_api=api,
        dedupe_keys=["cs:task:42:schedule-churn-risk-outreach"],
        confirm=False,
    )

    assert result["status"] == "requires_confirmation"
    assert result["summary"]["committed"] == 0
    assert api.notes == []


@pytest.mark.asyncio
async def test_commit_action_plan_writes_selected_account_note() -> None:
    api = FakeActiveCampaignAPI()
    plan = {
        "actions": [
            {
                "dedupe_key": "cs:task:42:schedule-churn-risk-outreach",
                "action_type": "task",
                "snowflake_account_id": 42,
                "activecampaign_account_id": 9001,
                "title": "Schedule churn-risk outreach",
                "priority": "high",
                "due_in_days": 1,
                "body": "Churn risk is Very High.",
            }
        ]
    }

    result = await commit_action_plan(
        plan=plan,
        activecampaign_api=api,
        dedupe_keys=["cs:task:42:schedule-churn-risk-outreach"],
        confirm=True,
    )

    assert result["status"] == "committed"
    assert result["summary"]["committed"] == 1
    assert api.notes[0]["account_id"] == 9001
    assert "Dedupe-Key: cs:task:42:schedule-churn-risk-outreach" in api.notes[0]["note"]
    assert result["committed"][0]["write_target"] == "account_note"


@pytest.mark.asyncio
async def test_commit_action_plan_skips_unmapped_account() -> None:
    api = FakeActiveCampaignAPI()
    plan = {
        "actions": [
            {
                "dedupe_key": "cs:task:42:schedule-churn-risk-outreach",
                "action_type": "task",
                "snowflake_account_id": 42,
                "activecampaign_account_id": None,
                "title": "Schedule churn-risk outreach",
                "priority": "high",
                "due_in_days": 1,
                "body": "Churn risk is Very High.",
            }
        ]
    }

    result = await commit_action_plan(
        plan=plan,
        activecampaign_api=api,
        dedupe_keys=["cs:task:42:schedule-churn-risk-outreach"],
        confirm=True,
    )

    assert result["summary"]["committed"] == 0
    assert result["summary"]["skipped"] == 1
    assert result["skipped"][0]["reason"] == "missing_activecampaign_account_id"
    assert api.notes == []


def _portfolio(accounts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "success_rep_name": "Kevin Oostema",
        "summary": {"account_count": len(accounts)},
        "accounts": accounts,
    }


def _account(
    *,
    account_id: int,
    action: str,
    health_status: str = "At Risk",
) -> dict[str, Any]:
    return {
        "account_id": account_id,
        "account_name": f"account-{account_id}.activehosted.com",
        "success_rep_name": "Kevin Oostema",
        "arr": 12000,
        "risk": {"future_cancel_churn_date": "2026-07-01"},
        "nps": {"latest_score": 4},
        "touchpoints": {"days_since_last_touchpoint": 21},
        "command": {
            "next_best_action": action,
            "health_status": health_status,
            "priority_reason": "Churn risk is High.",
            "priority_score": 99,
            "owner_attention": True,
        },
    }


class FakeActiveCampaignAPI:
    def __init__(self) -> None:
        self.notes: list[dict[str, Any]] = []

    async def create_account_note(
        self,
        *,
        account_id: int,
        note: str,
    ) -> dict[str, Any]:
        self.notes.append({"account_id": account_id, "note": note})
        return {"note": {"id": f"note-{len(self.notes)}"}}
