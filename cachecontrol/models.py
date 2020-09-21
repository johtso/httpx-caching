import dataclasses
from typing import Iterable

from httpx import Headers

@dataclasses.dataclass
class Response:
    """
    Simple wrapper for the raw response returned by a transport.
    """
    http_version: bytes
    status_code: int
    reason_phrase: bytes
    headers: Headers
    stream: Iterable

    @classmethod
    def from_raw(cls, raw_response):
        values = list(raw_response)
        values[3] = Headers(values[3])
        return cls(*values)

    def to_raw(self):
        raw = []
        for field in dataclasses.fields(self):
            value = getattr(self, field.name)
            if field.name == 'headers':
                value = value.raw
            raw.append(value)
        return tuple(raw)
