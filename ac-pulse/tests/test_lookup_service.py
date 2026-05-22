"""Unit tests for the dedupe lookup service.

Covers:
  - response shaping (the part that runs deterministically without I/O)
  - end-to-end lookup with the MCP call patched
  - cache hit short-circuits the MCP call
  - graceful failure when Zapier raises
"""

import json
from typing import Any

import pytest

from app.config import Settings
from app.lookup_service import (
    _build_sql,
    lookup_customer_by_email,
    shape_response,
)
from app.zapier_client import ZapierMCPError


class FakeRedis:
    """Minimal in-memory redis stand-in for the cache test paths."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value


# ── shape_response ────────────────────────────────────────────────────


def test_shape_response_empty_rows() -> None:
    out = shape_response("user@example.com", [])
    assert out["is_customer"] is False
    assert out["is_known"] is False
    assert out["highest_value_match"] is None
    assert out["exact_email_matches"] == []
    assert out["summary"]["accounts"] == 0
    assert out["input_domain"] == "example.com"


def test_shape_response_active_paid_customer_with_higher_arr_account() -> None:
    rows: list[dict[str, Any]] = [
        {
            "record_type": "ACCOUNT", "account_id": 1, "matched_email": "admin@acme.com",
            "match_type": "DOMAIN_MATCH", "discovery_source": "ACCOUNT_EXTENSION",
            "account_name": "acme.activehosted.com", "arr": 24000,
            "account_status": "Active Paid",
        },
        {
            "record_type": "ACCOUNT", "account_id": 2, "matched_email": "admin2@acme.com",
            "match_type": "ADMIN_EMAIL", "discovery_source": "ACCOUNT_EXTENSION",
            "account_name": "acme2.activehosted.com", "arr": 60000,
            "account_status": "Active Paid",
        },
        {
            "record_type": "DEAL", "deal_id": 99, "matched_email": "lead@acme.com",
            "match_type": "DOMAIN_MATCH", "discovery_source": "DEALS_MAT",
            "deal_status": "Open",
        },
    ]
    out = shape_response("admin@acme.com", rows)
    assert out["is_customer"] is True
    assert out["is_known"] is True
    # Highest ARR wins
    assert out["highest_value_match"]["account_id"] == 2
    # ADMIN_EMAIL on the input email itself counts as an exact match
    assert len(out["exact_email_matches"]) == 1
    assert out["exact_email_matches"][0]["match_type"] == "ADMIN_EMAIL"
    assert out["summary"]["accounts"] == 2
    assert out["summary"]["deals"] == 1
    assert out["summary"]["active_paid_accounts"] == 2


def test_shape_response_known_but_not_customer() -> None:
    rows = [
        {
            "record_type": "ACCOUNT", "account_id": 7, "arr": 0,
            "match_type": "DOMAIN_MATCH", "discovery_source": "ACCOUNT_EXTENSION",
            "account_status": "Trial / Never Converted",
        },
    ]
    out = shape_response("someone@evalco.com", rows)
    assert out["is_known"] is True
    assert out["is_customer"] is False
    assert out["highest_value_match"]["account_id"] == 7


# ── _build_sql ────────────────────────────────────────────────────────


def test_build_sql_substitutes_email() -> None:
    sql = _build_sql("user@example.com")
    assert "'user@example.com'" in sql
    assert ":EMAIL" not in sql


def test_build_sql_rejects_malformed_email() -> None:
    with pytest.raises(ValueError):
        _build_sql("not-an-email")


def test_build_sql_rejects_sql_injection_attempts() -> None:
    # Anything containing quotes/semicolons fails the email regex.
    bad_inputs = ["a@b.com'); DROP TABLE--", "x@y.com; DELETE FROM", "x'@y.com"]
    for bad in bad_inputs:
        with pytest.raises(ValueError):
            _build_sql(bad)


# ── lookup_customer_by_email ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_lookup_uses_cache_when_present(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    redis = FakeRedis()
    redis.store["acpulse:lookup:email:cached@acme.com"] = json.dumps(
        {"input_email": "cached@acme.com", "is_customer": True, "is_known": True}
    )

    async def explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("MCP should not be called when cache hits")

    monkeypatch.setattr("app.lookup_service.execute_snowflake_sql", explode)

    out = await lookup_customer_by_email(settings, redis, "cached@acme.com")
    assert out["is_customer"] is True
    assert out["cached"] is True


@pytest.mark.asyncio
async def test_lookup_calls_mcp_and_caches(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    redis = FakeRedis()
    captured: dict[str, Any] = {}

    async def fake_execute(*, server_url: str, token: str, statement: str, **kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        captured["url"] = server_url
        captured["statement"] = statement
        return [{
            "record_type": "ACCOUNT", "account_id": 42, "arr": 1000,
            "match_type": "ADMIN_EMAIL", "discovery_source": "ACCOUNT_EXTENSION",
            "account_status": "Active Paid",
        }], {"block_count": 1, "block_types": ["text"], "raw_text_preview": "stub", "parsed_row_count": 1}

    monkeypatch.setattr("app.lookup_service.execute_snowflake_sql", fake_execute)

    out = await lookup_customer_by_email(settings, redis, "Alice@AcmeCo.com")
    assert out["is_customer"] is True
    assert out["cached"] is False
    assert out["source"] == "zapier_mcp"
    # Email normalized to lowercase before reaching MCP/cache.
    assert "'alice@acmeco.com'" in captured["statement"]
    # Result cached under normalized key.
    assert "acpulse:lookup:email:alice@acmeco.com" in redis.store


@pytest.mark.asyncio
async def test_lookup_fails_closed_when_mcp_errors(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    redis = FakeRedis()

    async def fake_execute(**kwargs: Any) -> list[dict[str, Any]]:
        raise ZapierMCPError("boom")

    monkeypatch.setattr("app.lookup_service.execute_snowflake_sql", fake_execute)

    out = await lookup_customer_by_email(settings, redis, "x@example.com")
    assert out["is_customer"] is None
    assert out["reason"] == "lookup_unavailable"
    assert "boom" in out["error"]


# ── Zapier response-shape regression test ────────────────────────────

def test_extract_rows_handles_zapier_results_list_shape() -> None:
    """Zapier's snowflake_execute_sql returns {"results": [{...}]} —
    a list directly under "results", not a nested {"rows": [...]}.
    Regression test for the bug where /lookup returned empty for known
    customers because the parser only recognized {"results": {"rows": ...}}."""
    from app.zapier_client import _extract_rows

    payload = {
        "results": [
            {
                "record_type": "ACCOUNT",
                "account_id": 4129021,
                "matched_email": "admin@example.com",
                "account_status": "Active Paid",
            },
            {
                "record_type": "DEAL",
                "deal_id": 99,
                "matched_email": "lead@example.com",
            },
        ]
    }
    rows = _extract_rows(payload)
    assert rows is not None
    assert len(rows) == 2
    assert rows[0]["account_id"] == 4129021
    assert rows[1]["deal_id"] == 99


@pytest.mark.asyncio
async def test_lookup_rejects_invalid_email(settings: Settings) -> None:
    redis = FakeRedis()
    out = await lookup_customer_by_email(settings, redis, "not-an-email")
    assert out["reason"] == "invalid_email"
    assert out["is_customer"] is None
