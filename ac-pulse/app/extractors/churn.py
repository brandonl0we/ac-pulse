from typing import Any

from app.extractors.base import Extractor


class ChurnExtractor(Extractor):
    """Monthly churn model drivers pulled from VELOCITY_CHURN_MODEL predictions.

    Source is model-scored and updated monthly. It is suitable for operational ranking
    but should still be snapshotted for point-in-time history reconstruction.
    """

    sql_file = "churn.sql"

    async def extract(self) -> dict[int, dict[str, Any]]:
        rows = await self.sf.execute(self.sql)
        return {
            int(row["ACCOUNT_ID"]): {
                "account_id": int(row["ACCOUNT_ID"]),
                "churn_decile_band": row.get("CHURN_DECILE_BAND"),
                "churn_score": float(row["CHURN_SCORE"])
                if row.get("CHURN_SCORE") is not None
                else None,
            }
            for row in rows
        }
