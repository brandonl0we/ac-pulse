from typing import Any

import pytest


@pytest.mark.asyncio
async def test_index_returns_portfolio_shell() -> None:
    from app import main

    html = await main.index()
    app_html = await main.app_index()

    assert "ac-pulse" in html
    assert app_html == html
    assert "/portfolio?rep_name=" in html
    assert "/actions/plan" in html
    assert "/actions/commit" in html
    assert "Action Plan" in html
    assert "Preview Actions" in html
    assert "Commit Notes" in html
    assert "Account Mapping" in html
    assert "/admin/account-map/preview" in html
    assert "ACCOUNT_ID_MAP_JSON" in html
    assert r"\\\"" not in html
    assert "class='selected'" in html
    assert "Kevin Oostema" in html


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
async def test_account_pulse_returns_built_pulse(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import main

    class FakeSnowflakeClient:
        def __init__(self, settings: Any) -> None:
            self.settings = settings

    class FakeExtractor:
        def __init__(self, sf: FakeSnowflakeClient) -> None:
            self.sf = sf

    async def fake_build_account_pulse(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["snowflake_account_id"] == 42
        assert len(list(kwargs["extractor_instances"])) == 6
        return {
            "snowflake_account_id": 42,
            "activecampaign_account_id": 202,
            "command": {"health_status": "Critical"},
            "metrics": {},
        }

    monkeypatch.setattr(main, "SnowflakeClient", FakeSnowflakeClient)
    monkeypatch.setattr(main, "ChurnExtractor", FakeExtractor)
    monkeypatch.setattr(main, "ACAIExtractor", FakeExtractor)
    monkeypatch.setattr(main, "NBNExtractor", FakeExtractor)
    monkeypatch.setattr(main, "UtilizationExtractor", FakeExtractor)
    monkeypatch.setattr(main, "TouchpointsExtractor", FakeExtractor)
    monkeypatch.setattr(main, "RenewalExtractor", FakeExtractor)
    monkeypatch.setattr(main, "build_account_resolver", lambda path, inline_json=None: None)
    monkeypatch.setattr(main, "build_account_pulse", fake_build_account_pulse)

    result = await main.account_pulse(42)

    assert result["snowflake_account_id"] == 42
    assert result["activecampaign_account_id"] == 202


@pytest.mark.asyncio
async def test_success_rep_portfolio_returns_built_portfolio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import main

    class FakeSnowflakeClient:
        def __init__(self, settings: Any) -> None:
            self.settings = settings

    async def fake_build_success_rep_portfolio(**kwargs: Any) -> dict[str, Any]:
        assert isinstance(kwargs["snowflake_client"], FakeSnowflakeClient)
        assert kwargs["rep_name"] == "Kevin Oostema"
        return {
            "success_rep_name": "Kevin Oostema",
            "summary": {"account_count": 197},
            "accounts": [],
        }

    monkeypatch.setattr(main, "SnowflakeClient", FakeSnowflakeClient)
    monkeypatch.setattr(
        main,
        "build_success_rep_portfolio",
        fake_build_success_rep_portfolio,
    )

    result = await main.success_rep_portfolio("Kevin Oostema")

    assert result["success_rep_name"] == "Kevin Oostema"
    assert result["summary"]["account_count"] == 197


@pytest.mark.asyncio
async def test_success_rep_portfolio_query_route_reuses_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import main

    async def fake_success_rep_portfolio(rep_name: str) -> dict[str, Any]:
        assert rep_name == "Kevin Oostema"
        return {"success_rep_name": rep_name, "accounts": []}

    monkeypatch.setattr(main, "success_rep_portfolio", fake_success_rep_portfolio)

    result = await main.success_rep_portfolio_query("Kevin Oostema")

    assert result["success_rep_name"] == "Kevin Oostema"


@pytest.mark.asyncio
async def test_plan_actions_builds_dry_run_from_portfolio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import main

    class FakeSnowflakeClient:
        def __init__(self, settings: Any) -> None:
            self.settings = settings

    async def fake_build_success_rep_portfolio(**kwargs: Any) -> dict[str, Any]:
        assert isinstance(kwargs["snowflake_client"], FakeSnowflakeClient)
        assert kwargs["rep_name"] == "Kevin Oostema"
        return {
            "success_rep_name": "Kevin Oostema",
            "summary": {"account_count": 1},
            "accounts": [{"account_id": 42}],
        }

    def fake_build_action_plan(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["portfolio"]["success_rep_name"] == "Kevin Oostema"
        assert kwargs["account_ids"] == [42]
        assert kwargs["limit"] == 10
        return {
            "mode": "dry_run",
            "summary": {"planned_actions": 1},
            "actions": [{"snowflake_account_id": 42}],
            "skipped": [],
        }

    monkeypatch.setattr(main, "SnowflakeClient", FakeSnowflakeClient)
    monkeypatch.setattr(
        main,
        "build_success_rep_portfolio",
        fake_build_success_rep_portfolio,
    )
    monkeypatch.setattr(main, "build_action_plan", fake_build_action_plan)

    result = await main.plan_actions(
        main.ActionPlanRequest(
            rep_name="Kevin Oostema",
            account_ids=[42],
            limit=10,
        )
    )

    assert result["mode"] == "dry_run"
    assert result["actions"][0]["snowflake_account_id"] == 42


@pytest.mark.asyncio
async def test_account_map_preview_builds_read_only_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import main

    class FakeSnowflakeClient:
        def __init__(self, settings: Any) -> None:
            self.settings = settings

    class FakeActiveCampaignAPI:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        async def __aenter__(self) -> "FakeActiveCampaignAPI":
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        async def list_all_accounts(self) -> list[dict[str, Any]]:
            return [{"id": "9001", "accountUrl": "https://biofit.activehosted.com"}]

    async def fake_build_success_rep_portfolio(**kwargs: Any) -> dict[str, Any]:
        assert isinstance(kwargs["snowflake_client"], FakeSnowflakeClient)
        assert kwargs["rep_name"] == "Kevin Oostema"
        return {
            "success_rep_name": "Kevin Oostema",
            "accounts": [
                {
                    "account_id": 1043604,
                    "account_name": "biofit.activehosted.com",
                    "account_web_domain": "biofit.example",
                    "arr": 14721,
                }
            ],
        }

    monkeypatch.setattr(main.settings, "service_api_key", "secret")
    monkeypatch.setattr(main, "SnowflakeClient", FakeSnowflakeClient)
    monkeypatch.setattr(main, "ActiveCampaignAPI", FakeActiveCampaignAPI)
    monkeypatch.setattr(
        main,
        "build_success_rep_portfolio",
        fake_build_success_rep_portfolio,
    )

    result = await main.account_map_preview(
        rep_name="Kevin Oostema",
        x_service_key="secret",
    )

    assert result["mode"] == "read_only"
    assert result["summary"]["matched"] == 1
    assert "1043604,9001" in result["csv"]


@pytest.mark.asyncio
async def test_account_map_preview_reports_activecampaign_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException

    from app import main

    class FakeSnowflakeClient:
        def __init__(self, settings: Any) -> None:
            self.settings = settings

    class FakeActiveCampaignAPI:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        async def __aenter__(self) -> "FakeActiveCampaignAPI":
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        async def list_all_accounts(self) -> list[dict[str, Any]]:
            raise RuntimeError("AC auth failed")

    async def fake_build_success_rep_portfolio(**kwargs: Any) -> dict[str, Any]:
        return {"success_rep_name": "Kevin Oostema", "accounts": []}

    monkeypatch.setattr(main.settings, "service_api_key", "secret")
    monkeypatch.setattr(main, "SnowflakeClient", FakeSnowflakeClient)
    monkeypatch.setattr(main, "ActiveCampaignAPI", FakeActiveCampaignAPI)
    monkeypatch.setattr(
        main,
        "build_success_rep_portfolio",
        fake_build_success_rep_portfolio,
    )

    with pytest.raises(HTTPException) as exc_info:
        await main.account_map_preview(
            rep_name="Kevin Oostema",
            x_service_key="secret",
        )

    assert exc_info.value.status_code == 502
    assert "Unable to list ActiveCampaign accounts" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_commit_actions_builds_plan_and_commits_selected_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import main

    class FakeSnowflakeClient:
        def __init__(self, settings: Any) -> None:
            self.settings = settings

    class FakeActiveCampaignAPI:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        async def __aenter__(self) -> "FakeActiveCampaignAPI":
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    async def fake_build_success_rep_portfolio(**kwargs: Any) -> dict[str, Any]:
        assert isinstance(kwargs["snowflake_client"], FakeSnowflakeClient)
        assert kwargs["rep_name"] == "Kevin Oostema"
        return {
            "success_rep_name": "Kevin Oostema",
            "summary": {"account_count": 1},
            "accounts": [{"account_id": 42}],
        }

    def fake_build_action_plan(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["portfolio"]["success_rep_name"] == "Kevin Oostema"
        assert kwargs["account_ids"] == [42]
        assert kwargs["limit"] == 10
        assert kwargs["resolver"] == "resolver"
        return {"actions": [{"dedupe_key": "cs:task:42:x"}]}

    async def fake_commit_action_plan(**kwargs: Any) -> dict[str, Any]:
        assert isinstance(kwargs["activecampaign_api"], FakeActiveCampaignAPI)
        assert kwargs["dedupe_keys"] == ["cs:task:42:x"]
        assert kwargs["confirm"] is True
        return {"status": "committed", "summary": {"committed": 1}}

    monkeypatch.setattr(main, "SnowflakeClient", FakeSnowflakeClient)
    monkeypatch.setattr(main, "ActiveCampaignAPI", FakeActiveCampaignAPI)
    monkeypatch.setattr(
        main,
        "build_success_rep_portfolio",
        fake_build_success_rep_portfolio,
    )
    monkeypatch.setattr(main, "build_action_plan", fake_build_action_plan)
    monkeypatch.setattr(main, "commit_action_plan", fake_commit_action_plan)
    monkeypatch.setattr(
        main,
        "build_account_resolver",
        lambda path, inline_json=None: "resolver",
    )

    result = await main.commit_actions(
        main.ActionCommitRequest(
            rep_name="Kevin Oostema",
            account_ids=[42],
            dedupe_keys=["cs:task:42:x"],
            limit=10,
            confirm=True,
        )
    )

    assert result["status"] == "committed"
    assert result["summary"]["committed"] == 1


@pytest.mark.asyncio
async def test_account_pulse_raises_404_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import HTTPException

    from app import main

    class FakeSnowflakeClient:
        def __init__(self, settings: Any) -> None:
            self.settings = settings

    class FakeExtractor:
        def __init__(self, sf: FakeSnowflakeClient) -> None:
            self.sf = sf

    async def fake_build_account_pulse(**kwargs: Any) -> None:
        del kwargs
        return None

    monkeypatch.setattr(main, "SnowflakeClient", FakeSnowflakeClient)
    monkeypatch.setattr(main, "ChurnExtractor", FakeExtractor)
    monkeypatch.setattr(main, "ACAIExtractor", FakeExtractor)
    monkeypatch.setattr(main, "NBNExtractor", FakeExtractor)
    monkeypatch.setattr(main, "UtilizationExtractor", FakeExtractor)
    monkeypatch.setattr(main, "TouchpointsExtractor", FakeExtractor)
    monkeypatch.setattr(main, "RenewalExtractor", FakeExtractor)
    monkeypatch.setattr(main, "build_account_resolver", lambda path, inline_json=None: None)
    monkeypatch.setattr(main, "build_account_pulse", fake_build_account_pulse)

    with pytest.raises(HTTPException) as exc:
        await main.account_pulse(404)

    assert exc.value.status_code == 404
