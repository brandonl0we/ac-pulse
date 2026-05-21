import csv
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.config import Settings


class AccountResolver:
    def __init__(self, csv_path: Path, inline_json: str | None = None):
        self.csv_path = csv_path
        self.inline_json = inline_json
        self._mapping = self._load_mapping()

    @classmethod
    def from_settings(cls, settings: Settings) -> "AccountResolver":
        return cls(
            csv_path=settings.account_id_map_path,
            inline_json=settings.account_id_map_json,
        )

    def resolve(self, snowflake_account_id: int) -> int:
        try:
            return self._mapping[snowflake_account_id]
        except KeyError as exc:
            raise KeyError(
                "Missing ActiveCampaign account mapping for "
                f"Snowflake account {snowflake_account_id}"
            ) from exc

    def _load_mapping(self) -> dict[int, int]:
        mapping = self._load_inline_mapping()
        if mapping:
            return mapping

        if not self.csv_path.exists():
            return {}

        with self.csv_path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                sf_id = int(row["snowflake_account_id"])
                ac_id = int(row["ac_account_id"])
                mapping[sf_id] = ac_id
        return mapping

    def _load_inline_mapping(self) -> dict[int, int]:
        if not self.inline_json:
            return {}

        raw_mapping = json.loads(self.inline_json)
        if isinstance(raw_mapping, Mapping):
            return {
                int(snowflake_account_id): int(ac_account_id)
                for snowflake_account_id, ac_account_id in raw_mapping.items()
            }

        if isinstance(raw_mapping, Sequence) and not isinstance(raw_mapping, str):
            mapping: dict[int, int] = {}
            for row in raw_mapping:
                mapping.update(_mapping_row_to_pair(row))
            return mapping

        raise ValueError(
            "ACCOUNT_ID_MAP_JSON must be a JSON object or a list of mapping rows"
        )


def _mapping_row_to_pair(row: Any) -> dict[int, int]:
    if not isinstance(row, Mapping):
        raise ValueError("ACCOUNT_ID_MAP_JSON rows must be objects")
    return {
        int(row["snowflake_account_id"]): int(row["ac_account_id"]),
    }
