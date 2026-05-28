import csv
import json
from pathlib import Path
from typing import Any


class AccountResolver:
    def __init__(self, csv_path: Path, inline_json: str | None = None):
        self.csv_path = csv_path
        self.inline_json = inline_json
        self._mapping = self._load_mapping()

    def resolve(self, snowflake_account_id: int) -> int:
        try:
            return self._mapping[snowflake_account_id]
        except KeyError as exc:
            raise KeyError(
                "Missing ActiveCampaign account mapping for "
                f"Snowflake account {snowflake_account_id}"
            ) from exc

    def _load_mapping(self) -> dict[int, int]:
        inline_mapping = self._load_inline_mapping()
        if inline_mapping:
            return inline_mapping

        if not self.csv_path.exists():
            return {}

        with self.csv_path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            mapping: dict[int, int] = {}
            for row in reader:
                sf_id = int(row["snowflake_account_id"])
                ac_id = int(row["ac_account_id"])
                mapping[sf_id] = ac_id
        return mapping

    def _load_inline_mapping(self) -> dict[int, int]:
        if not self.inline_json:
            return {}

        payload = json.loads(self.inline_json)
        if not isinstance(payload, dict):
            raise ValueError("ACCOUNT_ID_MAP_JSON must be a JSON object")

        mapping: dict[int, int] = {}
        for snowflake_account_id, ac_account_id in payload.items():
            mapping[int(snowflake_account_id)] = _coerce_ac_account_id(ac_account_id)
        return mapping


def _coerce_ac_account_id(value: Any) -> int:
    if isinstance(value, dict):
        value = value.get("ac_account_id")
    return int(value)
