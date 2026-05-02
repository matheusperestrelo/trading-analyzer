from src.storage.sql.database import test_connection as test_postgres
from src.storage.sql.redis_client import test_connection as test_redis

def test_postgres_connection():
    assert test_postgres() is True

def test_redis_connection():
    assert test_redis() is True