from app.account_materialization import build_account_materialization_plan


def test_build_account_materialization_plan_proposes_create_and_associate() -> None:
    plan = build_account_materialization_plan(
        portfolio={
            "success_rep_name": "Kevin Oostema",
            "accounts": [
                {
                    "account_id": 42,
                    "account_name": "Example Co",
                    "account_web_domain": "example.com",
                    "arr": 12000,
                }
            ],
        },
        activecampaign_accounts=[],
        contacts_by_account_id={
            42: [{"id": "101", "email": "buyer@example.com", "firstName": "Bea"}]
        },
        limit=10,
        diagnostics={"activecampaign_account_lookup": "timeout"},
    )

    assert plan["mode"] == "dry_run"
    assert plan["source"]["diagnostics"]["activecampaign_account_lookup"] == "timeout"
    assert plan["summary"]["create_account_and_associate_contacts"] == 1
    assert plan["accounts"][0]["action"] == "create_account_and_associate_contacts"
    assert plan["accounts"][0]["matching_contact_count"] == 1


def test_build_account_materialization_plan_uses_existing_account() -> None:
    plan = build_account_materialization_plan(
        portfolio={
            "success_rep_name": "Kevin Oostema",
            "accounts": [
                {
                    "account_id": 42,
                    "account_name": "example.com",
                    "account_web_domain": "example.com",
                    "arr": 12000,
                }
            ],
        },
        activecampaign_accounts=[
            {"id": "9001", "name": "Example", "accountUrl": "https://example.com"}
        ],
        contacts_by_account_id={42: []},
        limit=10,
    )

    assert plan["summary"]["use_existing_account"] == 1
    assert plan["accounts"][0]["existing_ac_account"]["ac_account_id"] == 9001
