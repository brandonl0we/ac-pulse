from typing import Any

import pytest


@pytest.mark.asyncio
async def test_resync_runs_on_demand_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import main

    async def fake_run_on_demand(ctx: dict[str, Any], account_id: int) -> dict[str, Any]:
        assert ctx == {}
        assert account_id == 42
        return {
            "account_id": 42,
            "summary": {"run_id": "on_demand-1", "processed": 1},
            "audit_rows": [],
        }

    monkeypatch.setattr(main, "run_on_demand", fake_run_on_demand)

    result = await main.resync(42)

    assert result["account_id"] == 42
    assert result["summary"]["run_id"] == "on_demand-1"
