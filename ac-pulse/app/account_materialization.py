from datetime import UTC, datetime
from typing import Any

from app.account_mapping import build_account_map_preview


def build_account_materialization_plan(
    *,
    portfolio: dict[str, Any],
    activecampaign_accounts: list[dict[str, Any]],
    contacts_by_account_id: dict[int, list[dict[str, Any]]],
    limit: int,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    accounts = [
        account
        for account in portfolio.get("accounts", [])[:limit]
        if isinstance(account, dict)
    ]
    limited_portfolio = {**portfolio, "accounts": accounts}
    mapping = build_account_map_preview(
        portfolio=limited_portfolio,
        activecampaign_accounts=activecampaign_accounts,
    )

    matched_by_sf = {
        int(row["snowflake_account_id"]): row for row in mapping.get("matched", [])
    }
    ambiguous_by_sf = {
        int(row["snowflake_account_id"]): row for row in mapping.get("ambiguous", [])
    }

    rows: list[dict[str, Any]] = []
    for account in accounts:
        snowflake_account_id = int(account["account_id"])
        contacts = _contact_sample(contacts_by_account_id.get(snowflake_account_id, []))
        existing = matched_by_sf.get(snowflake_account_id)
        ambiguous = ambiguous_by_sf.get(snowflake_account_id)
        domain = _usable_domain(account.get("account_web_domain"))

        if ambiguous:
            action = "needs_review"
            reason = "Multiple ActiveCampaign account candidates matched this Snowflake account."
        elif existing and contacts:
            action = "associate_contacts_to_existing_account"
            reason = "An ActiveCampaign account exists and matching contacts were found."
        elif existing:
            action = "use_existing_account"
            reason = (
                "An ActiveCampaign account exists, but no matching contacts were "
                "found in this preview."
            )
        elif contacts:
            action = "create_account_and_associate_contacts"
            reason = (
                "No ActiveCampaign account matched, but contacts exist for this "
                "business domain."
            )
        elif domain:
            action = "needs_contact_discovery"
            reason = (
                "No ActiveCampaign account or matching contacts were found for "
                "this business domain."
            )
        else:
            action = "needs_domain"
            reason = "Snowflake did not provide a usable business domain for contact discovery."

        rows.append(
            {
                "snowflake_account_id": snowflake_account_id,
                "snowflake_account_name": account.get("account_name"),
                "account_web_domain": account.get("account_web_domain"),
                "proposed_account_name": account.get("account_name"),
                "arr": account.get("arr"),
                "action": action,
                "reason": reason,
                "existing_ac_account": _existing_account(existing),
                "ambiguous_candidates": (ambiguous or {}).get("candidates", []),
                "matching_contacts": contacts,
                "matching_contact_count": len(
                    contacts_by_account_id.get(snowflake_account_id, [])
                ),
            }
        )

    return {
        "mode": "dry_run",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": {
            "rep_name": portfolio.get("success_rep_name"),
            "snowflake_accounts_considered": len(accounts),
            "activecampaign_accounts": len(activecampaign_accounts),
            "diagnostics": diagnostics or {},
        },
        "summary": {
            "use_existing_account": _count(rows, "use_existing_account"),
            "associate_contacts_to_existing_account": _count(
                rows, "associate_contacts_to_existing_account"
            ),
            "create_account_and_associate_contacts": _count(
                rows, "create_account_and_associate_contacts"
            ),
            "needs_review": _count(rows, "needs_review"),
            "needs_contact_discovery": _count(rows, "needs_contact_discovery"),
            "needs_domain": _count(rows, "needs_domain"),
        },
        "accounts": rows,
    }


def _existing_account(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "ac_account_id": row.get("ac_account_id"),
        "ac_account_name": row.get("ac_account_name"),
        "ac_account_url": row.get("ac_account_url"),
        "match_keys": row.get("match_keys", []),
        "confidence": row.get("confidence"),
    }


def _contact_sample(contacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "contact_id": contact.get("id"),
            "email": contact.get("email"),
            "first_name": contact.get("firstName") or contact.get("first_name"),
            "last_name": contact.get("lastName") or contact.get("last_name"),
        }
        for contact in contacts[:25]
    ]


def _count(rows: list[dict[str, Any]], action: str) -> int:
    return sum(1 for row in rows if row.get("action") == action)


def _usable_domain(value: Any) -> str | None:
    text = str(value or "").strip().casefold()
    if not text or text.endswith(".activehosted.com"):
        return None
    return text
