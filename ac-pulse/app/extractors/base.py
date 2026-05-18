from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.snowflake_client import SnowflakeClient


class Extractor(ABC):
    """One extractor per Snowflake source. Owns a single SQL file and transform step.

    These queries power operational signal movement into ActiveCampaign and should
    remain analyst-readable. Keep business logic in Python transformation minimal.
    """

    sql_file: str

    def __init__(self, sf: SnowflakeClient):
        self.sf = sf

    @property
    def sql(self) -> str:
        path = Path(__file__).parent.parent.parent / "sql" / "extractors" / self.sql_file
        return path.read_text(encoding="utf-8")

    @abstractmethod
    async def extract(self) -> dict[int, dict[str, Any]]: ...
