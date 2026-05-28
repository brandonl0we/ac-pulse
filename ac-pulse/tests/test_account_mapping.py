from app.account_mapping import build_account_map_preview


def test_build_account_map_preview_matches_activehosted_domain() -> None:
    preview = build_account_map_preview(
        portfolio={
            "success_rep_name": "Kevin Oostema",
            "accounts": [
                {
                    "account_id": 1043604,
                    "account_name": "biofit.activehosted.com",
                    "account_web_domain": "biofit.example",
                    "arr": 14721,
                }
            ],
        },
        activecampaign_accounts=[
            {
                "id": "9001",
                "name": "BioFit",
                "accountUrl": "https://biofit.activehosted.com",
            }
        ],
    )

    assert preview["summary"] == {"matched": 1, "ambiguous": 0, "unmatched": 0}
    assert preview["matched"][0]["snowflake_account_id"] == 1043604
    assert preview["matched"][0]["ac_account_id"] == 9001
    assert preview["account_id_map"] == {"1043604": 9001}
    assert "1043604,9001" in preview["csv"]


def test_build_account_map_preview_buckets_ambiguous_and_unmatched() -> None:
    preview = build_account_map_preview(
        portfolio={
            "success_rep_name": "Kevin Oostema",
            "accounts": [
                {
                    "account_id": 1,
                    "account_name": "same.activehosted.com",
                    "arr": 100,
                },
                {
                    "account_id": 2,
                    "account_name": "missing.activehosted.com",
                    "arr": 200,
                },
            ],
        },
        activecampaign_accounts=[
            {"id": "10", "name": "same.activehosted.com"},
            {"id": "11", "accountUrl": "https://same.activehosted.com"},
        ],
    )

    assert preview["summary"] == {"matched": 0, "ambiguous": 1, "unmatched": 1}
    assert preview["ambiguous"][0]["snowflake_account_id"] == 1
    assert preview["ambiguous"][0]["candidate_count"] == 2
    assert preview["unmatched"][0]["snowflake_account_id"] == 2
