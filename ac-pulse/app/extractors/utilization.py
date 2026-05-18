from typing import Any

from app.extractors.base import Extractor


class UtilizationExtractor(Extractor):
    """Daily product utilization rollup for account-level activity health.

    This source is refreshed daily and can be sparse on weekends depending on
    ingestion lag; missing values are expected for low-activity accounts.
    """

    sql_file = "utilization.sql"

    async def extract(self) -> dict[int, dict[str, Any]]:
        rows = await self.sf.execute(self.sql)
        return {
            int(row["ACCOUNT_ID"]): {
                "account_id": int(row["ACCOUNT_ID"]),
                "utilization_percent": float(row["UTILIZATION_PERCENT"])
                if row.get("UTILIZATION_PERCENT") is not None
                else None,
            }
            for row in rows
        }
