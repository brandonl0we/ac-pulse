from typing import Any

import pytest

from app.portfolio import build_success_rep_portfolio


class FakeSnowflakeClient:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows
        self.sql: str | None = None
        self.params: dict[str, Any] | None = None

    async def execute(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.sql = sql
        self.params = params
        return self.rows


@pytest.mark.asyncio
async def test_build_success_rep_portfolio_shapes_summary_and_queue() -> None:
    client = FakeSnowflakeClient(
        [
            {
                "ACCOUNT_ID": 1,
                "ACCOUNT_NAME": "healthy.activehosted.com",
                "SUCCESS_REP_NAME": "Kevin Oostema",
                "PLAN_TIER_NAME": "Enterprise",
                "MRR": 1000,
                "ARR": 12000,
                "CURRENT_CHURN_RISK_3MO": "Low",
                "CURRENT_OVERALL_PREDICTION_TYPE_RISK": "Low",
                "PRODUCT_SCORE": 70,
                "LATEST_NPS_SCORE": 9,
                "TOTAL_TOUCHPOINTS_90D": 5,
                "DAYS_SINCE_LAST_TP": 3,
                "TOTAL_TOUCHPOINTS_30D": 2,
            },
            {
                "ACCOUNT_ID": 2,
                "ACCOUNT_NAME": "risk.activehosted.com",
                "SUCCESS_REP_NAME": "Kevin Oostema",
                "PLAN_TIER_NAME": "Professional",
                "MRR": 2000,
                "ARR": 24000,
                "CURRENT_CHURN_RISK_3MO": "Very High",
                "CURRENT_OVERALL_PREDICTION_TYPE_RISK": "Moderate",
                "PRODUCT_SCORE": 20,
                "LATEST_NPS_SCORE": 0,
                "TOTAL_TOUCHPOINTS_90D": 4,
                "DAYS_SINCE_LAST_TP": 14,
                "TOTAL_TOUCHPOINTS_30D": 1,
            },
        ]
    )

    portfolio = await build_success_rep_portfolio(
        snowflake_client=client,
        rep_name="Kevin Oostema",
    )

    assert client.params == {"rep_name": "Kevin Oostema"}
    assert "%(rep_name)s" in (client.sql or "")
    assert portfolio["summary"]["account_count"] == 2
    assert portfolio["summary"]["total_arr"] == 36000
    assert portfolio["summary"]["high_or_very_high_churn_count"] == 1
    assert portfolio["summary"]["nps_detractor_arr"] == 24000
    assert portfolio["accounts"][0]["account_id"] == 2
    assert portfolio["accounts"][0]["command"]["health_status"] == "Critical"
    assert portfolio["accounts"][0]["command"]["next_best_action"] == (
        "Schedule churn-risk outreach"
    )


@pytest.mark.asyncio
async def test_build_success_rep_portfolio_handles_empty_book() -> None:
    client = FakeSnowflakeClient([])

    portfolio = await build_success_rep_portfolio(
        snowflake_client=client,
        rep_name="Missing Rep",
    )

    assert portfolio["summary"]["account_count"] == 0
    assert portfolio["summary"]["total_arr"] == 0
    assert portfolio["accounts"] == []
