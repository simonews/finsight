import redis

from app.core.config import settings

CACHE_TTL_SECONDS = 900

_client: redis.Redis | None = None


def get_redis_sync() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client