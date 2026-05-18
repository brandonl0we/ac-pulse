from typing import Any

from app.extractors.base import Extractor


class TouchpointsExtractor(Extractor):
    """Daily CSM touchpoint signals sourced from Totango-originated events.

    For MVP we intentionally filter to event_source = Totango to preserve continuity
    during migration. This can undercount if events have not landed yet for the day.
    """

    sql_file = "touchpoints.sql"

    async def extract(self) -> dict[int, dict[str, Any]]:
        rows = await self.sf.execute(self.sql)
        return {
            int(row["ACCOUNT_ID"]): {
                "account_id": int(row["ACCOUNT_ID"]),
                "days_since_touchpoint": int(row["DAYS_SINCE_TOUCHPOINT"])
                if row.get("DAYS_SINCE_TOUCHPOINT") is not None
                else None,
                "touchpoint_count_30d": int(row["TOUCHPOINT_COUNT_30D"])
                if row.get("TOUCHPOINT_COUNT_30D") is not None
                else None,
            }
            for row in rows
        }
