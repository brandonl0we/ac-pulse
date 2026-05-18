from unittest.mock import patch

import httpx
import pytest

from app.ac_client.api import ActiveCampaignAPI


@pytest.mark.asyncio
async def test_ac_api_retries_on_5xx() -> None:
    with patch("app.ac_client.api._backoff_with_jitter", return_value=0.0):
        async with httpx.AsyncClient(base_url="https://example.test/api/3") as client:
            api = ActiveCampaignAPI(
                base_url="https://example.test/api/3",
                api_key="key",
                client=client,
            )
            with patch.object(
                client,
                "request",
                side_effect=[
                    httpx.Response(status_code=500, request=httpx.Request("GET", "/accounts/1")),
                    httpx.Response(status_code=502, request=httpx.Request("GET", "/accounts/1")),
                    httpx.Response(
                        status_code=200,
                        request=httpx.Request("GET", "/accounts/1"),
                        json={"account": {"id": "1"}},
                    ),
                ],
            ) as request_mock:
                payload = await api.get_account(1)

    assert payload == {"account": {"id": "1"}}
    assert request_mock.call_count == 3


@pytest.mark.asyncio
async def test_ac_api_does_not_retry_on_non_429_4xx() -> None:
    async with httpx.AsyncClient(base_url="https://example.test/api/3") as client:
        api = ActiveCampaignAPI(
            base_url="https://example.test/api/3",
            api_key="key",
            client=client,
        )
        with patch.object(
            client,
            "request",
            return_value=httpx.Response(
                status_code=400,
                request=httpx.Request("GET", "/accounts/1"),
                json={"error": "bad request"},
            ),
        ) as request_mock, pytest.raises(httpx.HTTPStatusError):
            await api.get_account(1)

    assert request_mock.call_count == 1
