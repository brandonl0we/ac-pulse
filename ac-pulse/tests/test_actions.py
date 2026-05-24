from typing import Any

from app.actions import build_action_plan


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
