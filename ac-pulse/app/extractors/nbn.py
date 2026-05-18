from typing import Any

from app.extractors.base import Extractor


class NBNExtractor(Extractor):
    """Monthly next-best-action signal from Snowflake curated source.

    The metric is used as context for prioritization and not as a standalone trigger.
    """

    sql_file = "nbn.sql"

    async def extract(self) -> dict[int, dict[str, Any]]:
        rows = await self.sf.execute(self.sql)
        return {
            int(row["ACCOUNT_ID"]): {
                "account_id": int(row["ACCOUNT_ID"]),
                "nbn_score": float(row["NBN_SCORE"]) if row.get("NBN_SCORE") is not None else None,
            }
            for row in rows
        }
