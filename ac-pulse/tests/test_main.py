from typing import Any

import pytest
from fastapi import HTTPException


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


@pytest.mark.asyncio
async def test_resync_fails_when_mapping_blocks_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import main

    async def fake_run_on_demand(ctx: dict[str, Any], account_id: int) -> dict[str, Any]:
        del ctx, account_id
        return {
            "account_id": 42,
            "summary": {"run_id": "on_demand-1", "processed": 0, "failed": 1},
            "audit_rows": [],
        }

    monkeypatch.setattr(main, "run_on_demand", fake_run_on_demand)

    with pytest.raises(HTTPException) as exc_info:
        await main.resync(42)

    assert exc_info.value.status_code == 424


@pytest.mark.asyncio
async def test_resync_fails_when_account_has_no_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import main

    async def fake_run_on_demand(ctx: dict[str, Any], account_id: int) -> dict[str, Any]:
        del ctx, account_id
        return {
            "account_id": 42,
            "summary": {"run_id": "on_demand-1", "processed": 0, "failed": 0},
            "audit_rows": [],
        }

    monkeypatch.setattr(main, "run_on_demand", fake_run_on_demand)

    with pytest.raises(HTTPException) as exc_info:
        await main.resync(42)

    assert exc_info.value.status_code == 404
