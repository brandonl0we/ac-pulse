from pathlib import Path

import pytest

from app.ac_client.account_resolver import AccountResolver


def test_account_resolver_reads_inline_object_mapping() -> None:
    resolver = AccountResolver(
        csv_path=Path("missing.csv"),
        inline_json='{"101": 9001}',
    )

    assert resolver.resolve(101) == 9001


def test_account_resolver_reads_inline_row_mapping() -> None:
    resolver = AccountResolver(
        csv_path=Path("missing.csv"),
        inline_json='[{"snowflake_account_id": 101, "ac_account_id": 9001}]',
    )

    assert resolver.resolve(101) == 9001


def test_account_resolver_inline_mapping_takes_precedence(tmp_path: Path) -> None:
    mapping_path = tmp_path / "account_id_map.csv"
    mapping_path.write_text(
        "snowflake_account_id,ac_account_id\n101,8001\n",
        encoding="utf-8",
    )

    resolver = AccountResolver(
        csv_path=mapping_path,
        inline_json='{"101": 9001}',
    )

    assert resolver.resolve(101) == 9001


def test_account_resolver_raises_for_missing_mapping() -> None:
    resolver = AccountResolver(csv_path=Path("missing.csv"))

    with pytest.raises(KeyError):
        resolver.resolve(101)
