import pytest

from app.workers import monthly, nightly, on_demand, weekly_snapshot


@pytest.mark.asyncio
async def test_nightly_worker_calls_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_signal_sync(**kwargs: object) -> dict[str, int | str]:
        assert kwargs["worker_name"] == "nightly"
        return {
            "run_id": "nightly-1",
            "worker": "nightly",
            "processed": 10,
            "skipped": 2,
            "failed": 0,
            "changed_fields": 5,
        }

    async def fake_alert(summary: dict[str, object]) -> None:
        assert summary["worker"] == "nightly"

    monkeypatch.setattr("app.workers.nightly.run_signal_sync", fake_run_signal_sync)
    monkeypatch.setattr("app.workers.nightly.maybe_alert_on_summary", fake_alert)

    result = await nightly.run_nightly({})
    assert result["worker"] == "nightly"
    assert result["processed"] == "10"


@pytest.mark.asyncio
async def test_weekly_snapshot_worker_calls_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_write_weekly_snapshot(_snowflake_client: object) -> dict[str, str]:
        return {"status": "ok", "executed_at": "2026-01-01T00:00:00+00:00"}

    monkeypatch.setattr(
        "app.workers.weekly_snapshot.write_weekly_snapshot",
        fake_write_weekly_snapshot,
    )
    result = await weekly_snapshot.run_weekly_snapshot({})
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_on_demand_returns_audit_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_signal_sync(**kwargs: object) -> dict[str, int | str]:
        assert kwargs["worker_name"] == "on_demand"
        assert kwargs["account_filter"] == 42
        return {
            "run_id": "on_demand-1",
            "worker": "on_demand",
            "processed": 1,
            "skipped": 0,
            "failed": 0,
            "changed_fields": 2,
        }

    async def fake_get_audit_rows_for_run(run_id: str) -> list[dict[str, str]]:
        assert run_id == "on_demand-1"
        return [{"run_id": run_id, "status": "success"}]

    monkeypatch.setattr("app.workers.on_demand.run_signal_sync", fake_run_signal_sync)
    monkeypatch.setattr("app.workers.on_demand.get_audit_rows_for_run", fake_get_audit_rows_for_run)
    result = await on_demand.run_on_demand({}, 42)
    assert result["account_id"] == 42
    assert result["audit_rows"] == [{"run_id": "on_demand-1", "status": "success"}]


@pytest.mark.asyncio
async def test_monthly_worker_calls_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_signal_sync(**kwargs: object) -> dict[str, int | str]:
        assert kwargs["worker_name"] == "monthly"
        return {
            "run_id": "monthly-1",
            "worker": "monthly",
            "processed": 5,
            "skipped": 1,
            "failed": 0,
            "changed_fields": 3,
        }

    async def fake_alert(summary: dict[str, object]) -> None:
        assert summary["worker"] == "monthly"

    monkeypatch.setattr("app.workers.monthly.run_signal_sync", fake_run_signal_sync)
    monkeypatch.setattr("app.workers.monthly.maybe_alert_on_summary", fake_alert)

    result = await monthly.run_monthly({})
    assert result["worker"] == "monthly"
