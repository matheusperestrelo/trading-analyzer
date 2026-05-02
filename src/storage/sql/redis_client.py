import os
import redis 
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")

client = redis.Redis.from_url(
    REDIS_URL,
    decode_responses=True
)

def get_client() -> redis.Redis:
    return client

def test_connection() -> bool:
    try:
        client.ping()
        logger.info("Redis conectado com sucesso")
        return True
    except Exception as e:
        logger.info(f"Erro ao conectar no Redis: {e}")
        return False