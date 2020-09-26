from threading import Lock
from typing import Optional, Tuple

from ._models import Response
from ._serializer import Serializer


class DictCache:
    def __init__(self, serializer: Optional[Serializer] = None) -> None:
        self.lock = Lock()
        self.serializer = serializer if serializer else Serializer()
        self.data: dict = {}

    async def aget(self, key: str) -> Tuple[Optional[Response], Optional[dict]]:
        return self.serializer.loads(self.data.get(key, None))

    def get(self, key: str) -> Tuple[Optional[Response], Optional[dict]]:
        return self.serializer.loads(self.data.get(key, None))

    async def aset(
        self, key: str, response: Response, vary_header_data: dict, response_body: bytes
    ) -> None:
        with self.lock:
            self.data.update(
                {key: self.serializer.dumps(response, vary_header_data, response_body)}
            )

    async def adelete(self, key: str) -> None:
        with self.lock:
            if key in self.data:
                self.data.pop(key)

    def set(
        self, key: str, response: Response, vary_header_data: dict, response_body: bytes
    ) -> None:
        with self.lock:
            self.data.update(
                {key: self.serializer.dumps(response, vary_header_data, response_body)}
            )

    def delete(self, key: str) -> None:
        with self.lock:
            if key in self.data:
                self.data.pop(key)

    def close(self):
        pass

    async def aclose(self):
        pass
