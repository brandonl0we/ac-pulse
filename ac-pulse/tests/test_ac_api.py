from unittest.mock import patch

import httpx
import pytest

from app.ac_client.api import ActiveCampaignAPI, _normalize_base_url


def test_ac_api_normalizes_root_base_url_to_api_v3() -> None:
    assert _normalize_base_url("https://example.test") == "https://example.test/api/3"
    assert _normalize_base_url("https://example.test/api/3") == "https://example.test/api/3"


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
    assert request_mock.call_args.kwargs["headers"] == {"Api-Token": "key"}


@pytest.mark.asyncio
async def test_create_account_note_posts_to_account_notes() -> None:
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
                status_code=201,
                request=httpx.Request("POST", "/accounts/123/notes"),
                json={"note": {"id": "note-1"}},
            ),
        ) as request_mock:
            payload = await api.create_account_note(
                account_id=123,
                note="Follow up note",
            )

    assert payload == {"note": {"id": "note-1"}}
    request_mock.assert_called_once()
    assert request_mock.call_args.kwargs["method"] == "POST"
    assert request_mock.call_args.kwargs["url"] == "accounts/123/notes"
    assert request_mock.call_args.kwargs["json"] == {
        "note": {"note": "Follow up note"}
    }


@pytest.mark.asyncio
async def test_list_all_accounts_pages_until_short_page() -> None:
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
                httpx.Response(
                    status_code=200,
                    request=httpx.Request("GET", "/accounts"),
                    json={"accounts": [{"id": "1"}, {"id": "2"}]},
                ),
                httpx.Response(
                    status_code=200,
                    request=httpx.Request("GET", "/accounts"),
                    json={"accounts": [{"id": "3"}]},
                ),
            ],
        ) as request_mock:
            payload = await api.list_all_accounts(page_size=2)

    assert payload == [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    assert request_mock.call_count == 2
    assert request_mock.call_args_list[0].kwargs["params"] == {"limit": 2, "offset": 0}
    assert request_mock.call_args_list[1].kwargs["params"] == {"limit": 2, "offset": 2}
    assert request_mock.call_args_list[0].kwargs["url"] == "accounts"
    assert request_mock.call_args_list[0].kwargs["headers"] == {"Api-Token": "key"}


@pytest.mark.asyncio
async def test_search_contacts_uses_contact_search_endpoint() -> None:
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
                status_code=200,
                request=httpx.Request("GET", "/contacts"),
                json={"contacts": [{"id": "101", "email": "buyer@example.com"}]},
            ),
        ) as request_mock:
            contacts = await api.search_contacts(search="example.com")

    assert contacts == [{"id": "101", "email": "buyer@example.com"}]
    assert request_mock.call_args.kwargs["url"] == "contacts"
    assert request_mock.call_args.kwargs["params"] == {
        "search": "example.com",
        "limit": 100,
        "offset": 0,
    }
    assert request_mock.call_args.kwargs["headers"] == {"Api-Token": "key"}
