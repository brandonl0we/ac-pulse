from typing import Any

from app.extractors.base import Extractor


class ACAIExtractor(Extractor):
    """Monthly ACAI signal feed used as a directional health indicator.

    Refresh cadence is monthly. Missing values are propagated as None and handled
    downstream by the model validator before any ActiveCampaign writes.
    """

    sql_file = "acai.sql"

    async def extract(self) -> dict[int, dict[str, Any]]:
        rows = await self.sf.execute(self.sql)
        return {
            int(row["ACCOUNT_ID"]): {
                "account_id": int(row["ACCOUNT_ID"]),
                "acai_score": float(row["ACAI_SCORE"])
                if row.get("ACAI_SCORE") is not None
                else None,
            }
            for row in rows
        }
