from typing import Optional, Tuple

from httpx_caching._models import Response
from httpx_caching._serializer import Serializer
from httpx_caching._utils import AsyncLock


class AsyncDictCache:
    def __init__(self, serializer: Optional[Serializer] = None) -> None:
        self.serializer = serializer if serializer else Serializer()
        self.data: dict = {}
        self.lock = None

    def get_lock(self):
        if not self.lock:
            self.lock = AsyncLock()
        return self.lock

    async def aget(self, key: str) -> Tuple[Optional[Response], Optional[dict]]:
        return self.serializer.loads(self.data.get(key, None))

    async def aset(
        self, key: str, response: Response, vary_header_data: dict, response_body: bytes
    ) -> None:
        async with self.get_lock():
            self.data.update(
                {key: self.serializer.dumps(response, vary_header_data, response_body)}
            )

    async def adelete(self, key: str) -> None:
        async with self.get_lock():
            if key in self.data:
                self.data.pop(key)

    async def aclose(self):
        pass
