from datetime import date
from typing import Any

from app.extractors.base import Extractor


class RenewalExtractor(Extractor):
    """Daily renewal horizon signals for account intervention timing.

    Source comes from renewal schedule tables and should remain point-in-time aware;
    downstream snapshotting captures these values before churn state mutates source rows.
    """

    sql_file = "renewal.sql"

    async def extract(self) -> dict[int, dict[str, Any]]:
        rows = await self.sf.execute(self.sql)
        payload: dict[int, dict[str, Any]] = {}
        for row in rows:
            renewal_raw = row.get("RENEWAL_DATE")
            renewal_date = renewal_raw if isinstance(renewal_raw, date) else None
            account_id = int(row["ACCOUNT_ID"])
            payload[account_id] = {
                "account_id": account_id,
                "days_to_renewal": int(row["DAYS_TO_RENEWAL"])
                if row.get("DAYS_TO_RENEWAL") is not None
                else None,
                "renewal_date": renewal_date,
            }
        return payload
