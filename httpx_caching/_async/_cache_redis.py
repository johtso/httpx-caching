from typing import Optional, Tuple
import redis.asyncio as redis
from httpx_caching._models import Response
from httpx_caching._serializer import Serializer
from httpx_caching._utils import AsyncLock


class AsyncRedisCache:
    def __init__(self, serializer: Optional[Serializer] = None) -> None:
        self.serializer = serializer if serializer else Serializer()
        self.redis = redis.Redis()
        self.lock = None

    def get_lock(self):
        if not self.lock:
            self.lock = AsyncLock()
        return self.lock

    async def aget(self, key: str) -> Tuple[Optional[Response], Optional[dict]]:
        value = await self.redis.get(key)
        return self.serializer.loads(value)

    async def aset(
        self, key: str, response: Response, vary_header_data: dict, response_body: bytes
    ) -> None:
        async with self.get_lock():
            await self.redis.set(key, self.serializer.dumps(response, vary_header_data, response_body))

    async def adelete(self, key: str) -> None:
        async with self.get_lock():
            await self.redis.delete(key)

    async def aclose(self):
        await self.redis.close()
