from functools import lru_cache
from typing import TYPE_CHECKING, cast

from legal_workbench.config import get_settings

if TYPE_CHECKING:
    from redis.asyncio import Redis


@lru_cache(maxsize=1)
def get_redis_client() -> "Redis":
    from redis.asyncio import Redis

    return cast(
        "Redis",
        Redis.from_url(get_settings().redis_url, decode_responses=True),
    )


async def redis_is_ready() -> bool:
    try:
        return bool(await get_redis_client().ping())
    except Exception:
        return False


async def close_redis_client() -> None:
    if get_redis_client.cache_info().currsize:
        await get_redis_client().aclose()
    get_redis_client.cache_clear()
