from datetime import UTC, datetime, timedelta
from typing import Any

from app.ac_client.account_resolver import AccountResolver
from app.ac_client.api import ActiveCampaignAPI

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
    resolver: AccountResolver | None = None,
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

        planned_actions.append(_planned_task(account, rule, resolver))
        if rule.get("include_note"):
            planned_actions.append(_planned_note(account, action_label, resolver))

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


async def commit_action_plan(
    *,
    plan: dict[str, Any],
    activecampaign_api: ActiveCampaignAPI,
    dedupe_keys: list[str],
    confirm: bool,
) -> dict[str, Any]:
    selected_keys = set(dedupe_keys)
    actions = [
        action for action in plan.get("actions", []) if action.get("dedupe_key") in selected_keys
    ]
    missing_keys = sorted(selected_keys - {str(action.get("dedupe_key")) for action in actions})

    if not confirm:
        return _commit_response(
            status="requires_confirmation",
            actions=actions,
            committed=[],
            skipped=[],
            missing_keys=missing_keys,
        )

    committed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for action in actions:
        ac_account_id = action.get("activecampaign_account_id")
        if not ac_account_id:
            skipped.append(_commit_skip(action, "missing_activecampaign_account_id"))
            continue

        if action.get("action_type") == "task":
            response = await activecampaign_api.create_task(
                title=str(action["title"]),
                note=_commit_task_body(action),
                due_at=_task_due_at(action),
            )
            write_target = "activecampaign_task"
        else:
            response = await activecampaign_api.create_account_note(
                account_id=int(ac_account_id),
                note=_commit_note_body(action),
            )
            write_target = "account_note"

        committed.append(
            {
                "dedupe_key": action["dedupe_key"],
                "action_type": action["action_type"],
                "snowflake_account_id": action["snowflake_account_id"],
                "activecampaign_account_id": int(ac_account_id),
                "write_target": write_target,
                "activecampaign_response": response,
            }
        )

    return _commit_response(
        status="committed",
        actions=actions,
        committed=committed,
        skipped=skipped,
        missing_keys=missing_keys,
    )


def _planned_task(
    account: dict[str, Any],
    rule: dict[str, Any],
    resolver: AccountResolver | None,
) -> dict[str, Any]:
    action_label = str(account["command"]["next_best_action"])
    body = _action_body(account)
    return _base_action(
        account,
        action_type="task",
        action_label=action_label,
        resolver=resolver,
    ) | {
        "priority": rule["priority"],
        "title": rule["title"],
        "body": body,
        "due_in_days": rule["due_in_days"],
    }


def _planned_note(
    account: dict[str, Any],
    action_label: str,
    resolver: AccountResolver | None,
) -> dict[str, Any]:
    title = f"CS context: {action_label}"
    return _base_action(
        account,
        action_type="note",
        action_label=action_label,
        resolver=resolver,
    ) | {
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
    resolver: AccountResolver | None,
) -> dict[str, Any]:
    snowflake_account_id = int(account["account_id"])
    activecampaign_account_id, target_resolution = _resolve_account_id(
        resolver=resolver,
        snowflake_account_id=snowflake_account_id,
    )
    slug = _slug(action_label)
    return {
        "dedupe_key": f"cs:{action_type}:{snowflake_account_id}:{slug}",
        "action_type": action_type,
        "status": "planned",
        "snowflake_account_id": snowflake_account_id,
        "activecampaign_account_id": activecampaign_account_id,
        "target_resolution": target_resolution,
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


def _resolve_account_id(
    *,
    resolver: AccountResolver | None,
    snowflake_account_id: int,
) -> tuple[int | None, str]:
    if resolver is None:
        return None, "pending"
    try:
        return resolver.resolve(snowflake_account_id), "resolved"
    except KeyError:
        return None, "missing_mapping"


def _commit_response(
    *,
    status: str,
    actions: list[dict[str, Any]],
    committed: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    missing_keys: list[str],
) -> dict[str, Any]:
    return {
        "mode": "activecampaign_objects",
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "requested": len(actions) + len(missing_keys),
            "selected": len(actions),
            "committed": len(committed),
            "skipped": len(skipped),
            "missing_dedupe_keys": len(missing_keys),
        },
        "committed": committed,
        "skipped": skipped,
        "missing_dedupe_keys": missing_keys,
    }


def _commit_skip(action: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "dedupe_key": action.get("dedupe_key"),
        "action_type": action.get("action_type"),
        "snowflake_account_id": action.get("snowflake_account_id"),
        "activecampaign_account_id": action.get("activecampaign_account_id"),
        "reason": reason,
    }


def _commit_task_body(action: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"[ac-pulse] {action['title']}",
            f"Dedupe-Key: {action['dedupe_key']}",
            f"ActiveCampaign Account ID: {action['activecampaign_account_id']}",
            f"Snowflake Account ID: {action['snowflake_account_id']}",
            f"Priority: {action.get('priority', 'normal')}",
            "",
            str(action.get("body") or ""),
        ]
    )


def _commit_note_body(action: dict[str, Any]) -> str:
    due = action.get("due_in_days")
    due_line = "Due: none" if due is None else f"Due: in {due} days"
    return "\n".join(
        [
            f"[ac-pulse] {action['title']}",
            f"Dedupe-Key: {action['dedupe_key']}",
            f"Type: {action['action_type']}",
            f"Priority: {action.get('priority', 'normal')}",
            due_line,
            "",
            str(action.get("body") or ""),
        ]
    )


def _task_due_at(action: dict[str, Any]) -> str | None:
    due_in_days = action.get("due_in_days")
    if due_in_days is None:
        return None
    due_at = datetime.now(UTC).replace(microsecond=0) + timedelta(days=int(due_in_days))
    return due_at.isoformat()


def _slug(value: str) -> str:
    return "-".join(value.lower().split())
