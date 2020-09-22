import dataclasses
from typing import Iterable

from httpx import Headers

@dataclasses.dataclass
class Response:
    """
    Simple wrapper for the raw response returned by a transport.
    """
    status_code: int
    headers: Headers
    stream: Iterable
    ext: dict

    @classmethod
    def from_raw(cls, raw_response):
        values = list(raw_response)
        values[1] = Headers(values[1])
        return cls(*values)

    def to_raw(self):
        raw = []
        for field in dataclasses.fields(self):
            value = getattr(self, field.name)
            if field.name == 'headers':
                value = value.raw
            raw.append(value)
        return tuple(raw)
