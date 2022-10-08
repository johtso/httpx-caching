from typing import Optional, Tuple
import redis as redis
from httpx_caching._models import Response
from httpx_caching._serializer import Serializer
from httpx_caching._utils import SyncLock


class SyncRedisCache:
    def __init__(self, serializer: Optional[Serializer] = None) -> None:
        self.serializer = serializer if serializer else Serializer()
        self.redis = redis.Redis()
        self.lock = None

    def get_lock(self):
        if not self.lock:
            self.lock = SyncLock()
        return self.lock

    def get(self, key: str) -> Tuple[Optional[Response], Optional[dict]]:
        value = self.redis.get(key)
        return self.serializer.loads(value)

    def set(
        self, key: str, response: Response, vary_header_data: dict, response_body: bytes
    ) -> None:
        with self.get_lock():
            self.redis.set(key, self.serializer.dumps(response, vary_header_data, response_body))

    def delete(self, key: str) -> None:
        with self.get_lock():
            self.redis.delete(key)

    def close(self):
        self.redis.close()
