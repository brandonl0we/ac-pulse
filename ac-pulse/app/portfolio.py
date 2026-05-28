from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.snowflake_client import SnowflakeClient

_SQL_PATH = Path(__file__).resolve().parent.parent / "sql" / "portfolio" / "success_rep_book.sql"
_HIGH_RISK = {"High", "Very High"}
_RISK_RANK = {
    "Very High": 5,
    "High": 4,
    "Moderate": 3,
    "Low": 2,
    "Minimal": 1,
    "Minimal short-term": 1,
}


async def build_success_rep_portfolio(
    *,
    snowflake_client: SnowflakeClient,
    rep_name: str,
) -> dict[str, Any]:
    rows = await snowflake_client.execute(_load_sql(), {"rep_name": rep_name})
    accounts = [_shape_account(row) for row in rows]
    accounts.sort(key=lambda account: account["command"]["priority_score"], reverse=True)

    return {
        "success_rep_name": rep_name,
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": _summarize(accounts),
        "accounts": accounts,
    }


def _load_sql() -> str:
    return _SQL_PATH.read_text(encoding="utf-8")


def _shape_account(row: dict[str, Any]) -> dict[str, Any]:
    arr = _as_float(row.get("ARR"))
    churn_risk = _as_str(row.get("CURRENT_CHURN_RISK_3MO"))
    overall_risk = _as_str(row.get("CURRENT_OVERALL_PREDICTION_TYPE_RISK"))
    product_score = _as_float_or_none(row.get("PRODUCT_SCORE"))
    nps_score = _as_int_or_none(row.get("LATEST_NPS_SCORE"))
    days_since_last_tp = _as_int_or_none(row.get("DAYS_SINCE_LAST_TP"))
    total_touchpoints_90d = _as_int(row.get("TOTAL_TOUCHPOINTS_90D"))
    total_touchpoints_30d = _as_int(row.get("TOTAL_TOUCHPOINTS_30D"))

    command = _derive_command(
        arr=arr,
        churn_risk=churn_risk,
        overall_risk=overall_risk,
        product_score=product_score,
        nps_score=nps_score,
        days_since_last_tp=days_since_last_tp,
        total_touchpoints_90d=total_touchpoints_90d,
        future_cancel_churn_date=row.get("FUTURE_CANCEL_CHURN_DATE"),
    )

    return {
        "account_id": _as_int(row.get("ACCOUNT_ID")),
        "account_name": row.get("ACCOUNT_NAME"),
        "success_rep_name": row.get("SUCCESS_REP_NAME"),
        "success_ownership_bucket": row.get("SUCCESS_OWNERSHIP_BUCKET"),
        "plan_tier_name": row.get("PLAN_TIER_NAME"),
        "product_line_actual": row.get("PRODUCT_LINE_ACTUAL"),
        "account_web_domain": _as_str_or_none(row.get("ACCOUNT_WEB_DOMAIN")),
        "region": row.get("REGION"),
        "mrr": _as_float(row.get("MRR")),
        "arr": arr,
        "account_convert_date": _as_str_or_none(row.get("ACCOUNT_CONVERT_DATE")),
        "contract_end_date": _as_str_or_none(row.get("CONTRACT_END_DATE")),
        "contract_length_current": _as_str_or_none(row.get("CONTRACT_LENGTH_CURRENT")),
        "risk": {
            "churn_3mo": churn_risk or None,
            "contraction_3mo": _as_str_or_none(row.get("CURRENT_CONTRACTION_RISK_3MO")),
            "overall_prediction": overall_risk or None,
            "future_cancel_churn_date": _as_str_or_none(row.get("FUTURE_CANCEL_CHURN_DATE")),
        },
        "product": {
            "score": product_score,
            "max_score": _as_float_or_none(row.get("MAX_PRODUCT_SCORE")),
            "active_automations_score": _as_float_or_none(
                row.get("ACTIVE_AUTOMATIONS_PRODUCT_SCORE")
            ),
            "batch_campaigns_score": _as_float_or_none(row.get("BATCH_CAMPAIGNS_PRODUCT_SCORE")),
            "active_integrations_score": _as_float_or_none(
                row.get("ACTIVE_INTEGRATIONS_PRODUCT_SCORE")
            ),
            "unique_non_ac_user_logins_score": _as_float_or_none(
                row.get("UNIQUE_NON_AC_USER_LOGINS_PRODUCT_SCORE")
            ),
            "generative_ai_score": _as_float_or_none(row.get("GENERATIVE_AI_PRODUCT_SCORE")),
            "crm_deals_score": _as_float_or_none(row.get("CRM_DEALS_PRODUCT_SCORE")),
            "sms_add_on_score": _as_float_or_none(row.get("SMS_ADD_ON_PRODUCT_SCORE")),
        },
        "nps": {
            "latest_score": nps_score,
            "latest_submission_date": _as_str_or_none(row.get("LATEST_NPS_SUBMISSION_DATE")),
        },
        "touchpoints": {
            "total_90d": total_touchpoints_90d,
            "email_90d": _as_int(row.get("EMAIL_TOUCHPOINTS_90D")),
            "web_meetings_90d": _as_int(row.get("WEB_MEETINGS_90D")),
            "internal_notes_90d": _as_int(row.get("INTERNAL_NOTES_90D")),
            "phone_calls_90d": _as_int(row.get("PHONE_CALLS_90D")),
            "linkedin_90d": _as_int(row.get("LINKEDIN_90D")),
            "sms_90d": _as_int(row.get("SMS_TOUCHPOINTS_90D")),
            "last_touchpoint_date": _as_str_or_none(row.get("LAST_TP_DATE")),
            "days_since_last_touchpoint": days_since_last_tp,
            "total_30d": total_touchpoints_30d,
            "email_30d": _as_int(row.get("EMAIL_TOUCHPOINTS_30D")),
            "web_meetings_30d": _as_int(row.get("WEB_MEETINGS_30D")),
            "last_success_interaction_date": _as_str_or_none(
                row.get("LAST_SUCCESS_INTERACTION_DATE")
            ),
            "last_success_interaction_content": _as_str_or_none(
                row.get("LAST_SUCCESS_INTERACTION_CONTENT")
            ),
        },
        "command": command,
    }


def _derive_command(
    *,
    arr: float,
    churn_risk: str,
    overall_risk: str,
    product_score: float | None,
    nps_score: int | None,
    days_since_last_tp: int | None,
    total_touchpoints_90d: int,
    future_cancel_churn_date: Any,
) -> dict[str, Any]:
    priority_score = _priority_score(
        arr=arr,
        churn_risk=churn_risk,
        product_score=product_score,
        nps_score=nps_score,
        days_since_last_tp=days_since_last_tp,
        future_cancel_churn_date=future_cancel_churn_date,
    )
    health_status = _health_status(
        churn_risk=churn_risk,
        overall_risk=overall_risk,
        product_score=product_score,
        nps_score=nps_score,
    )
    owner_attention = (
        health_status in {"Critical", "At Risk"}
        or (days_since_last_tp is not None and days_since_last_tp >= 14)
        or bool(future_cancel_churn_date)
    )

    return {
        "priority_score": round(priority_score, 1),
        "health_status": health_status,
        "owner_attention": owner_attention,
        "next_best_action": _next_best_action(
            health_status=health_status,
            product_score=product_score,
            nps_score=nps_score,
            days_since_last_tp=days_since_last_tp,
            total_touchpoints_90d=total_touchpoints_90d,
            future_cancel_churn_date=future_cancel_churn_date,
        ),
        "priority_reason": _priority_reason(
            churn_risk=churn_risk,
            overall_risk=overall_risk,
            product_score=product_score,
            nps_score=nps_score,
            days_since_last_tp=days_since_last_tp,
            future_cancel_churn_date=future_cancel_churn_date,
        ),
    }


def _summarize(accounts: list[dict[str, Any]]) -> dict[str, Any]:
    total_arr = sum(float(account["arr"] or 0) for account in accounts)
    high_risk_accounts = [
        account for account in accounts if account["risk"]["churn_3mo"] in _HIGH_RISK
    ]
    stale_accounts = [
        account
        for account in accounts
        if (account["touchpoints"]["days_since_last_touchpoint"] or 0) >= 14
    ]
    detractor_accounts = [
        account
        for account in accounts
        if account["nps"]["latest_score"] is not None and account["nps"]["latest_score"] <= 6
    ]
    owner_attention_accounts = [
        account for account in accounts if account["command"]["owner_attention"]
    ]

    return {
        "account_count": len(accounts),
        "total_arr": round(total_arr, 2),
        "average_arr": round(total_arr / len(accounts), 2) if accounts else 0,
        "owner_attention_count": len(owner_attention_accounts),
        "owner_attention_arr": _sum_arr(owner_attention_accounts),
        "high_or_very_high_churn_count": len(high_risk_accounts),
        "high_or_very_high_churn_arr": _sum_arr(high_risk_accounts),
        "stale_touchpoint_14d_count": len(stale_accounts),
        "stale_touchpoint_14d_arr": _sum_arr(stale_accounts),
        "nps_detractor_count": len(detractor_accounts),
        "nps_detractor_arr": _sum_arr(detractor_accounts),
        "risk_mix": _count_by(accounts, "risk", "churn_3mo"),
        "plan_mix": _count_by(accounts, "plan_tier_name"),
    }


def _priority_score(
    *,
    arr: float,
    churn_risk: str,
    product_score: float | None,
    nps_score: int | None,
    days_since_last_tp: int | None,
    future_cancel_churn_date: Any,
) -> float:
    score = arr / 1000
    score += _RISK_RANK.get(churn_risk, 0) * 10
    if product_score is not None:
        score += max(0, 50 - product_score) / 5
    if nps_score is not None and nps_score <= 6:
        score += 8
    if days_since_last_tp is not None:
        score += days_since_last_tp / 7
    if future_cancel_churn_date:
        score += 25
    return score


def _health_status(
    *,
    churn_risk: str,
    overall_risk: str,
    product_score: float | None,
    nps_score: int | None,
) -> str:
    if churn_risk == "Very High":
        return "Critical"
    if churn_risk == "High" or overall_risk == "High":
        return "At Risk"
    if (product_score is not None and product_score < 35) or (
        nps_score is not None and nps_score <= 6
    ):
        return "Watch"
    return "Healthy"


def _next_best_action(
    *,
    health_status: str,
    product_score: float | None,
    nps_score: int | None,
    days_since_last_tp: int | None,
    total_touchpoints_90d: int,
    future_cancel_churn_date: Any,
) -> str:
    if future_cancel_churn_date:
        return "Confirm save plan for future cancellation"
    if health_status == "Critical":
        return "Schedule churn-risk outreach"
    if health_status == "At Risk":
        return "Book customer health check"
    if nps_score is not None and nps_score <= 6:
        return "Follow up on NPS detractor feedback"
    if product_score is not None and product_score < 35:
        return "Review adoption plan"
    if days_since_last_tp is not None and days_since_last_tp >= 14:
        return "Log customer touchpoint"
    if total_touchpoints_90d == 0:
        return "Establish success cadence"
    return "Maintain normal cadence"


def _priority_reason(
    *,
    churn_risk: str,
    overall_risk: str,
    product_score: float | None,
    nps_score: int | None,
    days_since_last_tp: int | None,
    future_cancel_churn_date: Any,
) -> str:
    reasons: list[str] = []
    if churn_risk:
        reasons.append(f"Churn risk is {churn_risk}.")
    if overall_risk and overall_risk != churn_risk:
        reasons.append(f"Overall prediction risk is {overall_risk}.")
    if product_score is not None and product_score < 50:
        reasons.append(f"PAS is {product_score:g}.")
    if nps_score is not None and nps_score <= 6:
        reasons.append(f"NPS is {nps_score}.")
    if days_since_last_tp is not None and days_since_last_tp >= 14:
        reasons.append(f"No Totango touchpoint in {days_since_last_tp} days.")
    if future_cancel_churn_date:
        reasons.append(f"Future cancel date is {future_cancel_churn_date}.")
    return " ".join(reasons) if reasons else "No elevated customer success risk detected."


def _sum_arr(accounts: list[dict[str, Any]]) -> float:
    return round(sum(float(account["arr"] or 0) for account in accounts), 2)


def _count_by(
    accounts: list[dict[str, Any]],
    key: str,
    nested_key: str | None = None,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for account in accounts:
        raw = account[key][nested_key] if nested_key else account[key]
        value = str(raw or "Unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_str_or_none(value: Any) -> str | None:
    text = _as_str(value)
    return text or None


def _as_int(value: Any) -> int:
    parsed = _as_int_or_none(value)
    return parsed if parsed is not None else 0


def _as_int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float:
    parsed = _as_float_or_none(value)
    return parsed if parsed is not None else 0.0


def _as_float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
