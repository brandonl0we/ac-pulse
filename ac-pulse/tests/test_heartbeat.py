"""Heartbeat cron tests — verify each branch triggers the right alert
behavior without touching real Redis or Zapier MCP."""

from typing import Any

import pytest

from app.workers.heartbeat import run_heartbeat


@pytest.fixture
def alerts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Capture send_alert calls into a list rather than hitting Slack."""
    captured: list[str] = []

    async def fake_send(msg: str) -> None:
        captured.append(msg)

    monkeypatch.setattr("app.workers.heartbeat.send_alert", fake_send)
    return captured


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace Redis.from_url with a no-op stub — heartbeat doesn't
    actually need Redis when we also stub out lookup_customer_by_email."""

    class StubRedis:
        @staticmethod
        def from_url(*args: Any, **kwargs: Any) -> "StubRedis":
            return StubRedis()

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr("app.workers.heartbeat.Redis", StubRedis)


def _patch_lookup(monkeypatch: pytest.MonkeyPatch, return_value: dict[str, Any]) -> None:
    async def fake_lookup(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return return_value

    monkeypatch.setattr("app.workers.heartbeat.lookup_customer_by_email", fake_lookup)


@pytest.mark.asyncio
async def test_heartbeat_skips_when_email_unset(
    monkeypatch: pytest.MonkeyPatch, alerts: list[str], fake_redis: None
) -> None:
    monkeypatch.delenv("HEARTBEAT_TEST_EMAIL", raising=False)
    # Re-init settings to pick up the env change
    from app.config import get_settings
    get_settings.cache_clear()

    result = await run_heartbeat({})
    assert result == {"skipped": True}
    assert alerts == []


@pytest.mark.asyncio
async def test_heartbeat_alerts_on_lookup_unavailable(
    monkeypatch: pytest.MonkeyPatch, alerts: list[str], fake_redis: None
) -> None:
    monkeypatch.setenv("HEARTBEAT_TEST_EMAIL", "test@activecampaign.com")
    from app.config import get_settings
    get_settings.cache_clear()

    _patch_lookup(monkeypatch, {
        "input_email": "test@activecampaign.com",
        "is_customer": None,
        "is_known": None,
        "reason": "lookup_unavailable",
        "error": "MCP call failed: boom",
        "elapsed_ms": 30000,
    })

    result = await run_heartbeat({})
    assert result["ok"] is False
    assert len(alerts) == 1
    assert "unavailable" in alerts[0].lower()
    assert "boom" in alerts[0]


@pytest.mark.asyncio
async def test_heartbeat_alerts_on_unexpected_unknown(
    monkeypatch: pytest.MonkeyPatch, alerts: list[str], fake_redis: None
) -> None:
    monkeypatch.setenv("HEARTBEAT_TEST_EMAIL", "test@activecampaign.com")
    from app.config import get_settings
    get_settings.cache_clear()

    _patch_lookup(monkeypatch, {
        "input_email": "test@activecampaign.com",
        "is_customer": False,
        "is_known": False,
        "total_rows": 0,
        "elapsed_ms": 1500,
    })

    result = await run_heartbeat({})
    assert result["ok"] is False
    assert len(alerts) == 1
    assert "drift" in alerts[0].lower()


@pytest.mark.asyncio
async def test_heartbeat_ok_path(
    monkeypatch: pytest.MonkeyPatch, alerts: list[str], fake_redis: None
) -> None:
    monkeypatch.setenv("HEARTBEAT_TEST_EMAIL", "test@activecampaign.com")
    from app.config import get_settings
    get_settings.cache_clear()

    _patch_lookup(monkeypatch, {
        "input_email": "test@activecampaign.com",
        "is_customer": True,
        "is_known": True,
        "total_rows": 3,
        "elapsed_ms": 1800,
    })

    result = await run_heartbeat({})
    assert result["ok"] is True
    assert result["is_customer"] is True
    assert alerts == []
