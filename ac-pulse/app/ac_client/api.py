import asyncio
import random
import time
from collections.abc import Mapping
from typing import Any, cast

import httpx
import structlog

logger = structlog.get_logger(__name__)


class _TokenBucket:
    def __init__(self, rate: float, capacity: float):
        self._rate = rate
        self._capacity = capacity
        self._tokens = capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._last_refill = now
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)

                if self._tokens >= 1:
                    self._tokens -= 1
                    return

                wait_seconds = (1 - self._tokens) / self._rate

            await asyncio.sleep(wait_seconds)


_GLOBAL_RATE_LIMITER = _TokenBucket(rate=5.0, capacity=5.0)


class ActiveCampaignAPI:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = _normalize_base_url(base_url)
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(base_url=self._base_url, timeout=30.0)
        self._owns_client = client is None

    async def __aenter__(self) -> "ActiveCampaignAPI":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_account(self, account_id: int) -> dict[str, Any]:
        response = await self._request("GET", f"/accounts/{account_id}")
        return cast(dict[str, Any], response.json())

    async def list_accounts(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        response = await self._request(
            "GET",
            "/accounts",
            params={"limit": limit, "offset": offset},
        )
        payload = cast(dict[str, Any], response.json())
        rows = payload.get("accounts")
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    async def list_all_accounts(self, *, page_size: int = 100) -> list[dict[str, Any]]:
        accounts: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = await self.list_accounts(limit=page_size, offset=offset)
            accounts.extend(page)
            if len(page) < page_size:
                return accounts
            offset += page_size

    async def update_account_custom_fields(
        self,
        account_id: int,
        fields: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload = {"account": {"fields": dict(fields)}}
        response = await self._request("PUT", f"/accounts/{account_id}", json=payload)
        return cast(dict[str, Any], response.json())

    async def bulk_update_account_custom_fields(
        self,
        updates: tuple[tuple[int, Mapping[str, Any]], ...]
        | list[tuple[int, Mapping[str, Any]]],
    ) -> dict[str, Any]:
        if len(updates) == 1:
            account_id, fields = updates[0]
            return await self.update_account_custom_fields(account_id, fields)

        accounts = [
            {"id": account_id, "fields": dict(fields)} for account_id, fields in updates
        ]
        payload = {"accounts": accounts}
        response = await self._request("POST", "/accountBulkUpdates", json=payload)
        return cast(dict[str, Any], response.json())

    async def get_account_custom_fields(self) -> list[dict[str, Any]]:
        response = await self._request("GET", "/accountCustomFieldMeta")
        payload = cast(dict[str, Any], response.json())
        rows = payload.get("accountCustomFieldMeta")
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    async def create_account_custom_field(
        self,
        *,
        field_name: str,
        field_label: str,
        field_type: str,
    ) -> dict[str, Any]:
        payload = {
            "accountCustomFieldMeta": {
                "fieldName": field_name,
                "fieldLabel": field_label,
                "fieldType": field_type,
            }
        }
        response = await self._request("POST", "/accountCustomFieldMeta", json=payload)
        return cast(dict[str, Any], response.json())

    async def create_account_note(
        self,
        *,
        account_id: int,
        note: str,
    ) -> dict[str, Any]:
        payload = {"note": {"note": note}}
        response = await self._request("POST", f"/accounts/{account_id}/notes", json=payload)
        return cast(dict[str, Any], response.json())

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        retries = 5
        for attempt in range(retries + 1):
            await _GLOBAL_RATE_LIMITER.acquire()
            try:
                response = await self._client.request(
                    method=method,
                    url=path.lstrip("/"),
                    json=json,
                    params=params,
                    headers={"Api-Token": self._api_key},
                )
            except httpx.RequestError:
                if attempt == retries:
                    raise
                await asyncio.sleep(_backoff_with_jitter(attempt))
                continue

            if response.status_code == 429 or response.status_code >= 500:
                if attempt == retries:
                    response.raise_for_status()
                logger.warning(
                    "ac_request_retry",
                    method=method,
                    path=path,
                    status_code=response.status_code,
                    attempt=attempt + 1,
                )
                await asyncio.sleep(_backoff_with_jitter(attempt))
                continue

            if 400 <= response.status_code < 500:
                response.raise_for_status()

            return response

        raise RuntimeError("AC request retry loop exited unexpectedly")


def _backoff_with_jitter(attempt: int) -> float:
    base_delay = min(16.0, 0.5 * (2**attempt))
    jitter = float(random.uniform(0.0, base_delay / 2))
    return float(base_delay + jitter)


def _normalize_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/api/3"):
        return normalized
    return f"{normalized}/api/3"
