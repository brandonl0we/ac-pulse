import csv
from pathlib import Path


class AccountResolver:
    def __init__(self, csv_path: Path):
        self.csv_path = csv_path
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
