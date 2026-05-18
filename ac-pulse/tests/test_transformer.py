from app.transformer import transform_account_signals


def test_transformer_sets_critical_and_intervention_due() -> None:
    result = transform_account_signals(
        {
            "account_id": 1,
            "churn_decile_band": "Very High",
            "days_to_renewal": 45,
            "days_since_touchpoint": 35,
        }
    )
    assert result is not None
    assert result.cs_priority_tier == "Critical"
    assert result.cs_intervention_due is True


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


def test_transformer_returns_none_for_invalid_payload() -> None:
    assert transform_account_signals({"churn_decile_band": "Very High"}) is None
