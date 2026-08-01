from redis.asyncio import Redis

from legal_workbench.config import get_settings


settings = get_settings()
redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


async def redis_is_ready() -> bool:
    try:
        return bool(await redis_client.ping())
    except Exception:
        return False
