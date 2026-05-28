from app.ac_client.account_resolver import AccountResolver


def test_account_resolver_uses_inline_json_before_csv(tmp_path) -> None:
    csv_path = tmp_path / "account-map.csv"
    csv_path.write_text(
        "snowflake_account_id,ac_account_id\n1043604,111\n",
        encoding="utf-8",
    )

    resolver = AccountResolver(csv_path, '{"1043604": 9001}')

    assert resolver.resolve(1043604) == 9001


def test_account_resolver_accepts_richer_inline_rows(tmp_path) -> None:
    resolver = AccountResolver(
        tmp_path / "missing.csv",
        '{"1043604": {"ac_account_id": "9001"}}',
    )

    assert resolver.resolve(1043604) == 9001
