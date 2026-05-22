from app.transformer import transform_account_signals


def test_transformer_sets_critical_and_intervention_due() -> None:
    result = transform_account_signals(
        {
            "account_id": 1,
            "churn_decile_band": "Very High",
            "days_to_renewal": 45,
            "days_since_touchpoint": 35,
            "utilization_percent": 72,
        }
    )
    assert result is not None
    assert result.cs_priority_tier == "Critical"
    assert result.cs_intervention_due is True
    assert result.cs_health_status == "Critical"
    assert result.cs_renewal_motion == "Renewing Soon"
    assert result.cs_owner_attention is True
    assert result.cs_next_best_action == "Schedule renewal risk outreach"
    assert result.cs_priority_reason == (
        "Churn band is Very High. Renewal motion is Renewing Soon. "
        "No CSM touchpoint in 35 days."
    )


def test_transformer_sets_high_priority() -> None:
    result = transform_account_signals(
        {
            "account_id": 2,
            "churn_decile_band": "High",
            "days_to_renewal": 120,
            "days_since_touchpoint": 31,
        }
    )
    assert result is not None
    assert result.cs_priority_tier == "High"
    assert result.cs_intervention_due is True
    assert result.cs_health_status == "At Risk"
    assert result.cs_next_best_action == "Book customer health check"


def test_transformer_sets_standard_priority() -> None:
    result = transform_account_signals(
        {
            "account_id": 3,
            "churn_decile_band": "Medium",
            "days_to_renewal": 10,
            "days_since_touchpoint": 100,
        }
    )
    assert result is not None
    assert result.cs_priority_tier == "Standard"
    assert result.cs_intervention_due is False
    assert result.cs_health_status == "Watch"
    assert result.cs_owner_attention is False
    assert result.cs_next_best_action == "Log customer touchpoint"


def test_transformer_returns_none_for_invalid_payload() -> None:
    assert transform_account_signals({"churn_decile_band": "Very High"}) is None


def test_transformer_sets_watch_for_low_utilization() -> None:
    result = transform_account_signals(
        {
            "account_id": 4,
            "churn_decile_band": "Medium",
            "days_to_renewal": 150,
            "days_since_touchpoint": 15,
            "utilization_percent": 42.5,
        }
    )

    assert result is not None
    assert result.cs_priority_tier == "Standard"
    assert result.cs_health_status == "Watch"
    assert result.cs_renewal_motion == "Mid-Cycle"
    assert result.cs_next_best_action == "Review adoption plan"
    assert result.cs_priority_reason == "Churn band is Medium. Utilization is 42.5%."


def test_transformer_sets_overdue_renewal_motion() -> None:
    result = transform_account_signals(
        {
            "account_id": 5,
            "churn_decile_band": "Low",
            "days_to_renewal": -3,
            "days_since_touchpoint": 12,
        }
    )

    assert result is not None
    assert result.cs_health_status == "Healthy"
    assert result.cs_renewal_motion == "Overdue"
    assert result.cs_owner_attention is True
    assert result.cs_next_best_action == "Confirm renewal status"
