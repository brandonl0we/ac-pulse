from datetime import UTC, datetime
from typing import Any

_NOOP_ACTIONS = {"Maintain normal cadence"}

_ACTION_RULES = {
    "Schedule churn-risk outreach": {
        "action_type": "task",
        "priority": "high",
        "due_in_days": 1,
        "title": "Schedule churn-risk outreach",
    },
    "Book customer health check": {
        "action_type": "task",
        "priority": "high",
        "due_in_days": 3,
        "title": "Book customer health check",
    },
    "Follow up on NPS detractor feedback": {
        "action_type": "task",
        "priority": "high",
        "due_in_days": 2,
        "title": "Follow up on NPS detractor feedback",
        "include_note": True,
    },
    "Review adoption plan": {
        "action_type": "task",
        "priority": "normal",
        "due_in_days": 7,
        "title": "Review adoption plan",
    },
    "Confirm save plan for future cancellation": {
        "action_type": "task",
        "priority": "high",
        "due_in_days": 1,
        "title": "Confirm save plan for future cancellation",
        "include_note": True,
    },
    "Log customer touchpoint": {
        "action_type": "task",
        "priority": "normal",
        "due_in_days": 7,
        "title": "Log customer touchpoint",
    },
    "Establish success cadence": {
        "action_type": "task",
        "priority": "normal",
        "due_in_days": 7,
        "title": "Establish success cadence",
    },
}


def build_action_plan(
    *,
    portfolio: dict[str, Any],
    account_ids: list[int] | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    selected_ids = set(account_ids or [])
    planned_actions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for account in portfolio.get("accounts", []):
        snowflake_account_id = int(account["account_id"])
        if selected_ids and snowflake_account_id not in selected_ids:
            continue

        action_label = str(account["command"]["next_best_action"])
        if action_label in _NOOP_ACTIONS:
            skipped.append(_skip(account, "normal_cadence"))
            continue

        rule = _ACTION_RULES.get(action_label)
        if rule is None:
            skipped.append(_skip(account, "unsupported_action"))
            continue

        planned_actions.append(_planned_task(account, rule))
        if rule.get("include_note"):
            planned_actions.append(_planned_note(account, action_label))

        if len(planned_actions) >= limit:
            planned_actions = planned_actions[:limit]
            break

    return {
        "mode": "dry_run",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": {
            "rep_name": portfolio.get("success_rep_name"),
            "account_count": portfolio.get("summary", {}).get("account_count", 0),
        },
        "summary": {
            "planned_actions": len(planned_actions),
            "tasks": _count_actions(planned_actions, "task"),
            "notes": _count_actions(planned_actions, "note"),
            "skipped": len(skipped),
        },
        "actions": planned_actions,
        "skipped": skipped,
    }


def _planned_task(account: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    action_label = str(account["command"]["next_best_action"])
    body = _action_body(account)
    return _base_action(account, action_type="task", action_label=action_label) | {
        "priority": rule["priority"],
        "title": rule["title"],
        "body": body,
        "due_in_days": rule["due_in_days"],
    }


def _planned_note(account: dict[str, Any], action_label: str) -> dict[str, Any]:
    title = f"CS context: {action_label}"
    return _base_action(account, action_type="note", action_label=action_label) | {
        "priority": "normal",
        "title": title,
        "body": _action_body(account),
        "due_in_days": None,
    }


def _base_action(
    account: dict[str, Any],
    *,
    action_type: str,
    action_label: str,
) -> dict[str, Any]:
    snowflake_account_id = int(account["account_id"])
    slug = _slug(action_label)
    return {
        "dedupe_key": f"cs:{action_type}:{snowflake_account_id}:{slug}",
        "action_type": action_type,
        "status": "planned",
        "snowflake_account_id": snowflake_account_id,
        "activecampaign_account_id": None,
        "target_resolution": "pending",
        "account_name": account.get("account_name"),
        "owner": {"success_rep_name": account.get("success_rep_name")},
        "source_command": account.get("command", {}),
    }


def _action_body(account: dict[str, Any]) -> str:
    command = account["command"]
    risk = account.get("risk", {})
    nps = account.get("nps", {})
    touchpoints = account.get("touchpoints", {})
    parts = [
        command.get("priority_reason") or "Review current customer success context.",
        f"Health: {command.get('health_status', 'Unknown')}.",
        f"ARR: ${float(account.get('arr') or 0):,.0f}.",
    ]
    if risk.get("future_cancel_churn_date"):
        parts.append(f"Future cancel date: {risk['future_cancel_churn_date']}.")
    if nps.get("latest_score") is not None:
        parts.append(f"Latest NPS: {nps['latest_score']}.")
    if touchpoints.get("days_since_last_touchpoint") is not None:
        days = touchpoints["days_since_last_touchpoint"]
        parts.append(f"Days since last Totango touchpoint: {days}.")
    return " ".join(parts)


def _skip(account: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "snowflake_account_id": int(account["account_id"]),
        "account_name": account.get("account_name"),
        "reason": reason,
        "source_command": account.get("command", {}),
    }


def _count_actions(actions: list[dict[str, Any]], action_type: str) -> int:
    return sum(1 for action in actions if action["action_type"] == action_type)


def _slug(value: str) -> str:
    return "-".join(value.lower().split())
