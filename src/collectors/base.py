from abc import ABC, abstractmethod
from datetime import datetime
from pydantic import BaseModel


class CollectorResult(BaseModel):
    ticker: str
    source: str
    collected_at: datetime
    fundamentals: dict
    raw_json: dict
    text_description: str
    success: bool
    error: str | None = None


class BaseCollector(ABC):
    @abstractmethod
    def collect(self, ticker: str) -> CollectorResult:
        ...

    @abstractmethod
    def healthcheck(self) -> bool:
        ...
