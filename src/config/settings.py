from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, computed_field

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"


class _DatabaseConfig(BaseModel):
    host: str = "localhost"
    port: int = 5432
    user: str = "trading"
    password: str = "trading_dev"
    name: str = "trading_analyzer"


class _RedisConfig(BaseModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    ttl_fundamentals: int = 86400
    ttl_price: int = 86400
    ttl_quote: int = 300


class Settings(BaseModel):
    database: _DatabaseConfig = _DatabaseConfig()
    redis: _RedisConfig = _RedisConfig()

    @computed_field
    @property
    def database_url(self) -> str:
        db = self.database
        return f"postgresql+psycopg://{db.user}:{db.password}@{db.host}:{db.port}/{db.name}"


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        with open(_CONFIG_PATH) as f:
            data = yaml.safe_load(f)
        _settings = Settings(**data)
    return _settings
