from datetime import date

import pytest

from app.extractors.acai import ACAIExtractor
from app.extractors.churn import ChurnExtractor
from app.extractors.nbn import NBNExtractor
from app.extractors.renewal import RenewalExtractor
from app.extractors.touchpoints import TouchpointsExtractor
from app.extractors.utilization import UtilizationExtractor


@pytest.mark.asyncio
async def test_churn_extractor_shape(mock_snowflake_client, fixture_json) -> None:
    mock_snowflake_client.responses = fixture_json("snowflake_churn.json")
    extractor = ChurnExtractor(mock_snowflake_client)

    actual = await extractor.extract()

    assert actual == {
        101: {"account_id": 101, "churn_decile_band": "Very High", "churn_score": 0.97},
        202: {"account_id": 202, "churn_decile_band": "High", "churn_score": 0.73},
    }


@pytest.mark.asyncio
async def test_acai_extractor_shape(mock_snowflake_client, fixture_json) -> None:
    mock_snowflake_client.responses = fixture_json("snowflake_acai.json")
    extractor = ACAIExtractor(mock_snowflake_client)

    actual = await extractor.extract()

    assert actual == {
        101: {"account_id": 101, "acai_score": 82.5},
        202: {"account_id": 202, "acai_score": 51.0},
    }


@pytest.mark.asyncio
async def test_nbn_extractor_shape(mock_snowflake_client) -> None:
    mock_snowflake_client.responses = [
        {"ACCOUNT_ID": 101, "NBN_SCORE": 33.1},
        {"ACCOUNT_ID": 202, "NBN_SCORE": 62.2},
    ]
    extractor = NBNExtractor(mock_snowflake_client)

    actual = await extractor.extract()

    assert actual[101]["nbn_score"] == 33.1
    assert actual[202]["nbn_score"] == 62.2


@pytest.mark.asyncio
async def test_utilization_extractor_shape(mock_snowflake_client) -> None:
    mock_snowflake_client.responses = [
        {"ACCOUNT_ID": 101, "UTILIZATION_PERCENT": 48.4},
    ]
    extractor = UtilizationExtractor(mock_snowflake_client)

    actual = await extractor.extract()

    assert actual[101] == {"account_id": 101, "utilization_percent": 48.4}


@pytest.mark.asyncio
async def test_touchpoints_extractor_shape(mock_snowflake_client) -> None:
    mock_snowflake_client.responses = [
        {"ACCOUNT_ID": 101, "DAYS_SINCE_TOUCHPOINT": 45, "TOUCHPOINT_COUNT_30D": 0},
    ]
    extractor = TouchpointsExtractor(mock_snowflake_client)

    actual = await extractor.extract()

    assert actual[101] == {
        "account_id": 101,
        "days_since_touchpoint": 45,
        "touchpoint_count_30d": 0,
    }


@pytest.mark.asyncio
async def test_renewal_extractor_shape(mock_snowflake_client) -> None:
    mock_snowflake_client.responses = [
        {"ACCOUNT_ID": 101, "DAYS_TO_RENEWAL": 60, "RENEWAL_DATE": date(2026, 7, 17)},
    ]
    extractor = RenewalExtractor(mock_snowflake_client)

    actual = await extractor.extract()

    assert actual[101]["days_to_renewal"] == 60
    assert actual[101]["renewal_date"] == date(2026, 7, 17)
