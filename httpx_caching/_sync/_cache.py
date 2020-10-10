from typing import Optional, Tuple

from httpx_caching._models import Response
from httpx_caching._serializer import Serializer
from httpx_caching._utils import SyncLock


class SyncDictCache:
    def __init__(self, serializer: Optional[Serializer] = None) -> None:
        self.serializer = serializer if serializer else Serializer()
        self.data: dict = {}
        self.lock = None

    def get_lock(self):
        if not self.lock:
            self.lock = SyncLock()
        return self.lock

    def get(self, key: str) -> Tuple[Optional[Response], Optional[dict]]:
        return self.serializer.loads(self.data.get(key, None))

    def set(
        self, key: str, response: Response, vary_header_data: dict, response_body: bytes
    ) -> None:
        with self.get_lock():
            self.data.update(
                {key: self.serializer.dumps(response, vary_header_data, response_body)}
            )

    def delete(self, key: str) -> None:
        with self.get_lock():
            if key in self.data:
                self.data.pop(key)

    def close(self):
        pass
